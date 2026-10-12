"""Turn an LLM ``SchemeDraft`` into a validated ``RuleSet``.

Nothing reaches the rulebook unless code can check it:

* field must be in the vocabulary and the operator legal for its type
* value must normalise deterministically (e.g. "1.5 lakh" -> 150000)
* the quote must actually occur in the source (fuzzy match), on the cited page
  or, failing that, on some page (page corrected, warning raised)
* groups must form a single tree

Conditions that fail a hard check are *rejected* (kept in the report, not in
the rules). Soft problems become warnings/flags for the reviewing officer.
"""
from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

from .ingest import SourceDoc
from .normalize import NormalizationError, normalize_value
from .schema import Citation, Condition, DraftGroup, Group, Issue, RuleSet, SchemeDraft
from .vocabulary import FIELDS, OPS_BY_TYPE

QUOTE_MATCH_THRESHOLD = 90.0
LOW_CONFIDENCE = 0.6


def _norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


def match_quote(quote: str, pages: list[str], page_hint: int | None) -> tuple[int | None, float]:
    """Return (page, score) of the best match for `quote` across pages."""
    q = _norm_text(quote)
    if not q or not pages:
        return None, 0.0
    best_page, best = None, 0.0
    order = list(range(1, len(pages) + 1))
    if page_hint and 1 <= page_hint <= len(pages):
        order.remove(page_hint)
        order.insert(0, page_hint)
    for p in order:
        text = _norm_text(pages[p - 1])
        if not text:
            continue
        score = 100.0 if q in text else fuzz.partial_ratio(q, text)
        if score > best:
            best_page, best = p, score
        if best == 100.0:
            break
    return best_page, best


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "scheme"


def compile_draft(
    draft: SchemeDraft,
    source: SourceDoc | None,
    extractor: str,
    scheme_id: str | None = None,
) -> tuple[RuleSet, list[Issue]]:
    issues: list[Issue] = []

    # ---- groups ------------------------------------------------------------
    groups: dict[str, DraftGroup] = {g.id: g.model_copy() for g in draft.groups}
    roots = [g for g in groups.values() if g.parent is None]
    if len(roots) == 1:
        root_id = roots[0].id
    else:
        root_id = "__root__"
        issues.append(Issue(level="warning", code="no_single_root",
                            message=f"Expected one root group, found {len(roots)}; added an ALL root above them."))
        for g in roots:
            g.parent = root_id
        groups[root_id] = DraftGroup(id=root_id, logic="ALL", parent=None)
    for g in groups.values():
        if g.id == root_id:
            continue
        # unknown parent or a cycle -> attach to root
        seen, cur, broken = {g.id}, g.parent, False
        while cur is not None and cur != root_id:
            if cur not in groups or cur in seen:
                broken = True
                break
            seen.add(cur)
            cur = groups[cur].parent
        if broken:
            issues.append(Issue(level="warning", code="bad_parent",
                                message=f"Group {g.id} had an invalid parent chain; attached to root."))
            g.parent = root_id

    # ---- conditions --------------------------------------------------------
    pages = source.pages if source else []
    can_verify = bool(source and source.has_text)
    if not can_verify:
        issues.append(Issue(level="warning", code="no_source_text",
                            message="Source has no extractable text (scanned PDF?). Quotes could not be verified."))

    conditions: list[Condition] = []
    seen_ids: set[str] = set()
    for i, dc in enumerate(draft.conditions, start=1):
        cid = dc.id if dc.id and dc.id not in seen_ids else f"c{i}"
        seen_ids.add(cid)
        spec = FIELDS.get(dc.field)
        if spec is None:
            issues.append(Issue(level="error", code="unknown_field", condition_id=cid,
                                message=f"Field '{dc.field}' is not in the vocabulary; condition rejected."))
            continue
        if dc.op not in OPS_BY_TYPE[spec.type]:
            issues.append(Issue(level="error", code="bad_operator", condition_id=cid,
                                message=f"Operator '{dc.op}' is not valid for {spec.type} field {dc.field}; rejected."))
            continue
        try:
            value = normalize_value(dc.field, dc.op, dc.value, dc.value_as_written)
        except NormalizationError as e:
            issues.append(Issue(level="error", code="bad_value", condition_id=cid,
                                message=f"Could not normalise value {dc.value!r} / {dc.value_as_written!r}: {e}; rejected."))
            continue

        page, score = match_quote(dc.quote, pages, dc.page) if can_verify else (dc.page, 0.0)
        verified = can_verify and score >= QUOTE_MATCH_THRESHOLD
        if can_verify and not verified:
            issues.append(Issue(level="error", code="quote_not_found", condition_id=cid,
                                message=f"Quote not found in source (best match {score:.0f}%); rejected: {dc.quote[:120]!r}"))
            continue
        if verified and page != dc.page:
            issues.append(Issue(level="info", code="page_corrected", condition_id=cid,
                                message=f"Quote found on page {page}, not {dc.page}; page corrected."))

        group = dc.group if dc.group in groups else root_id
        if group != dc.group:
            issues.append(Issue(level="warning", code="bad_group", condition_id=cid,
                                message=f"Unknown group '{dc.group}'; attached to root."))
        if dc.confidence < LOW_CONFIDENCE:
            issues.append(Issue(level="warning", code="low_confidence", condition_id=cid,
                                message=f"Model confidence {dc.confidence:.2f}; please review."))
        if dc.ambiguity:
            issues.append(Issue(level="warning", code="ambiguity", condition_id=cid, message=dc.ambiguity))

        conditions.append(Condition(
            id=cid, group=group, field=dc.field, op=dc.op, value=value,
            citation=Citation(doc_id=source.doc_id if source else None, page=page or dc.page,
                              quote=dc.quote, verified=verified, match_score=round(score, 1)),
            confidence=dc.confidence, ambiguity=dc.ambiguity,
        ))

    for u in draft.unmapped_conditions:
        issues.append(Issue(level="warning", code="unmapped",
                            message=f"Not computable, needs human verification: {u.text} ({u.reason})"))

    # duplicate / contradictory numeric bounds on the same field in the same group
    by_key: dict[tuple[str, str], list[Condition]] = {}
    for c in conditions:
        by_key.setdefault((c.group, c.field), []).append(c)
    for (g, f), cs in by_key.items():
        lows = [float(c.value) for c in cs if c.op in (">=", ">")]
        highs = [float(c.value) for c in cs if c.op in ("<=", "<")]
        if groups[g].logic == "ALL" and lows and highs and max(lows) > min(highs):
            issues.append(Issue(level="error", code="contradiction",
                                message=f"Contradictory bounds on {f} in group {g}: >= {max(lows)} and <= {min(highs)}."))

    if not conditions:
        issues.append(Issue(level="error", code="no_conditions", message="No valid conditions extracted."))

    rules = RuleSet(
        scheme_id=scheme_id or slugify(draft.scheme_name),
        scheme_name=draft.scheme_name,
        department=draft.department,
        jurisdiction=draft.jurisdiction,
        benefit_summary=draft.benefit_summary,
        groups=[Group(id=g.id, logic=g.logic, parent=g.parent) for g in groups.values()],
        conditions=conditions,
        unmapped_conditions=draft.unmapped_conditions,
        documents_required=draft.documents_required,
        source_doc_ids=[source.doc_id] if source else [],
        extractor=extractor,
    )
    return rules, issues


def blocking_issues(issues: list[Issue]) -> list[Issue]:
    """Issues that must be resolved before approval (warnings about ambiguity too)."""
    return [i for i in issues if i.code in {"contradiction", "no_conditions"}]
