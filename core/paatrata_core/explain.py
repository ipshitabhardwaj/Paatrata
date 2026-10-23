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

_OP_WORDS_HI = {">=": "कम से कम", ">": "से अधिक", "<=": "अधिक से अधिक", "<": "से कम", "==": "बराबर",
                "!=": "नहीं", "in": "में से एक", "not_in": "में से नहीं"}
_OP_WORDS_PA = {">=": "ਘੱਟੋ-ਘੱਟ", ">": "ਤੋਂ ਵੱਧ", "<=": "ਵੱਧ ਤੋਂ ਵੱਧ", "<": "ਤੋਂ ਘੱਟ", "==": "ਬਰਾਬਰ",
                "!=": "ਨਹੀਂ", "in": "ਵਿੱਚੋਂ ਇੱਕ", "not_in": "ਵਿੱਚੋਂ ਨਹੀਂ"}

_FIELD_NAMES_HI = {
    "age_years": "आयु (वर्ष)", "gender": "लिंग", "marital_status": "वैवाहिक स्थिति",
    "family_annual_income_inr": "पारिवारिक वार्षिक आय (₹)", "residence_years_in_jurisdiction": "चंडीगढ़ में निवास (वर्ष)",
    "is_domicile_of_jurisdiction": "चंडीगढ़ का निवासी", "is_disabled": "विकलांग", "disability_percentage": "विकलांगता प्रतिशत",
    "is_bpl": "गरीबी रेखा से नीचे", "caste_category": "जाति श्रेणी", "is_construction_worker": "निर्माण श्रमिक",
    "is_registered_construction_worker": "पंजीकृत निर्माण श्रमिक", "children_count": "बच्चों की संख्या",
    "youngest_child_age_months": "सबसे छोटे बच्चे की आयु (महीने)", "is_pregnant": "गर्भवती", "is_lactating": "स्तनपान कराने वाली",
}
_FIELD_NAMES_PA = {
    "age_years": "ਉਮਰ (ਸਾਲ)", "gender": "ਲਿੰਗ", "marital_status": "ਵਿਆਹੁਤਾ ਸਥਿਤੀ",
    "family_annual_income_inr": "ਪਰਿਵਾਰਕ ਸਾਲਾਨਾ ਆਮਦਨ (₹)", "residence_years_in_jurisdiction": "ਚੰਡੀਗੜ੍ਹ ਵਿੱਚ ਨਿਵਾਸ (ਸਾਲ)",
    "is_domicile_of_jurisdiction": "ਚੰਡੀਗੜ੍ਹ ਦਾ ਨਿਵਾਸੀ", "is_disabled": "ਅਪੰਗ", "disability_percentage": "ਅਪੰਗਤਾ ਪ੍ਰਤੀਸ਼ਤ",
    "is_bpl": "ਗ਼ਰੀਬੀ ਰੇਖਾ ਤੋਂ ਹੇਠਾਂ", "caste_category": "ਜਾਤ ਸ਼੍ਰੇਣੀ", "is_construction_worker": "ਉਸਾਰੀ ਮਜ਼ਦੂਰ",
    "is_registered_construction_worker": "ਰਜਿਸਟਰਡ ਉਸਾਰੀ ਮਜ਼ਦੂਰ", "children_count": "ਬੱਚਿਆਂ ਦੀ ਗਿਣਤੀ",
    "youngest_child_age_months": "ਸਭ ਤੋਂ ਛੋਟੇ ਬੱਚੇ ਦੀ ਉਮਰ (ਮਹੀਨੇ)", "is_pregnant": "ਗਰਭਵਤੀ", "is_lactating": "ਦੁੱਧ ਚੁੰਘਾਉਣ ਵਾਲੀ",
}


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


def _field_hi(f: str) -> str:
    return _FIELD_NAMES_HI.get(f, f.replace("_", " "))


def _field_pa(f: str) -> str:
    return _FIELD_NAMES_PA.get(f, f.replace("_", " "))


