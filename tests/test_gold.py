"""Sanity checks on the gold rule files: they load, every quote is in its source, and a few
hand-worked cases give the expected verdict. These protect the answer key from typos."""
import csv
import json
from pathlib import Path

import pytest

from paatrata_core.evaluator import evaluate
from paatrata_core.ingest import load_file
from paatrata_core.schema import RuleSet
from paatrata_core.testgen import satisfying_profile
from paatrata_core.validator import match_quote

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {r["scheme_id"]: r["file"] for r in csv.DictReader(open(ROOT / "samples/sources/sources.csv", encoding="utf-8"))}
GOLD = {p.stem: RuleSet.model_validate(json.loads(p.read_text(encoding="utf-8"))) for p in (ROOT / "evaluation/gold").glob("*.json")}


@pytest.mark.parametrize("sid", sorted(GOLD))
def test_gold_quotes_are_in_source_and_satisfiable(sid):
    rules = GOLD[sid]
    assert rules.scheme_id == sid and sid in SOURCES
    doc = load_file(ROOT / "samples/sources" / SOURCES[sid])
    for c in rules.conditions:
        assert match_quote(c.citation.quote, doc.pages, c.citation.page)[1] >= 90, c.id
    assert satisfying_profile(rules) is not None


CASES = [
    ("ptwadwc-chandigarh", {"gender": "female", "age_years": 45, "residence_years_in_jurisdiction": 10,
                            "family_annual_income_inr": 90000}, "ELIGIBLE"),
    ("ptwadwc-chandigarh", {"gender": "female", "age_years": 61, "residence_years_in_jurisdiction": 10,
                            "family_annual_income_inr": 90000}, "NOT_ELIGIBLE"),
    ("disabled-pension-chandigarh", {"disability_percent": 39, "residence_years_in_jurisdiction": 5,
                                     "family_annual_income_inr": 100000}, "NOT_ELIGIBLE"),
    ("fsdcwdw-chandigarh", {"applicant_is_legal_guardian": True, "child_age_years": 12, "residence_years_in_jurisdiction": 4,
                            "child_receives_family_pension": False, "child_in_institutional_care": False}, "ELIGIBLE"),
    ("fsdcwdw-chandigarh", {"marital_status": "widowed", "child_age_years": 19, "residence_years_in_jurisdiction": 4,
                            "child_receives_family_pension": False, "child_in_institutional_care": False}, "NOT_ELIGIBLE"),
    ("wpcbocwwb-chandigarh", {"marital_status": "widowed", "board_membership_months": 8, "months_since_spouse_death": 13,
                              "receives_other_pension": False, "covered_under_epf": False}, "NOT_ELIGIBLE"),
    ("icds-chandigarh", {"age_years": 30, "is_pregnant": True}, "ELIGIBLE"),
    ("icds-chandigarh", {"age_years": 16, "gender": "female", "is_domicile_of_jurisdiction": True,
                         "is_pregnant": False, "is_lactating": False}, "ELIGIBLE"),
    ("icds-chandigarh", {"age_years": 30, "is_pregnant": False, "is_lactating": False, "gender": "male"}, "NOT_ELIGIBLE"),
]


@pytest.mark.parametrize("sid,profile,expected", CASES)
def test_hand_worked_cases(sid, profile, expected):
    assert evaluate(GOLD[sid], profile).verdict == expected
