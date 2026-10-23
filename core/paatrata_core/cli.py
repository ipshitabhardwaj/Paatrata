"""Command line: `paatrata compile|check|tests`.

    paatrata compile samples/sources/oapc_chandigarh.txt --backend gemini -o rules.json
    paatrata check rules.json --profile '{"age_years": 64, "family_annual_income_inr": 162000}'
    paatrata tests rules.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evaluator import evaluate
from .explain import template_explanation
from .extractors import get_extractor
from .ingest import load_file
from .schema import RuleSet
from .testgen import generate_tests, run_tests
from .validator import compile_draft


def _load_dotenv():
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def cmd_compile(a) -> int:
    from .registry import lookup

    row = lookup(a.source, Path(a.source).parent / "sources.csv")
    scheme_id = a.scheme_id or (row or {}).get("scheme_id")
    if row and not a.scheme_id:
        print(f"scheme id from sources.csv: {scheme_id}", file=sys.stderr)
    doc = load_file(a.source, url=(row or {}).get("url"), is_primary_source=(row or {}).get("source_type") == "primary")
    try:
        res = get_extractor(a.backend, a.model).extract(doc)
    except Exception as e:  # ExtractionError carries a friendly message
        print(f"Extraction failed: {e}", file=sys.stderr)
        return 2
    print(f"[{res.meta.backend}:{res.meta.model}] cache_hit={res.meta.cache_hit} latency={res.meta.latency_ms}ms",
          file=sys.stderr)
    if res.draft is None:
        print(f"Extraction failed: {res.meta.error}\n{res.raw_text[:2000]}", file=sys.stderr)
        return 2
    rules, issues = compile_draft(res.draft, doc, extractor=f"{res.meta.backend}:{res.meta.model}", scheme_id=scheme_id)
    if a.review:
        from .review import review_and_apply

        more, meta = review_and_apply(rules, doc)
        issues += more
        if meta:
            print(f"[review {meta.model}] cache_hit={meta.cache_hit} latency={meta.latency_ms}ms", file=sys.stderr)
    out = {"rules": rules.model_dump(), "issues": [i.model_dump() for i in issues]}
    text = json.dumps(out, indent=2, ensure_ascii=False)
    if a.output:
        Path(a.output).write_text(text, encoding="utf-8")
        print(f"wrote {a.output}: {len(rules.conditions)} conditions, {len(issues)} issues", file=sys.stderr)
    else:
        print(text)
    for i in issues:
        print(f"  {i.level.upper():7} {i.code:18} {i.condition_id or '':4} {i.message}", file=sys.stderr)
    return 0


def _read_rules(path: str) -> RuleSet:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return RuleSet.model_validate(data.get("rules", data))


def cmd_check(a) -> int:
    rules = _read_rules(a.rules)
    profile = json.loads(a.profile)
    v = evaluate(rules, profile)
    print(template_explanation(v, rules.scheme_name) if not a.json else v.model_dump_json(indent=2))
    return 0


def cmd_tests(a) -> int:
    rules = _read_rules(a.rules)
    ref = _read_rules(a.reference) if a.reference else None
    results = run_tests(rules, generate_tests(rules, reference=ref))
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        print(f"{mark}  expected={r.test.expected:12} actual={r.actual:12} {r.test.description}")
    failed = sum(not r.passed for r in results)
    print(f"\n{len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


def main(argv=None) -> int:
    _load_dotenv()
    p = argparse.ArgumentParser(prog="paatrata")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile", help="extract + validate rules from a source document")
    c.add_argument("source")
    c.add_argument("--backend", default="gemini", help="gemini | groq | gemma-studio | ollama | cache:<backend>:<model>")
    c.add_argument("--model", default=None)
    c.add_argument("--scheme-id", default=None)
    c.add_argument("-o", "--output", default=None)
    c.add_argument("--no-review", dest="review", action="store_false",
                   help="skip the second-pass Gemini review (on by default)")
    c.set_defaults(fn=cmd_compile)
    k = sub.add_parser("check", help="evaluate a profile against rules")
    k.add_argument("rules")
    k.add_argument("--profile", required=True, help="JSON object")
    k.add_argument("--json", action="store_true")
    k.set_defaults(fn=cmd_check)
    t = sub.add_parser("tests", help="generate + run boundary tests")
    t.add_argument("rules")
    t.add_argument("--reference", default=None, help="gold rules to take expected verdicts from")
    t.set_defaults(fn=cmd_tests)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
