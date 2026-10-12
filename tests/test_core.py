import json
from pathlib import Path

import pytest

from paatrata_core.evaluator import evaluate
from paatrata_core.ingest import load_file, load_text
from paatrata_core.normalize import NormalizationError, parse_number
from paatrata_core.schema import RuleSet, SchemeDraft
from paatrata_core.testgen import generate_tests, run_tests, satisfying_profile
from paatrata_core.validator import compile_draft

ROOT = Path(__file__).resolve().parents[1]
GOLD = RuleSet.model_validate(json.loads((ROOT / "evaluation/gold/oapc-chandigarh.json").read_text(encoding="utf-8")))
SOURCE = ROOT / "samples/sources/oapc_chandigarh.txt"


def draft_fixture() -> SchemeDraft:
    data = json.loads((ROOT / "tests/fixtures/oapc_draft_handmade.json").read_text(encoding="utf-8"))
    data.pop("_note")
    return SchemeDraft.model_validate(data)


# ---------------------------------------------------------------- normalise
@pytest.mark.parametrize("text,expected", [
    ("1,50,000", 150000), ("Rs. 1.5 lakh", 150000), ("₹2 lakhs", 200000), ("150000", 150000),
    ("one lakh fifty thousand", 150000), ("sixty", 60), ("60 years", 60), ("2.5 crore", 25_000_000),
    ("Rs 15k", 15000), ("Rs. 1,000/- per month", 1000),
])
def test_parse_number(text, expected):
    assert parse_number(text) == expected


def test_parse_number_rejects_garbage():
    with pytest.raises(NormalizationError):
        parse_number("not stated")


# ---------------------------------------------------------------- evaluator
BASE = {"age_years": 64, "family_annual_income_inr": 120000, "residence_years_in_jurisdiction": 5,
        "is_domicile_of_jurisdiction": True}


def test_eligible():
    assert evaluate(GOLD, BASE).verdict == "ELIGIBLE"


def test_income_over_limit_is_not_eligible_and_cited():
    v = evaluate(GOLD, {**BASE, "family_annual_income_inr": 162000})
    assert v.verdict == "NOT_ELIGIBLE"
    assert v.failed_conditions == ["g1"]
    assert "1,50,000" in v.results[0].citation.quote


@pytest.mark.parametrize("age,verdict", [(59, "NOT_ELIGIBLE"), (60, "ELIGIBLE")])
def test_age_boundary(age, verdict):
    assert evaluate(GOLD, {**BASE, "age_years": age}).verdict == verdict


@pytest.mark.parametrize("years,verdict", [(3, "NOT_ELIGIBLE"), (3.1, "ELIGIBLE")])
def test_residence_is_exclusive(years, verdict):
    assert evaluate(GOLD, {**BASE, "residence_years_in_jurisdiction": years}).verdict == verdict


def test_missing_field_needs_info_not_guess():
    p = dict(BASE)
    del p["residence_years_in_jurisdiction"]
    v = evaluate(GOLD, p)
    assert v.verdict == "NEEDS_INFO"
    assert v.missing_fields == ["residence_years_in_jurisdiction"]


def test_known_failure_beats_unknown():
    # Kleene ALL: FALSE dominates UNKNOWN
    v = evaluate(GOLD, {"age_years": 40})
    assert v.verdict == "NOT_ELIGIBLE"


FICTIONAL = RuleSet.model_validate({
    "scheme_id": "fictional-test", "scheme_name": "FICTIONAL test scheme",
    "groups": [{"id": "root", "logic": "ALL", "parent": None},
               {"id": "age_or_widow", "logic": "ANY", "parent": "root"},
               {"id": "widow_branch", "logic": "ALL", "parent": "age_or_widow"}],
    "conditions": [
        {"id": "a", "group": "root", "field": "family_annual_income_inr", "op": "<=", "value": 100000,
         "citation": {"page": 1, "quote": "x"}},
        {"id": "b", "group": "age_or_widow", "field": "age_years", "op": ">=", "value": 60, "citation": {"page": 1, "quote": "x"}},
        {"id": "c", "group": "widow_branch", "field": "age_years", "op": ">=", "value": 50, "citation": {"page": 1, "quote": "x"}},
        {"id": "d", "group": "widow_branch", "field": "marital_status", "op": "==", "value": "widowed",
         "citation": {"page": 1, "quote": "x"}},
    ],
})


@pytest.mark.parametrize("profile,verdict", [
    ({"family_annual_income_inr": 50000, "age_years": 61}, "ELIGIBLE"),
    ({"family_annual_income_inr": 50000, "age_years": 52, "marital_status": "widowed"}, "ELIGIBLE"),
    ({"family_annual_income_inr": 50000, "age_years": 52, "marital_status": "married"}, "NOT_ELIGIBLE"),
    ({"family_annual_income_inr": 50000, "age_years": 52}, "NEEDS_INFO"),
    ({"family_annual_income_inr": 500000, "age_years": 70}, "NOT_ELIGIBLE"),
])
def test_nested_any_all(profile, verdict):
    assert evaluate(FICTIONAL, profile).verdict == verdict


