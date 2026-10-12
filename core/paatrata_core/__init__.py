"""paatrata_core: compile scheme documents into cited, tested eligibility rules.

    from paatrata_core import load_file, get_extractor, compile_draft, evaluate

    doc = load_file("samples/sources/oapc_chandigarh.txt")
    res = get_extractor("gemini").extract(doc)
    rules, issues = compile_draft(res.draft, doc, extractor="gemini")
    verdict = evaluate(rules, {"age_years": 64, "family_annual_income_inr": 162000})
"""
from .evaluator import evaluate, fields_used
from .extractors import get_extractor
from .ingest import SourceDoc, load_bytes, load_file, load_text
from .schema import RuleSet, SchemeDraft, Verdict
from .testgen import generate_tests, run_tests
from .validator import compile_draft

__version__ = "0.1.0"

__all__ = [
    "evaluate", "fields_used", "get_extractor", "SourceDoc", "load_bytes", "load_file", "load_text",
    "RuleSet", "SchemeDraft", "Verdict", "generate_tests", "run_tests", "compile_draft",
]
