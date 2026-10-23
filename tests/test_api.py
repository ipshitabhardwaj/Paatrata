import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    import importlib

    import server.db as dbmod
    importlib.reload(dbmod)
    import server.seed as seedmod
    importlib.reload(seedmod)
    import server.app as appmod
    importlib.reload(appmod)
    monkeypatch.setattr(appmod, "UPLOAD_DIR", tmp_path / "uploads")

    # Replace the Gemini extractor with the hand-written fixture (no network, no key).
    from paatrata_core.extractors.base import CallMeta, Extractor

    fixture = json.loads((ROOT / "tests/fixtures/oapc_draft_handmade.json").read_text(encoding="utf-8"))
    fixture.pop("_note")

    class Fake(Extractor):
        backend = "fake"

        def _call(self, doc):
            return json.dumps(fixture), CallMeta(backend="fake", model="fixture")

    monkeypatch.setattr(appmod, "get_extractor", lambda b, m=None: Fake("fixture", cache_dir=tmp_path / "cache"))
    with TestClient(appmod.app) as c:
        yield c


H = {"X-Admin-Token": "dev-token"}


def test_seeded_gold_check_works(client):
    schemes = {s["id"]: s for s in client.get("/api/schemes").json()}
    assert len(schemes) >= 6 and schemes["oapc-chandigarh"]["approved_version"] == 1
    r = client.post("/api/check", json={"scheme_id": "oapc-chandigarh",
                                        "profile": {"age_years": 64, "family_annual_income_inr": 162000,
                                                    "residence_years_in_jurisdiction": 5, "is_domicile_of_jurisdiction": True}}).json()
    assert r["verdict"]["verdict"] == "NOT_ELIGIBLE"
    assert "NOT ELIGIBLE" in r["explanation"]["text"]


def test_compile_review_approve_flow(client):
    src = (ROOT / "samples/sources/oapc_chandigarh.txt").read_bytes()
    assert client.post("/api/compile", files={"file": ("oapc.txt", src)}, data={"scheme_id": "oapc-chandigarh"}).status_code == 401
    r = client.post("/api/compile", files={"file": ("oapc.txt", src)},
                    data={"scheme_id": "oapc-chandigarh", "backend": "gemini"}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    vid = body["version_id"]
    assert len(body["rules"]["conditions"]) == 4
    assert any(i["code"] == "quote_not_found" for i in body["issues"])

    # ambiguity blocks approval until resolved
    assert client.post(f"/api/versions/{vid}/approve", headers=H).status_code == 409
    assert client.post(f"/api/versions/{vid}/conditions/c1/resolve", headers=H,
                       json={"resolution": "Family = applicant + spouse + dependants (dept. clarification)"}).status_code == 200
    tests = client.get(f"/api/versions/{vid}/tests").json()
    assert tests["gold_passed"] == tests["gold_total"]
    assert client.post(f"/api/versions/{vid}/approve", headers=H).status_code == 200
    r = client.post("/api/check", json={"scheme_id": "oapc-chandigarh", "profile": {"age_years": 64}}).json()
    assert r["version"] == 2 and r["verdict"]["verdict"] == "NEEDS_INFO"
    assert client.get("/api/llm-calls").json()[0]["backend"] == "fake"


def test_form_fields(client):
    fields = client.get("/api/schemes/oapc-chandigarh/form").json()
    assert {f["name"] for f in fields} == {"age_years", "family_annual_income_inr",
                                           "residence_years_in_jurisdiction", "is_domicile_of_jurisdiction"}


def test_check_all_schemes(client):
    r = client.post("/api/check/all", json={"age_years": 64, "family_annual_income_inr": 120000,
                                             "residence_years_in_jurisdiction": 5, "is_domicile_of_jurisdiction": True})
    assert r.status_code == 200
    data = r.json()
    assert data["total_schemes"] >= 1
    assert any(s["scheme_id"] == "oapc-chandigarh" for s in data["eligible"])


def test_batch_check(client):
    profiles = [
        {"age_years": 64, "family_annual_income_inr": 120000, "residence_years_in_jurisdiction": 5, "is_domicile_of_jurisdiction": True},
        {"age_years": 50, "family_annual_income_inr": 200000},
    ]
    r = client.post("/api/check/batch", json={"scheme_id": "oapc-chandigarh", "profiles": profiles})
    assert r.status_code == 200
    data = r.json()
    assert data["summary"]["total"] == 2
    assert data["results"][0]["verdict"] == "ELIGIBLE"
    assert data["results"][1]["verdict"] == "NOT_ELIGIBLE"


def test_batch_check_limit(client):
    profiles = [{"age_years": 60}] * 51
    r = client.post("/api/check/batch", json={"scheme_id": "oapc-chandigarh", "profiles": profiles})
    assert r.status_code == 400


def test_confidence_report(client):
    r = client.get("/api/confidence/oapc-chandigarh")
    assert r.status_code == 200
    data = r.json()
    assert data["n_conditions"] == 4
    assert len(data["conditions"]) == 4
    assert "overall_confidence" in data
    assert "all_quotes_verified" in data


def test_audit_trail(client):
    r = client.get("/api/audit/oapc-chandigarh")
    assert r.status_code == 200
    data = r.json()
    assert len(data["history"]) >= 1
    assert data["history"][0]["status"] == "approved"


def test_diff_versions(client):
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "samples/sources/oapc_chandigarh.txt").read_bytes()
    r = client.post("/api/compile", files={"file": ("oapc.txt", src)},
                    data={"scheme_id": "oapc-chandigarh", "backend": "gemini"}, headers=H)
    vid2 = r.json()["version_id"]
    r = client.get(f"/api/versions/1/diff/{vid2}")
    assert r.status_code == 200
    data = r.json()
    assert "added" in data and "removed" in data and "changed" in data


def test_overview(client):
    o = client.get("/api/overview").json()
    ids = {s["id"]: s for s in o["schemes"]}
    assert ids["oapc-chandigarh"]["conditions"] == 4 and ids["icds-chandigarh"]["any_groups"] == 1