def template_explanation_hi(v: Verdict, scheme_name: str) -> str:
    head = {
        "ELIGIBLE": f"दी गई जानकारी के अनुसार, आवेदक {scheme_name} के लिए पात्र प्रतीत होता है।",
        "NOT_ELIGIBLE": f"दी गई जानकारी के अनुसार, आवेदक {scheme_name} के लिए पात्र नहीं है।",
        "NEEDS_INFO": f"{scheme_name} के लिए पात्रता तय करने हेतु और जानकारी चाहिए।",
    }[v.verdict]
    lines = [head]
    for r in v.results:
        op_w = "" if r.op == "==" else (_OP_WORDS_HI.get(r.op, r.op) + " ")
        rule = f"{_field_hi(r.field)} {op_w}{_fmt(r.field, r.expected)} होना चाहिए"
        cite = f'(स्रोत पृष्ठ {r.citation.page}: "{_short(r.citation.quote)}")'
        if r.outcome == "FALSE":
            lines.append(f"- पूरी नहीं: {rule}; दिया गया {_fmt(r.field, r.actual)} {cite}")
        elif r.outcome == "UNKNOWN":
            lines.append(f"- जानकारी नहीं: {_field_hi(r.field)} आवश्यक — {rule} {cite}")
        else:
            lines.append(f"- पूरी: {rule} {cite}")
    for u in v.unmapped_conditions:
        lines.append(f"- विभाग द्वारा सत्यापन आवश्यक: {u.text}")
    lines.append(v.disclaimer)
    return "\n".join(lines)


def template_explanation_pa(v: Verdict, scheme_name: str) -> str:
    head = {
        "ELIGIBLE": f"ਦਿੱਤੀ ਗਈ ਜਾਣਕਾਰੀ ਅਨੁਸਾਰ, ਬਿਨੈਕਾਰ {scheme_name} ਲਈ ਯੋਗ ਜਾਪਦਾ ਹੈ।",
        "NOT_ELIGIBLE": f"ਦਿੱਤੀ ਗਈ ਜਾਣਕਾਰੀ ਅਨੁਸਾਰ, ਬਿਨੈਕਾਰ {scheme_name} ਲਈ ਯੋਗ ਨਹੀਂ ਹੈ।",
        "NEEDS_INFO": f"{scheme_name} ਲਈ ਯੋਗਤਾ ਤੈਅ ਕਰਨ ਲਈ ਹੋਰ ਜਾਣਕਾਰੀ ਚਾਹੀਦੀ ਹੈ।",
    }[v.verdict]
    lines = [head]
    for r in v.results:
        op_w = "" if r.op == "==" else (_OP_WORDS_PA.get(r.op, r.op) + " ")
        rule = f"{_field_pa(r.field)} {op_w}{_fmt(r.field, r.expected)} ਹੋਣਾ ਚਾਹੀਦਾ ਹੈ"
        cite = f'(ਸਰੋਤ ਪੰਨਾ {r.citation.page}: "{_short(r.citation.quote)}")'
        if r.outcome == "FALSE":
            lines.append(f"- ਪੂਰੀ ਨਹੀਂ: {rule}; ਦਿੱਤਾ ਗਿਆ {_fmt(r.field, r.actual)} {cite}")
        elif r.outcome == "UNKNOWN":
            lines.append(f"- ਜਾਣਕਾਰੀ ਨਹੀਂ: {_field_pa(r.field)} ਲੋੜੀਂਦਾ — {rule} {cite}")
        else:
            lines.append(f"- ਪੂਰੀ: {rule} {cite}")
    for u in v.unmapped_conditions:
        lines.append(f"- ਵਿਭਾਗ ਵੱਲੋਂ ਤਸਦੀਕ ਲੋੜੀਂਦੀ: {u.text}")
    lines.append(v.disclaimer)
    return "\n".join(lines)


def explain(v: Verdict, scheme_name: str, lang: str = "en", model: str | None = None) -> dict:
    """Return {'text', 'lang', 'source': 'template'|'gemini', 'verdict_check': bool, 'meta'?}."""
    base = template_explanation(v, scheme_name)
    if lang == "en":
        return {"text": base, "lang": "en", "source": "template", "verdict_check": True}

    # Local template fallback for Hindi/Punjabi (no LLM needed)
    _local_templates = {"hi": template_explanation_hi, "pa": template_explanation_pa}
    local_text = _local_templates.get(lang, lambda *_: None)(v, scheme_name)

    # Try Gemini for a more natural translation; fall back to local template
    import os
    _demo = os.environ.get("DEMO_MODE") or not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    if _demo and local_text:
        return {"text": local_text, "lang": lang, "source": "template", "verdict_check": True}

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
        # Gemini output failed verdict check — use local template if available
        fallback = local_text or base
        fallback_lang = lang if local_text else "en"
        return {"text": fallback, "lang": fallback_lang, "source": "template", "verdict_check": False,
                "note": "Model output failed the verdict check; using template.", "meta": meta.__dict__}
    except (ExtractionError, ValueError, Exception) as e:
        # Gemini unavailable — use local template if available, else English
        fallback = local_text or base
        fallback_lang = lang if local_text else "en"
        return {"text": fallback, "lang": fallback_lang, "source": "template", "verdict_check": False,
                "note": f"Translation via Gemini unavailable: {e}"}
