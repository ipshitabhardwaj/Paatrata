"""Second pass: an independent Gemini review of the compiled rules against the source.

Extraction models tend to be over-confident (the first live run gave 100% confidence on
'family income' with no question for the officer). The reviewer looks only for three
things: missing conditions, misread conditions, and ambiguities. Every finding must carry a
verbatim quote that the validator can find in the source, otherwise it is dropped.

Findings never change a rule by themselves. Ambiguities and possible misreads are attached
to the condition as questions, which blocks approval until an officer answers them.
"""
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from .extractors.base import CallMeta, ExtractionError, parse_json_text
from .extractors.prompts import REVIEW_VERSION, review_prompt
from .ingest import SourceDoc
from .schema import Issue, RuleSet
from .validator import QUOTE_MATCH_THRESHOLD, match_quote


class ReviewFinding(BaseModel):
    kind: Literal["missing", "misread", "ambiguity"]
    condition_id: Optional[str] = Field(default=None, description="Id of the encoded condition; null for 'missing'.")
    quote: str = Field(description="Verbatim text from the source supporting the finding.")
    message: str = Field(description="For ambiguity: one question for the officer. Otherwise: what is wrong or missing.")


class ReviewResult(BaseModel):
    findings: list[ReviewFinding]


def _conditions_text(rules: RuleSet) -> str:
    groups = {g.id: g for g in rules.groups}
    lines = []
    for c in rules.conditions:
        g = groups.get(c.group)
        lines.append(f"- {c.id} [group {c.group} ({g.logic if g else '?'})]: {c.field} {c.op} {c.value}  "
                     f"(quote: \"{c.citation.quote}\")")
    return "\n".join(lines) or "(none)"


def _cache_dir() -> Path:
    return Path(os.environ.get("PAATRATA_CACHE_DIR", "evaluation/cache")) / "review"


def review_rules(rules: RuleSet, doc: SourceDoc, model: Optional[str] = None,
                 live: bool = True) -> tuple[Optional[ReviewResult], CallMeta]:
    """Run (or replay from cache) the Gemini review. Returns (result or None, meta)."""
    from .extractors.gemini import DEFAULT_GEMINI_MODEL, generate_structured

    model = model or DEFAULT_GEMINI_MODEL
    source = doc.numbered_text() if doc.has_text else "(scanned document: no text layer available)"
    unmapped = "\n".join(f"- {u.text}" for u in rules.unmapped_conditions) or "(none)"
    prompt = review_prompt(_conditions_text(rules), unmapped, source)
    key = hashlib.sha256(json.dumps([REVIEW_VERSION, model, prompt]).encode()).hexdigest()[:24]
    path = _cache_dir() / f"{key}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = CallMeta(**{**data["meta"], "cache_hit": True, "latency_ms": 0})
        return ReviewResult.model_validate(data["result"]), meta
    if not live:
        return None, CallMeta(backend="gemini-review", model=model, error="not cached")
    t0 = time.time()
    raw, meta = generate_structured(prompt, ReviewResult, model=model)
    meta.backend, meta.latency_ms = "gemini-review", int((time.time() - t0) * 1000)
    try:
        result = ReviewResult.model_validate(parse_json_text(raw))
    except (ValidationError, ValueError) as e:
        meta.error = f"invalid review JSON: {e}"[:300]
        return None, meta
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"result": result.model_dump(), "meta": meta.__dict__}, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return result, meta


def apply_review(rules: RuleSet, result: ReviewResult, doc: SourceDoc) -> list[Issue]:
    """Attach grounded findings to the rules (in place) and return them as issues."""
    issues: list[Issue] = []
    by_id = {c.id: c for c in rules.conditions}
    for f in result.findings:
        if doc.has_text:
            _, score = match_quote(f.quote, doc.pages, None)
            if score < QUOTE_MATCH_THRESHOLD:
                issues.append(Issue(level="info", code="review_unverified", condition_id=f.condition_id,
                                    message=f"Reviewer finding dropped: its quote is not in the source ({f.message[:120]})"))
                continue
        cond = by_id.get(f.condition_id or "")
        if f.kind == "missing" or cond is None:
            issues.append(Issue(level="warning", code="review_missing",
                                message=f"[reviewer] Possibly missing condition: {f.message} (source: \"{f.quote[:120]}\")"))
            continue
        question = f.message if f.kind == "ambiguity" else f"[possible misread] {f.message}"
        if not cond.ambiguity:
            cond.ambiguity = question
            cond.confidence = min(cond.confidence, 0.79)
        issues.append(Issue(level="warning", code="ambiguity" if f.kind == "ambiguity" else "review_misread",
                            condition_id=cond.id, message=f"[reviewer] {question}"))
    return issues


def review_and_apply(rules: RuleSet, doc: SourceDoc, model: Optional[str] = None,
                     live: bool = True) -> tuple[list[Issue], Optional[CallMeta]]:
    """Convenience wrapper that never raises: a failed review becomes an info issue."""
    try:
        result, meta = review_rules(rules, doc, model=model, live=live)
    except ExtractionError as e:
        return [Issue(level="info", code="review_skipped", message=f"Review skipped: {e}")], None
    if result is None:
        return [Issue(level="info", code="review_skipped", message=f"Review skipped: {meta.error}")], meta
    issues = apply_review(rules, result, doc)
    if not result.findings:
        issues.append(Issue(level="info", code="review_clean", message="[reviewer] No missing, misread or ambiguous conditions found."))
    return issues, meta
