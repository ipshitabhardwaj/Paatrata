"""Evaluation harness.

    python -m evaluation.run_eval                     # replay cached model outputs only (no key needed)
    python -m evaluation.run_eval --live              # call models, fill the cache
    python -m evaluation.run_eval --live --backends gemini,gemma-studio --rag-profiles 8 --rag-runs 3

Measures, per scheme with a gold file in evaluation/gold/ and a source in samples/sources/sources.csv:

* extraction P/R/F1      condition = (field, operator, value) vs gold
* quote verification     share of model conditions whose quote is found in the source
* decision accuracy      verdict agreement with gold on synthetic + boundary profiles
* RAG baseline           decision accuracy, consistency across repeated runs, citation validity

Profiles are SYNTHETIC and gold rules are TEAM-LABELLED: results measure agreement
with our labels on these schemes, not real-world accuracy.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

from paatrata_core.evaluator import evaluate
from paatrata_core.extractors import get_extractor
from paatrata_core.extractors.base import ExtractionError
from paatrata_core.extractors.gemini import DEFAULT_GEMINI_MODEL
from paatrata_core.extractors.gemma import DEFAULT_GEMMA_MODEL, DEFAULT_OLLAMA_MODEL
from paatrata_core.ingest import load_file
from paatrata_core.schema import RuleSet
from paatrata_core.testgen import generate_tests, random_profiles
from paatrata_core.validator import compile_draft, match_quote

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "evaluation" / "gold"
SOURCES = ROOT / "samples" / "sources"
OUT = ROOT / "evaluation" / "results"
DEFAULT_MODELS = {"gemini": DEFAULT_GEMINI_MODEL, "gemma-studio": DEFAULT_GEMMA_MODEL, "ollama": DEFAULT_OLLAMA_MODEL}


def _key(c) -> tuple:
    v = c.value
    if isinstance(v, list):
        v = tuple(sorted(str(x).lower() for x in v))
    elif isinstance(v, bool):
        v = bool(v)
    elif isinstance(v, (int, float)):
        v = float(v)
    else:
        v = str(v).lower()
    return (c.field, c.op, v)


def prf(pred: list, gold: list) -> dict[str, float]:
    p, g = Counter(_key(c) for c in pred), Counter(_key(c) for c in gold)
    tp = sum((p & g).values())
    precision = tp / max(sum(p.values()), 1)
    recall = tp / max(sum(g.values()), 1)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp,
            "n_pred": sum(p.values()), "n_gold": sum(g.values())}


def load_sources() -> dict[str, dict[str, str]]:
    with open(SOURCES / "sources.csv", newline="", encoding="utf-8") as f:
        return {r["scheme_id"]: r for r in csv.DictReader(f)}


def profiles_for(gold: RuleSet, n: int, seed: int) -> list[dict[str, Any]]:
    boundary = [t.profile for t in generate_tests(gold, reference=gold)]
    return boundary + random_profiles([gold], n, seed=seed)


def eval_extraction(backend: str, model: str, live: bool, doc, gold: RuleSet, profiles, review: bool = False) -> dict[str, Any]:
    ex = get_extractor(backend, model) if live else get_extractor(f"cache:{backend}:{model}")
    try:
        res = ex.extract(doc)
    except ExtractionError as e:
        return {"status": "missing", "error": str(e)}
    if res.draft is None:
        return {"status": "invalid_output", "error": res.meta.error}
    rules, issues = compile_draft(res.draft, doc, extractor=f"{backend}:{model}", scheme_id=gold.scheme_id)
    review_codes: list[str] = []
    if review:
        from paatrata_core.review import review_and_apply

        more, _ = review_and_apply(rules, doc, live=live)
        review_codes = [i.code for i in more]
        issues += more
    n_draft = len(res.draft.conditions)
    verified = sum(c.citation.verified for c in rules.conditions)
    agree = sum(evaluate(rules, p).verdict == evaluate(gold, p).verdict for p in profiles)
    return {
        "status": "ok",
        "extraction": prf(rules.conditions, gold.conditions),
        "extraction_before_validation": prf(
            [type("C", (), {"field": c.field, "op": c.op, "value": _safe_val(c)}) for c in res.draft.conditions],
            gold.conditions),
        "quote_verified_rate": verified / max(n_draft, 1),
        "rejected_by_validator": n_draft - len(rules.conditions),
        "ambiguity_flags": sum(1 for i in issues if i.code == "ambiguity"),
        "review": {c: review_codes.count(c) for c in set(review_codes)} if review else None,
        "decision_accuracy": agree / max(len(profiles), 1),
        "n_profiles": len(profiles),
        "latency_ms": res.meta.latency_ms,
        "cache_hit": res.meta.cache_hit,
    }


def _safe_val(dc):
    from paatrata_core.normalize import NormalizationError, normalize_value

    try:
        return normalize_value(dc.field, dc.op, dc.value, dc.value_as_written)
    except (NormalizationError, KeyError):
        return dc.value


def eval_rag(doc, gold: RuleSet, profiles, runs: int, live: bool, temperature: float) -> dict[str, Any]:
    from evaluation.baselines.rag import ask

    correct = total = consistent = cited = answered = 0
    missing = 0
    for p in profiles:
        verdicts = []
        for r in range(runs):
            try:
                ans = ask(gold.scheme_name, doc, p, r, None, temperature, live)
            except ExtractionError:
                missing += 1
                continue
            verdicts.append(ans["verdict"])
            total += 1
            correct += ans["verdict"] == evaluate(gold, p).verdict
            if ans.get("quote"):
                answered += 1
                _, score = match_quote(ans["quote"], doc.pages, None)
                cited += score >= 90
        if len(verdicts) == runs:
            consistent += len(set(verdicts)) == 1
    if total == 0:
        return {"status": "missing", "error": "no cached RAG answers; run with --live"}
    return {"status": "ok", "decision_accuracy": correct / total, "consistency": consistent / max(len(profiles), 1),
            "citation_valid_rate": cited / total, "n_answers": total, "runs_per_profile": runs,
            "temperature": temperature, "missing": missing}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="call models (otherwise replay cache only)")
    ap.add_argument("--backends", default="gemini", help="comma list: gemini,gemma-studio,ollama")
    ap.add_argument("--profiles", type=int, default=300, help="random synthetic profiles per scheme")
    ap.add_argument("--rag-profiles", type=int, default=8, help="profiles per scheme sent to the RAG baseline")
    ap.add_argument("--rag-runs", type=int, default=3)
    ap.add_argument("--rag-temperature", type=float, default=1.0, help="typical chatbot default")
    ap.add_argument("--skip-rag", action="store_true")
    ap.add_argument("--review", action="store_true", help="also run the second-pass Gemini review and count its findings")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--schemes", default="", help="comma list of scheme_ids to evaluate (default: all gold files)")
    a = ap.parse_args(argv)

    sources = load_sources()
    backends = [b.strip() for b in a.backends.split(",") if b.strip()]
    only = {x.strip() for x in a.schemes.split(",") if x.strip()}
    rows: list[dict[str, Any]] = []
    for gp in sorted(GOLD.glob("*.json")):
        gold = RuleSet.model_validate(json.loads(gp.read_text(encoding="utf-8")))
        if only and gold.scheme_id not in only:
            continue
        src = sources.get(gold.scheme_id)
        if not src:
            print(f"skip {gold.scheme_id}: not in sources.csv")
            continue
        doc = load_file(SOURCES / src["file"])
        profiles = profiles_for(gold, a.profiles, a.seed)
        row: dict[str, Any] = {"scheme_id": gold.scheme_id, "scheme_name": gold.scheme_name,
                               "source_type": src.get("source_type"), "systems": {}}
        for b in backends:
            m = DEFAULT_MODELS[b]
            row["systems"][f"paatrata/{b}:{m}"] = eval_extraction(b, m, a.live, doc, gold, profiles, review=a.review)
            print(f"{gold.scheme_id:28} paatrata/{b}: {row['systems'][f'paatrata/{b}:{m}'].get('status')}")
        if not a.skip_rag:
            rag_p = profiles[: a.rag_profiles]
            row["systems"][f"rag/gemini:{DEFAULT_GEMINI_MODEL}"] = eval_rag(doc, gold, rag_p, a.rag_runs, a.live, a.rag_temperature)
            print(f"{gold.scheme_id:28} rag: {row['systems'][f'rag/gemini:{DEFAULT_GEMINI_MODEL}'].get('status')}")
        rows.append(row)

    summary = summarise(rows)
    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_schemes": len(rows),
        "notes": [
            "Profiles are synthetic (random + boundary), not real applicants.",
            "Gold rules were hand-labelled by the team; metrics measure agreement with those labels.",
            "Paatrata's verdicts are deterministic given approved rules (consistency = 1.0 by construction).",
            "Schemes whose only source is a portal summary are marked source_type=secondary.",
        ],
        "summary": summary,
        "schemes": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "latest.md").write_text(to_markdown(result), encoding="utf-8")
    print(to_markdown(result))
    return 0


def summarise(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    agg: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        for sysname, m in r["systems"].items():
            if m.get("status") != "ok":
                continue
            a = agg.setdefault(sysname, {})
            for k in ("decision_accuracy", "quote_verified_rate", "consistency", "citation_valid_rate"):
                if k in m:
                    a.setdefault(k, []).append(m[k])
            if "extraction" in m:
                a.setdefault("extraction_f1", []).append(m["extraction"]["f1"])
                a.setdefault("extraction_f1_before_validation", []).append(m["extraction_before_validation"]["f1"])
    return {s: {k: round(sum(v) / len(v), 3) for k, v in d.items()} | {"n_schemes": max(len(v) for v in d.values())}
            for s, d in agg.items()}


def to_markdown(res: dict[str, Any]) -> str:
    cols = ["extraction_f1", "extraction_f1_before_validation", "quote_verified_rate", "decision_accuracy",
            "consistency", "citation_valid_rate", "n_schemes"]
    lines = [f"# Evaluation results ({res['generated_at']})", "",
             f"Schemes evaluated: {res['n_schemes']}", "",
             "| system | " + " | ".join(cols) + " |", "|" + "---|" * (len(cols) + 1)]
    for s, m in res["summary"].items():
        vals = [m.get(c, "1.0 (deterministic)" if c == "consistency" and s.startswith("paatrata") else "—") for c in cols]
        lines.append(f"| {s} | " + " | ".join(str(v) for v in vals) + " |")
    lines += ["", "Notes:"] + [f"- {n}" for n in res["notes"]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    os.chdir(ROOT)
    raise SystemExit(main())
