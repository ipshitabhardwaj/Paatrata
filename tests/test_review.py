import json
from pathlib import Path

from paatrata_core.extractors.base import CallMeta, friendly_error
from paatrata_core.ingest import load_file
from paatrata_core.registry import lookup
from paatrata_core.schema import RuleSet

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "samples/sources/oapc_chandigarh.txt"


def gold():
    return RuleSet.model_validate(json.loads((ROOT / "evaluation/gold/oapc-chandigarh.json").read_text(encoding="utf-8")))


def test_review_findings_are_grounded_and_attached(monkeypatch, tmp_path):
    monkeypatch.setenv("PAATRATA_CACHE_DIR", str(tmp_path))
    import paatrata_core.extractors.gemini as g
    from paatrata_core import review

    findings = {"findings": [
        {"kind": "ambiguity", "condition_id": "g1", "quote": "family annual income of the applicant",
         "message": "Does 'family' include adult children living separately?"},
        {"kind": "misread", "condition_id": "g2", "quote": "applicants must be over 70",  # not in source -> dropped
         "message": "age should be > 70"},
        {"kind": "missing", "condition_id": None, "quote": "Only applicants from Chandigarh are eligible.",
         "message": "domicile requirement"},
    ]}
    calls = {"n": 0}

    def fake(prompt, schema, model=None, temperature=0.0):
        calls["n"] += 1
        return json.dumps(findings), CallMeta(backend="gemini", model="fake")

    monkeypatch.setattr(g, "generate_structured", fake)
    rules, doc = gold(), load_file(SRC)
    issues, meta = review.review_and_apply(rules, doc, model="fake")
    codes = [i.code for i in issues]
    assert codes.count("ambiguity") == 1 and "review_unverified" in codes and "review_missing" in codes
    g1 = next(c for c in rules.conditions if c.id == "g1")
    assert "adult children" in g1.ambiguity and g1.confidence < 0.8
    assert next(c for c in rules.conditions if c.id == "g2").ambiguity is None   # ungrounded finding ignored
    # second call is served from cache
    review.review_and_apply(gold(), doc, model="fake")
    assert calls["n"] == 1


def test_review_without_key_is_skipped_not_fatal(monkeypatch, tmp_path):
    monkeypatch.setenv("PAATRATA_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from paatrata_core.review import review_and_apply

    issues, _ = review_and_apply(gold(), load_file(SRC))
    assert [i.code for i in issues] == ["review_skipped"]


def test_friendly_errors():
    assert "API key" in friendly_error(Exception("400 INVALID_ARGUMENT API_KEY_INVALID"), "m")
    assert "not found" in friendly_error(Exception("404 NOT_FOUND models/x is not found"), "x")
    assert "quota" in friendly_error(Exception("429 RESOURCE_EXHAUSTED"), "m")


def test_registry_lookup():
    row = lookup(r"C:\\somewhere\\OAPC_Chandigarh.txt", ROOT / "samples/sources/sources.csv")
    assert row and row["scheme_id"] == "oapc-chandigarh"
    assert lookup("unknown.pdf", ROOT / "samples/sources/sources.csv") is None
