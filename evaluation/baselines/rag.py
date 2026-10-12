"""Baseline: a plain retrieval-augmented eligibility chatbot.

Same documents, same Gemini model. The only difference from Paatrata is that it
asks the model at query time instead of compiling rules once. Retrieval is TF-IDF
over ~600-character chunks (deliberately simple and transparent).

Responses are cached under evaluation/cache/rag/ so the evaluation can be re-run
for free; a cache entry is keyed by (model, temperature, prompt hash, run index).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from paatrata_core.extractors.base import ExtractionError, parse_json_text
from paatrata_core.ingest import SourceDoc
from paatrata_core.vocabulary import FIELDS

CACHE = Path("evaluation/cache/rag")
VERDICTS = {"ELIGIBLE", "NOT_ELIGIBLE", "NEEDS_INFO"}


def chunks(doc: SourceDoc, size: int = 600, overlap: int = 120) -> list[tuple[int, str]]:
    out = []
    for pno, text in enumerate(doc.pages, start=1):
        t = " ".join(text.split())
        i = 0
        while i < len(t):
            out.append((pno, t[i : i + size]))
            i += size - overlap
    return out or [(1, "")]


def retrieve(doc: SourceDoc, query: str, k: int = 4) -> list[tuple[int, str]]:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    cs = chunks(doc)
    texts = [c[1] for c in cs]
    vec = TfidfVectorizer(ngram_range=(1, 2)).fit(texts + [query])
    sims = cosine_similarity(vec.transform([query]), vec.transform(texts))[0]
    order = sims.argsort()[::-1][:k]
    return [cs[i] for i in sorted(order)]


def describe_profile(profile: dict[str, Any]) -> str:
    lines = []
    for f, v in profile.items():
        spec = FIELDS.get(f)
        lines.append(f"- {spec.description if spec else f}: {v}{' ' + spec.unit if spec and spec.unit else ''}")
    return "\n".join(lines) or "- (no details given)"


def build_prompt(scheme_name: str, ctx: list[tuple[int, str]], profile: dict[str, Any]) -> str:
    context = "\n\n".join(f"[page {p}] {t}" for p, t in ctx)
    return (
        f"You are a helpful assistant for the scheme '{scheme_name}'. Using ONLY the context below, "
        "decide if this applicant is eligible.\n\n"
        f"CONTEXT:\n{context}\n\nAPPLICANT:\n{describe_profile(profile)}\n\n"
        'Return JSON: {"verdict": "ELIGIBLE" | "NOT_ELIGIBLE" | "NEEDS_INFO", '
        '"reason": "<one or two sentences>", "quote": "<verbatim supporting text from the context>"}'
    )


def ask(scheme_name: str, doc: SourceDoc, profile: dict[str, Any], run: int, model: str | None,
        temperature: float, live: bool) -> dict[str, Any]:
    from paatrata_core.extractors.gemini import DEFAULT_GEMINI_MODEL, generate_json

    model = model or DEFAULT_GEMINI_MODEL
    query = f"{scheme_name} eligibility conditions " + " ".join(profile.keys()).replace("_", " ")
    prompt = build_prompt(scheme_name, retrieve(doc, query), profile)
    key = hashlib.sha256(json.dumps([model, temperature, prompt, run]).encode()).hexdigest()[:24]
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not live:
        raise ExtractionError("RAG response not cached; run with --live")
    raw, meta = generate_json(prompt, model=model, temperature=temperature)
    try:
        data = parse_json_text(raw)
    except ValueError:
        data = {"verdict": "INVALID", "reason": raw[:300], "quote": ""}
    if data.get("verdict") not in VERDICTS:
        data["verdict"] = "INVALID"
    rec = {"verdict": data.get("verdict"), "reason": data.get("reason", ""), "quote": data.get("quote", ""),
           "model": model, "temperature": temperature, "run": run, "latency_ms": meta.latency_ms}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec
