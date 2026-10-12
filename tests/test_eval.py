import json
from pathlib import Path

from paatrata_core.extractors.base import CallMeta, Extractor

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/oapc_draft_handmade.json").read_text(encoding="utf-8"))
FIXTURE.pop("_note")


class Fake(Extractor):
    backend = "fake"

    def _call(self, doc):
        return json.dumps(FIXTURE), CallMeta(backend="fake", model="fixture")


def test_full_eval_pipeline_with_fakes(monkeypatch, tmp_path):
    import evaluation.run_eval as ev
    import evaluation.baselines.rag as rag

    monkeypatch.setattr(ev, "get_extractor", lambda *a, **k: Fake("fixture", cache_dir=tmp_path))
    monkeypatch.setattr(ev, "OUT", tmp_path / "results")

    calls = {"n": 0}

    def fake_ask(scheme_name, doc, profile, run, model, temperature, live):
        calls["n"] += 1
        # a flaky chatbot: alternates answers and cites nothing on odd runs
        return {"verdict": "ELIGIBLE" if run % 2 == 0 else "NOT_ELIGIBLE",
                "quote": "The applicant should be 60 years of age or above." if run % 2 == 0 else ""}

    monkeypatch.setattr(rag, "ask", fake_ask)
    assert ev.main(["--schemes", "oapc-chandigarh", "--profiles", "40", "--rag-profiles", "4", "--rag-runs", "2"]) == 0
    res = json.loads((tmp_path / "results" / "latest.json").read_text(encoding="utf-8"))
    s = res["summary"]
    pa = next(v for k, v in s.items() if k.startswith("paatrata"))
    rg = next(v for k, v in s.items() if k.startswith("rag"))
    assert pa["extraction_f1"] == 1.0
    assert pa["extraction_f1_before_validation"] < 1.0   # the hallucinated condition counted before validation
    assert pa["decision_accuracy"] == 1.0
    assert rg["consistency"] == 0.0 and calls["n"] == 8
    assert "| system |" in (tmp_path / "results" / "latest.md").read_text(encoding="utf-8")