# ---------------------------------------------------------------- validator
def test_compile_draft_rejects_unsupported_quote_and_flags_ambiguity():
    doc = load_file(SOURCE)
    rules, issues = compile_draft(draft_fixture(), doc, extractor="fixture", scheme_id="oapc-chandigarh")
    codes = {(i.code, i.condition_id) for i in issues}
    assert ("quote_not_found", "c5") in codes          # hallucinated condition rejected
    assert ("ambiguity", "c1") in codes                # officer question surfaced
    assert ("low_confidence", "c5") not in codes       # rejected before confidence check
    assert [c.id for c in rules.conditions] == ["c1", "c2", "c3", "c4"]
    assert all(c.citation.verified for c in rules.conditions)
    assert rules.conditions[0].value == 150000.0


def test_compiled_rules_agree_with_gold_on_boundaries():
    doc = load_file(SOURCE)
    rules, _ = compile_draft(draft_fixture(), doc, extractor="fixture", scheme_id="oapc-chandigarh")
    results = run_tests(rules, generate_tests(GOLD, reference=GOLD))
    assert all(r.passed for r in results), [r for r in results if not r.passed]


def test_wrong_operator_is_caught_by_gold_boundary_tests():
    doc = load_file(SOURCE)
    d = draft_fixture()
    d.conditions[2].op = ">="  # model misread "more than 3 years" as inclusive
    rules, _ = compile_draft(d, doc, extractor="fixture")
    results = run_tests(rules, generate_tests(GOLD, reference=GOLD))
    assert any(not r.passed for r in results)


def test_bad_field_value_rejected():
    doc = load_text("Applicants must be 60 years or above.")
    d = SchemeDraft.model_validate({
        "scheme_name": "x", "groups": [{"id": "root", "logic": "ALL", "parent": None}],
        "conditions": [{"id": "c1", "group": "root", "field": "age_years", "op": ">=", "value": "sixty-ish",
                        "value_as_written": "unclear", "quote": "Applicants must be 60 years or above.",
                        "page": 1, "confidence": 0.9}],
    })
    rules, issues = compile_draft(d, doc, extractor="t")
    assert not rules.conditions
    assert {"bad_value", "no_conditions"} <= {i.code for i in issues}


def test_contradiction_detected():
    doc = load_text("Age 60 or above. Age not more than 50.")
    d = SchemeDraft.model_validate({
        "scheme_name": "x", "groups": [{"id": "root", "logic": "ALL", "parent": None}],
        "conditions": [
            {"id": "c1", "group": "root", "field": "age_years", "op": ">=", "value": "60", "value_as_written": "60",
             "quote": "Age 60 or above.", "page": 1, "confidence": 0.9},
            {"id": "c2", "group": "root", "field": "age_years", "op": "<=", "value": "50", "value_as_written": "50",
             "quote": "Age not more than 50.", "page": 1, "confidence": 0.9},
        ],
    })
    _, issues = compile_draft(d, doc, extractor="t")
    assert "contradiction" in {i.code for i in issues}


def test_two_roots_get_wrapped():
    doc = load_text("Age 60 or above.")
    d = SchemeDraft.model_validate({
        "scheme_name": "x",
        "groups": [{"id": "a", "logic": "ALL", "parent": None}, {"id": "b", "logic": "ALL", "parent": None}],
        "conditions": [{"id": "c1", "group": "a", "field": "age_years", "op": ">=", "value": "60",
                        "value_as_written": "60", "quote": "Age 60 or above.", "page": 1, "confidence": 0.9}],
    })
    rules, issues = compile_draft(d, doc, extractor="t")
    assert evaluate(rules, {"age_years": 61}).verdict == "ELIGIBLE"
    assert "no_single_root" in {i.code for i in issues}


# ---------------------------------------------------------------- testgen
def test_satisfying_profile_for_nested_rules():
    p = satisfying_profile(FICTIONAL)
    assert p is not None and evaluate(FICTIONAL, p).verdict == "ELIGIBLE"


def test_generated_tests_cover_boundaries():
    tests = generate_tests(GOLD)
    descs = " | ".join(t.description for t in tests)
    assert "149999" not in descs  # income boundary is +1 over the limit, not -1
    assert any(t.profile.get("family_annual_income_inr") == 150001 and t.expected == "NOT_ELIGIBLE" for t in tests)
    assert any(t.profile.get("age_years") == 59 and t.expected == "NOT_ELIGIBLE" for t in tests)
    assert any(t.expected == "NEEDS_INFO" for t in tests)
