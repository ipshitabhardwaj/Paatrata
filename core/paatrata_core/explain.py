"""Explanations of a deterministic verdict.

The English explanation is a template (no LLM). Hindi/Punjabi go through Gemini,
which is given the verdict and the per-condition results and must echo the
verdict code back; if it does not match, we fall back to the template.
"""
from __future__ import annotations

import json

from .schema import Verdict
from .vocabulary import FIELDS

LANGS = {"en": "English", "hi": "Hindi", "pa": "Punjabi (Gurmukhi script)"}

_OP_WORDS = {">=": "at least", ">": "more than", "<=": "at most", "<": "less than", "==": "equal to",
             "!=": "not", "in": "one of", "not_in": "not one of"}


def _fmt(field: str, v) -> str:
    spec = FIELDS.get(field)
    if spec and spec.type == "number":
        v = float(v)
        s = f"{v:,.0f}" if v == int(v) else f"{v:,}"
        return f"₹{s}" if spec.unit == "INR" else f"{s} {spec.unit or ''}".strip()
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, list):
        return ", ".join(v)
    return str(v)


def _short(q: str, n: int = 110) -> str:
    q = " ".join(q.split())
    return q if len(q) <= n else q[:n].rsplit(" ", 1)[0] + "…"


def template_explanation(v: Verdict, scheme_name: str) -> str:
    head = {
        "ELIGIBLE": f"Based on the details given, the applicant appears ELIGIBLE for {scheme_name}.",
        "NOT_ELIGIBLE": f"Based on the details given, the applicant is NOT ELIGIBLE for {scheme_name}.",
        "NEEDS_INFO": f"More information is needed to decide eligibility for {scheme_name}.",
    }[v.verdict]
    lines = [head]
    for r in v.results:
        op_words = "" if r.op == "==" else _OP_WORDS.get(r.op, r.op) + " "
        rule = f"{r.field.replace('_', ' ')} must be {op_words}{_fmt(r.field, r.expected)}"
        cite = f'(source p.{r.citation.page}: "{_short(r.citation.quote)}")'
        if r.outcome == "FALSE":
            lines.append(f"- Not met: {rule}; given {_fmt(r.field, r.actual)} {cite}")
        elif r.outcome == "UNKNOWN":
            lines.append(f"- Missing: {r.field.replace('_', ' ')} is needed — {rule} {cite}")
        else:
            lines.append(f"- Met: {rule} {cite}")
    for u in v.unmapped_conditions:
        lines.append(f"- Also requires verification by the department: {u.text}")
    lines.append(v.disclaimer)
    return "\n".join(lines)


def explain(v: Verdict, scheme_name: str, lang: str = "en", model: str | None = None) -> dict:
    """Return {'text', 'lang', 'source': 'template'|'gemini', 'verdict_check': bool, 'meta'?}."""
    base = template_explanation(v, scheme_name)
    if lang == "en":
        return {"text": base, "lang": "en", "source": "template", "verdict_check": True}
    from .extractors.base import ExtractionError, parse_json_text
    from .extractors.gemini import generate_json

    prompt = (
        f"Rewrite this eligibility result for a citizen in simple {LANGS.get(lang, lang)}. "
        "Do not change the decision, numbers or conditions; do not add advice or new facts. "
        'Return JSON: {"verdict": "<the verdict code exactly as given>", "explanation": "<text>"}.\n\n'
        f"VERDICT CODE: {v.verdict}\nRESULT:\n{base}\n\nSTRUCTURED:\n{json.dumps(v.model_dump(), ensure_ascii=False)[:6000]}"
    )
    try:
        raw, meta = generate_json(prompt, model=model)
        data = parse_json_text(raw)
        ok = data.get("verdict") == v.verdict and bool(data.get("explanation"))
        if ok:
            return {"text": data["explanation"], "lang": lang, "source": "gemini", "verdict_check": True,
                    "meta": meta.__dict__}
        return {"text": base, "lang": "en", "source": "template", "verdict_check": False,
                "note": "Model output failed the verdict check; showing the English template.", "meta": meta.__dict__}
    except (ExtractionError, ValueError) as e:
        return {"text": base, "lang": "en", "source": "template", "verdict_check": False,
                "note": f"Translation unavailable: {e}"}
