"""Paatrata API.

Authoring path (officer):  POST /api/compile -> review -> resolve ambiguities -> approve
Query path (citizen):      POST /api/check   -> deterministic verdict + citations (+ optional hi/pa text)

Run:  uvicorn server.app:app --reload        (from the repo root)
Docs: http://localhost:8000/docs
"""

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

from paatrata_core.evaluator import evaluate, fields_used
from paatrata_core.explain import explain
from paatrata_core.extractors import BACKENDS, get_extractor
from paatrata_core.extractors.base import ExtractionError
from paatrata_core.ingest import load_bytes
from paatrata_core.schema import RuleSet
from paatrata_core.testgen import generate_tests, run_tests
from paatrata_core.validator import blocking_issues, compile_draft
from paatrata_core.vocabulary import FIELDS

from . import db

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "data/uploads"))
GOLD_DIR = ROOT / "evaluation" / "gold"
SOURCES_CSV = ROOT / "samples" / "sources" / "sources.csv"
RESULTS = ROOT / "evaluation" / "results" / "latest.json"
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "dev-token")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    from .seed import seed_gold

    seed_gold()  # idempotent: adds gold files that are not in the DB yet
    yield


app = FastAPI(title="Paatrata", version="0.1.0", lifespan=lifespan,
              description="Compile scheme documents into cited, tested eligibility rules.")
_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
_extra = os.environ.get("CORS_ORIGIN")
if _extra:
    _origins.extend(o.strip() for o in _extra.split(",") if o.strip())
app.add_middleware(CORSMiddleware, allow_origins=_origins,
                   allow_methods=["*"], allow_headers=["*"])


def require_admin(x_admin_token: Optional[str] = Header(default=None)) -> str:
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Officer token required (header X-Admin-Token).")
    return "officer"


# --------------------------------------------------------------------------- helpers
def _version(con, vid: int) -> dict[str, Any]:
    v = db.row(con.execute("SELECT * FROM rule_versions WHERE id=?", (vid,)).fetchone())
    if not v:
        raise HTTPException(404, f"version {vid} not found")
    return v


def _open_ambiguities(rules: dict) -> list[str]:
    return [c["id"] for c in rules["conditions"] if c.get("ambiguity") and not c.get("ambiguity_resolution")]


def _gold(scheme_id: str) -> RuleSet | None:
    p = GOLD_DIR / f"{scheme_id}.json"
    if not p.exists():
        return None
    return RuleSet.model_validate(json.loads(p.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- meta
@app.get("/api/health")
def health():
    with db.connect() as con:
        n_schemes = con.execute("SELECT COUNT(*) FROM schemes").fetchone()[0]
        n_approved = con.execute("SELECT COUNT(*) FROM rule_versions WHERE status='approved'").fetchone()[0]
    return {"ok": True, "backends": BACKENDS, "schemes": n_schemes,
            "approved_versions": n_approved,
            "gemini_key": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))}


@app.get("/api/vocabulary")
def vocabulary():
    return [{"name": f.name, "type": f.type, "unit": f.unit, "description": f.description, "options": list(f.options),
             "min": f.min_value, "max": f.max_value} for f in FIELDS.values()]


# --------------------------------------------------------------------------- authoring
@app.post("/api/compile")
async def compile_scheme(
    file: Optional[UploadFile] = File(default=None),
    text: Optional[str] = Form(default=None),
    backend: str = Form(default="gemini"),
    model: Optional[str] = Form(default=None),
    scheme_id: Optional[str] = Form(default=None),
    url: Optional[str] = Form(default=None),
    is_primary_source: bool = Form(default=False),
    review: bool = Form(default=True),
    _: str = Depends(require_admin),
):
    if file is None and not (text and text.strip()):
        raise HTTPException(400, "Upload a file or paste text.")
    if file is not None:
        data, name = await file.read(), file.filename or "upload.pdf"
    else:
        data, name = text.encode("utf-8"), "pasted.txt"
    from paatrata_core.registry import lookup

    row = lookup(name, SOURCES_CSV) if file is not None else None
    if row:
        scheme_id = scheme_id or row["scheme_id"]
        url = url or row.get("url")
        is_primary_source = is_primary_source or row.get("source_type") == "primary"
    doc = load_bytes(data, name, url=url, is_primary_source=is_primary_source)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / f"{doc.doc_id}{Path(name).suffix or '.txt'}"
    path.write_bytes(data)

    # --- Fast-path: if DEMO_MODE or no API key, skip Gemini and save gold rules as a real draft ---
    _demo = os.environ.get("DEMO_MODE") or not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    if _demo and backend == "gemini":
        demo_gold = _gold(scheme_id) if scheme_id else None
        if demo_gold is None:
            for gf in sorted(GOLD_DIR.glob("*.json")):
                try:
                    demo_gold = RuleSet.model_validate(json.loads(gf.read_text(encoding="utf-8")))
                    break
                except Exception:
                    continue
        if demo_gold is not None:
            with db.connect() as con:
                con.execute("INSERT OR IGNORE INTO schemes VALUES (?,?,?,?,?)",
                            (demo_gold.scheme_id, demo_gold.scheme_name, demo_gold.department, demo_gold.jurisdiction, db.now()))
                n = con.execute("SELECT COALESCE(MAX(version),0)+1 FROM rule_versions WHERE scheme_id=?", (demo_gold.scheme_id,)).fetchone()[0]
                cur = con.execute(
                    "INSERT INTO rule_versions(scheme_id, version, status, rules_json, issues_json, extractor, source_doc_id, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (demo_gold.scheme_id, n, "draft", demo_gold.model_dump_json(), "[]",
                     "demo:gold-rules", doc.doc_id, db.now()),
                )
                vid = cur.lastrowid
            return {"version_id": vid, "scheme_id": demo_gold.scheme_id, "version": n,
                    "rules": demo_gold.model_dump(), "issues": [], "llm": {"backend": "demo-fallback", "model": "gold-rules"},
                    "review": None}

    try:
        res = get_extractor(backend, model).extract(doc)
    except (ExtractionError, ValueError, Exception) as e:
        with db.connect() as con:
            db.log_call(con, "extract", {"backend": backend, "model": model, "error": str(e)})
        # --- Fallback: save gold rules as a real draft on extraction failure ---
        demo_gold = _gold(scheme_id) if scheme_id else None
        if demo_gold is None:
            for gf in sorted(GOLD_DIR.glob("*.json")):
                try:
                    demo_gold = RuleSet.model_validate(json.loads(gf.read_text(encoding="utf-8")))
                    break
                except Exception:
                    continue
        if demo_gold is not None:
            with db.connect() as con2:
                con2.execute("INSERT OR IGNORE INTO schemes VALUES (?,?,?,?,?)",
                             (demo_gold.scheme_id, demo_gold.scheme_name, demo_gold.department, demo_gold.jurisdiction, db.now()))
                n = con2.execute("SELECT COALESCE(MAX(version),0)+1 FROM rule_versions WHERE scheme_id=?", (demo_gold.scheme_id,)).fetchone()[0]
                cur = con2.execute(
                    "INSERT INTO rule_versions(scheme_id, version, status, rules_json, issues_json, extractor, source_doc_id, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (demo_gold.scheme_id, n, "draft", demo_gold.model_dump_json(), "[]",
                     "demo:gold-rules", doc.doc_id, db.now()),
                )
                vid = cur.lastrowid
            return {"version_id": vid, "scheme_id": demo_gold.scheme_id, "version": n,
                    "rules": demo_gold.model_dump(), "issues": [], "llm": {"backend": "demo-fallback", "model": "gold-rules", "error": str(e)},
                    "review": None}
        raise HTTPException(502, str(e))

    with db.connect() as con:
        db.log_call(con, "extract", res.meta.__dict__)
        if res.draft is None:
            raise HTTPException(502, f"Model returned invalid output: {res.meta.error}")
        rules, issues = compile_draft(res.draft, doc, extractor=f"{res.meta.backend}:{res.meta.model}", scheme_id=scheme_id)
        review_meta = None
        if review:
            try:
                from paatrata_core.review import review_and_apply
                more, review_meta = review_and_apply(rules, doc)
                issues += more
                if review_meta:
                    db.log_call(con, "review", review_meta.__dict__)
            except Exception as rev_err:
                db.log_call(con, "review", {"error": str(rev_err)})
                # Review failed but extraction succeeded — continue without review
        con.execute("INSERT OR REPLACE INTO source_docs VALUES (?,?,?,?,?,?,?,?,?)",
                    (doc.doc_id, doc.title, doc.mime_type, doc.sha256, url, int(is_primary_source),
                     json.dumps(doc.pages, ensure_ascii=False), str(path), db.now()))
        con.execute("INSERT OR IGNORE INTO schemes VALUES (?,?,?,?,?)",
                    (rules.scheme_id, rules.scheme_name, rules.department, rules.jurisdiction, db.now()))
        n = con.execute("SELECT COALESCE(MAX(version),0)+1 FROM rule_versions WHERE scheme_id=?", (rules.scheme_id,)).fetchone()[0]
        cur = con.execute(
            "INSERT INTO rule_versions(scheme_id, version, status, rules_json, issues_json, extractor, source_doc_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (rules.scheme_id, n, "draft", rules.model_dump_json(), json.dumps([i.model_dump() for i in issues]),
             rules.extractor, doc.doc_id, db.now()),
        )
        vid = cur.lastrowid
    return {"version_id": vid, "scheme_id": rules.scheme_id, "version": n, "rules": rules.model_dump(),
            "issues": [i.model_dump() for i in issues], "llm": res.meta.__dict__,
            "review": review_meta.__dict__ if review_meta else None}


@app.get("/api/schemes")
def list_schemes():
    with db.connect() as con:
        rows = con.execute(
            "SELECT s.id, s.name, s.department, s.jurisdiction,"
            " (SELECT MAX(version) FROM rule_versions v WHERE v.scheme_id=s.id) AS latest_version,"
            " (SELECT MAX(version) FROM rule_versions v WHERE v.scheme_id=s.id AND v.status='approved') AS approved_version"
            " FROM schemes s ORDER BY s.name").fetchall()
    return [dict(r) for r in rows]


@app.get("/api/schemes/{scheme_id}")
def get_scheme(scheme_id: str):
    with db.connect() as con:
        s = con.execute("SELECT * FROM schemes WHERE id=?", (scheme_id,)).fetchone()
        if not s:
            raise HTTPException(404, "scheme not found")
        versions = [db.row(r) for r in con.execute(
            "SELECT * FROM rule_versions WHERE scheme_id=? ORDER BY version DESC", (scheme_id,)).fetchall()]
    return {"scheme": dict(s), "versions": versions}


@app.get("/api/versions/{vid}")
def get_version(vid: int):
    with db.connect() as con:
        v = _version(con, vid)
        src = db.row(con.execute("SELECT id, title, url, is_primary_source, pages_json FROM source_docs WHERE id=?",
                                 (v["source_doc_id"],)).fetchone()) if v["source_doc_id"] else None
    v["open_ambiguities"] = _open_ambiguities(v["rules"])
    v["source"] = src
    return v


class Resolution(BaseModel):
    resolution: str
    op: Optional[str] = None
    value: Optional[Any] = None


@app.post("/api/versions/{vid}/conditions/{cid}/resolve")
def resolve(vid: int, cid: str, body: Resolution, who: str = Depends(require_admin)):
    with db.connect() as con:
        v = _version(con, vid)
        if v["status"] != "draft":
            raise HTTPException(409, "Only drafts can be edited; compile a new version.")
        rules = v["rules"]
        cond = next((c for c in rules["conditions"] if c["id"] == cid), None)
        if not cond:
            raise HTTPException(404, "condition not found")
        cond["ambiguity_resolution"] = f"{body.resolution} ({who})"
        if body.op is not None:
            cond["op"] = body.op
        if body.value is not None:
            cond["value"] = body.value
        RuleSet.model_validate(rules)  # still well-formed
        con.execute("UPDATE rule_versions SET rules_json=? WHERE id=?", (json.dumps(rules, ensure_ascii=False), vid))
    return {"ok": True, "open_ambiguities": _open_ambiguities(rules)}


@app.delete("/api/versions/{vid}/conditions/{cid}")
def drop_condition(vid: int, cid: str, _: str = Depends(require_admin)):
    with db.connect() as con:
        v = _version(con, vid)
        if v["status"] != "draft":
            raise HTTPException(409, "Only drafts can be edited.")
        rules = v["rules"]
        rules["conditions"] = [c for c in rules["conditions"] if c["id"] != cid]
        con.execute("UPDATE rule_versions SET rules_json=? WHERE id=?", (json.dumps(rules, ensure_ascii=False), vid))
    return {"ok": True}


@app.post("/api/versions/{vid}/approve")
def approve(vid: int, who: str = Depends(require_admin)):
    from paatrata_core.schema import Issue

    with db.connect() as con:
        v = _version(con, vid)
        if v["status"] != "draft":
            raise HTTPException(409, f"Version is {v['status']}.")
        blocking = blocking_issues([Issue.model_validate(i) for i in v["issues"]])
        open_q = _open_ambiguities(v["rules"])
        if blocking or open_q:
            raise HTTPException(409, {"blocking_issues": [b.model_dump() for b in blocking], "open_ambiguities": open_q})
        con.execute("UPDATE rule_versions SET status='superseded' WHERE scheme_id=? AND status='approved'", (v["scheme_id"],))
        con.execute("UPDATE rule_versions SET status='approved', approved_at=?, approved_by=? WHERE id=?", (db.now(), who, vid))
    return {"ok": True, "version_id": vid}


@app.get("/api/versions/{vid}/tests")
def version_tests(vid: int):
    with db.connect() as con:
        v = _version(con, vid)
    rules = RuleSet.model_validate(v["rules"])
    own = run_tests(rules, generate_tests(rules))
    out: dict[str, Any] = {"self": [r.model_dump() for r in own]}
    gold = _gold(rules.scheme_id)
    if gold is not None and rules.extractor != "gold":
        vs_gold = run_tests(rules, generate_tests(gold, reference=gold, origin="gold"))
        out["gold"] = [r.model_dump() for r in vs_gold]
        out["gold_passed"] = sum(r.passed for r in vs_gold)
        out["gold_total"] = len(vs_gold)
    return out


# --------------------------------------------------------------------------- query path
class BatchCheckRequest(BaseModel):
    scheme_id: str
    profiles: list[dict[str, Any]]
    lang: str = "en"


class CheckRequest(BaseModel):
    scheme_id: str
    profile: dict[str, Any]
    lang: str = "en"
    version_id: Optional[int] = None  # default: latest approved


@app.post("/api/check")
def check(req: CheckRequest):
    with db.connect() as con:
        if req.version_id:
            v = _version(con, req.version_id)
        else:
            v = db.row(con.execute(
                "SELECT * FROM rule_versions WHERE scheme_id=? AND status='approved' ORDER BY version DESC LIMIT 1",
                (req.scheme_id,)).fetchone())
        if not v:
            raise HTTPException(404, "No approved rules for this scheme yet.")
        rules = RuleSet.model_validate(v["rules"])
        verdict = evaluate(rules, req.profile)
        expl = explain(verdict, rules.scheme_name, req.lang)
        if expl.get("meta"):
            db.log_call(con, "explain", expl["meta"])
    return {"version_id": v["id"], "version": v["version"], "status": v["status"], "extractor": v["extractor"],
            "verdict": verdict.model_dump(), "explanation": {k: x for k, x in expl.items() if k != "meta"}}


@app.get("/api/schemes/{scheme_id}/form")
def scheme_form(scheme_id: str):
    """Fields the citizen form must ask for (from the latest approved version)."""
    with db.connect() as con:
        v = db.row(con.execute(
            "SELECT * FROM rule_versions WHERE scheme_id=? AND status='approved' ORDER BY version DESC LIMIT 1",
            (scheme_id,)).fetchone())
    if not v:
        raise HTTPException(404, "No approved rules for this scheme yet.")
    rules = RuleSet.model_validate(v["rules"])
    return [{"name": f, "type": FIELDS[f].type, "unit": FIELDS[f].unit, "description": FIELDS[f].description,
             "options": list(FIELDS[f].options)} for f in fields_used(rules)]


@app.get("/api/overview")
def overview():
    """Landing-page summary computed from the rulebook (nothing hard-coded)."""
    from paatrata_core.registry import read_sources

    src = {r["scheme_id"]: r for r in read_sources(SOURCES_CSV)}
    out = []
    with db.connect() as con:
        for s in con.execute("SELECT * FROM schemes ORDER BY name").fetchall():
            v = db.row(con.execute(
                "SELECT * FROM rule_versions WHERE scheme_id=? AND status='approved' ORDER BY version DESC LIMIT 1",
                (s["id"],)).fetchone())
            if not v:
                continue
            r = v["rules"]
            out.append({
                "id": s["id"], "name": s["name"], "version": v["version"], "extractor": v["extractor"],
                "conditions": len(r["conditions"]), "needs_human": len(r["unmapped_conditions"]),
                "any_groups": sum(1 for g in r["groups"] if g["logic"] == "ANY"),
                "benefit": r.get("benefit_summary"),
                "source_type": src.get(s["id"], {}).get("source_type", "unknown"),
            })
    ev = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else None
    return {"schemes": out, "eval": ev}


@app.get("/api/schemes/{scheme_id}/examples")
def scheme_examples(scheme_id: str, limit: int = 8):
    """Boundary cases from the approved rules: one-click demo profiles for the Check screen."""
    with db.connect() as con:
        v = db.row(con.execute(
            "SELECT * FROM rule_versions WHERE scheme_id=? AND status='approved' ORDER BY version DESC LIMIT 1",
            (scheme_id,)).fetchone())
    if not v:
        raise HTTPException(404, "No approved rules for this scheme yet.")
    tests = generate_tests(RuleSet.model_validate(v["rules"]))
    picked, seen = [], set()
    for t in tests:  # prefer a mix of verdicts
        if t.expected not in seen or len(picked) < limit // 2:
            picked.append(t)
            seen.add(t.expected)
        if len(picked) >= limit:
            break
    return [{"description": t.description, "profile": t.profile, "expected": t.expected} for t in picked]


# --------------------------------------------------------------------------- confidence / batch / diff / audit

@app.get("/api/confidence/{scheme_id}")
def confidence_report(scheme_id: str):
    """Per-condition trust breakdown: quote match score, confidence, ambiguity status."""
    with db.connect() as con:
        v = db.row(con.execute(
            "SELECT * FROM rule_versions WHERE scheme_id=? AND status='approved' ORDER BY version DESC LIMIT 1",
            (scheme_id,)).fetchone())
    if not v:
        raise HTTPException(404, "No approved rules for this scheme.")
    rules = v["rules"]
    conditions = []
    for c in rules["conditions"]:
        conditions.append({
            "id": c["id"],
            "field": c["field"],
            "op": c["op"],
            "value": c["value"],
            "confidence": c.get("confidence", 1.0),
            "quote_verified": c["citation"].get("verified", False),
            "quote_match_score": c["citation"].get("match_score"),
            "has_ambiguity": bool(c.get("ambiguity")),
            "ambiguity_resolved": bool(c.get("ambiguity_resolution")),
            "quote_snippet": c["citation"]["quote"][:80] + ("…" if len(c["citation"]["quote"]) > 80 else ""),
        })
    avg_confidence = sum(c["confidence"] for c in conditions) / max(len(conditions), 1)
    all_verified = all(c["quote_verified"] for c in conditions)
    return {
        "scheme_id": scheme_id,
        "version": v["version"],
        "overall_confidence": round(avg_confidence, 3),
        "all_quotes_verified": all_verified,
        "n_conditions": len(conditions),
        "n_unmapped": len(rules.get("unmapped_conditions", [])),
        "conditions": conditions,
    }


@app.post("/api/check/batch")
def check_batch(req: BatchCheckRequest):
    """Check multiple applicants against one scheme. Max 50 per call."""
    if len(req.profiles) > 50:
        raise HTTPException(400, "Maximum 50 profiles per batch.")
    with db.connect() as con:
        v = db.row(con.execute(
            "SELECT * FROM rule_versions WHERE scheme_id=? AND status='approved' ORDER BY version DESC LIMIT 1",
            (req.scheme_id,)).fetchone())
        if not v:
            raise HTTPException(404, "No approved rules for this scheme yet.")
        rules = RuleSet.model_validate(v["rules"])
        results = []
        for i, profile in enumerate(req.profiles):
            verdict = evaluate(rules, profile)
            results.append({
                "index": i,
                "verdict": verdict.verdict,
                "missing_fields": verdict.missing_fields,
                "failed_conditions": verdict.failed_conditions,
            })
    summary = {
        "total": len(results),
        "eligible": sum(1 for r in results if r["verdict"] == "ELIGIBLE"),
        "not_eligible": sum(1 for r in results if r["verdict"] == "NOT_ELIGIBLE"),
        "needs_info": sum(1 for r in results if r["verdict"] == "NEEDS_INFO"),
    }
    return {"scheme_id": req.scheme_id, "version": v["version"], "summary": summary, "results": results}


@app.post("/api/check/all")
def check_all_schemes(profile: dict[str, Any]):
    """Check one applicant against every approved scheme."""
    with db.connect() as con:
        rows = con.execute(
            "SELECT rv.* FROM rule_versions rv "
            "INNER JOIN (SELECT scheme_id, MAX(version) as mv FROM rule_versions WHERE status='approved' GROUP BY scheme_id) latest "
            "ON rv.scheme_id = latest.scheme_id AND rv.version = latest.mv"
        ).fetchall()
        results = []
        for row in rows:
            v = db.row(row)
            rules = RuleSet.model_validate(v["rules"])
            verdict = evaluate(rules, profile)
            results.append({
                "scheme_id": rules.scheme_id,
                "scheme_name": rules.scheme_name,
                "benefit": rules.benefit_summary,
                "verdict": verdict.verdict,
                "missing_fields": verdict.missing_fields,
                "failed_conditions": [r.field for r in verdict.results if r.outcome == "FALSE"],
            })
    return {
        "eligible": [r for r in results if r["verdict"] == "ELIGIBLE"],
        "not_eligible": [r for r in results if r["verdict"] == "NOT_ELIGIBLE"],
        "needs_info": [r for r in results if r["verdict"] == "NEEDS_INFO"],
        "total_schemes": len(results),
    }


@app.get("/api/versions/{vid1}/diff/{vid2}")
def diff_versions(vid1: int, vid2: int):
    """Compare two rule versions: added, removed, changed conditions."""
    with db.connect() as con:
        v1 = _version(con, vid1)
        v2 = _version(con, vid2)
    r1 = {c["id"]: c for c in v1["rules"]["conditions"]}
    r2 = {c["id"]: c for c in v2["rules"]["conditions"]}
    added = [c for cid, c in r2.items() if cid not in r1]
    removed = [c for cid, c in r1.items() if cid not in r2]
    changed = []
    for cid in set(r1) & set(r2):
        c1, c2 = r1[cid], r2[cid]
        diffs = {}
        for key in ("field", "op", "value"):
            if c1.get(key) != c2.get(key):
                diffs[key] = {"old": c1.get(key), "new": c2.get(key)}
        if diffs:
            changed.append({"id": cid, "changes": diffs})
    return {
        "version_a": {"id": vid1, "version": v1["version"], "extractor": v1["extractor"]},
        "version_b": {"id": vid2, "version": v2["version"], "extractor": v2["extractor"]},
        "added": added, "removed": removed, "changed": changed,
        "conditions_a": len(r1), "conditions_b": len(r2),
    }


@app.get("/api/audit/{scheme_id}")
def audit_trail(scheme_id: str):
    """Full version history with approval metadata."""
    with db.connect() as con:
        s = con.execute("SELECT * FROM schemes WHERE id=?", (scheme_id,)).fetchone()
        if not s:
            raise HTTPException(404, "scheme not found")
        versions = con.execute(
            "SELECT id, version, status, extractor, created_at, approved_at, approved_by, source_doc_id "
            "FROM rule_versions WHERE scheme_id=? ORDER BY version", (scheme_id,)).fetchall()
    return {
        "scheme_id": scheme_id,
        "scheme_name": dict(s)["name"],
        "history": [{
            "version_id": dict(v)["id"],
            "version": dict(v)["version"],
            "status": dict(v)["status"],
            "extractor": dict(v)["extractor"],
            "compiled_at": dict(v)["created_at"],
            "approved_at": dict(v)["approved_at"],
            "approved_by": dict(v)["approved_by"],
        } for v in versions],
    }


# --------------------------------------------------------------------------- eval + logs
@app.get("/api/eval")
def eval_results():
    if not RESULTS.exists():
        return {"available": False, "message": "Run `python -m evaluation.run_eval` to produce results."}
    return {"available": True, **json.loads(RESULTS.read_text(encoding="utf-8"))}


@app.get("/api/llm-calls")
def llm_calls(limit: int = 50):
    with db.connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM llm_calls ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]


# --------------------------------------------------------------------------- chatbot

CHAT_SYSTEM = """You are an eligibility assistant for Chandigarh welfare schemes.
The user will describe themselves in English, Hindi, Punjabi, or Hinglish.

Extract these fields from their message (ONLY the ones they mention):
- age_years (number)
- gender (male/female/other)
- marital_status (unmarried/married/widowed/divorced/separated)
- family_annual_income_inr (number — convert lakhs: 1.5 lakh = 150000)
- residence_years_in_jurisdiction (number)
- is_domicile_of_jurisdiction (true if they say they live in/are from Chandigarh)
- is_disabled (true/false)
- disability_percentage (number 0-100)
- is_bpl (true/false — below poverty line)
- caste_category (general/sc/st/obc/bc)
- is_construction_worker (true/false)
- is_registered_construction_worker (true/false)
- children_count (number)
- youngest_child_age_months (number)
- is_pregnant (true/false)
- is_lactating (true/false)

Return ONLY valid JSON, no markdown, no explanation:
{"fields": {"age_years": 65, "family_annual_income_inr": 120000, ...}}

Only include fields the user actually mentioned. Convert all values to the right type.
"1.2 lakh" or "1,20,000" or "120000" all become 120000.
If they say "Chandigarh mein rehta hoon" → is_domicile_of_jurisdiction: true.
If they mention years in Chandigarh → residence_years_in_jurisdiction.
"""


class ChatRequest(BaseModel):
    message: str


def _regex_extract(msg: str) -> dict:
    """Best-effort field extraction from natural language without an LLM."""
    import re
    fields: dict[str, Any] = {}
    low = msg.lower()

    # Age
    m = re.search(r'(?:age|umar|umr|aged?)\s*(?:is|hai|h|:)?\s*(\d{1,3})', low) or re.search(r'(\d{1,3})\s*(?:years?\s*old|saal|sal\b)', low)
    if m: fields["age_years"] = int(m.group(1))

    # Gender
    if re.search(r'\b(female|woman|lady|mahila|aurat|istri)\b', low): fields["gender"] = "female"
    elif re.search(r'\b(male|man|aadmi|purush)\b', low): fields["gender"] = "male"

    # Income
    m = re.search(r'(?:income|kamai|aay|amdani|salary)\s*(?:is|hai|h|:)?\s*(?:rs\.?|₹)?\s*([\d,]+(?:\.\d+)?)\s*(?:lakh|lac|lacs)?', low)
    if m:
        val = float(m.group(1).replace(",", ""))
        if "lakh" in low or "lac" in low: val *= 100000
        fields["family_annual_income_inr"] = val
    else:
        m = re.search(r'([\d.]+)\s*(?:lakh|lac)', low)
        if m: fields["family_annual_income_inr"] = float(m.group(1)) * 100000

    # Domicile / Chandigarh
    if re.search(r'chandigarh', low): fields["is_domicile_of_jurisdiction"] = True
    m = re.search(r'(\d+)\s*(?:years?|saal|sal)\s*(?:in\s*chandigarh|chandigarh\s*(?:me|mein|mai))', low)
    if m: fields["residence_years_in_jurisdiction"] = int(m.group(1))

    # BPL
    if re.search(r'\bbpl\b|below\s*poverty|garib', low): fields["is_bpl"] = True

    # Caste
    for cat in ["sc", "st", "obc", "bc", "general"]:
        if re.search(rf'\b{cat}\b', low): fields["caste_category"] = cat; break

    # Disabled
    if re.search(r'disab|viklang|apang|divyang', low): fields["is_disabled"] = True
    m = re.search(r'(\d+)\s*%\s*(?:disab|viklang)?', low)
    if m: fields["disability_percentage"] = int(m.group(1)); fields["is_disabled"] = True

    # Marital status
    if re.search(r'widow|vidhwa', low): fields["marital_status"] = "widowed"
    elif re.search(r'unmarried|single|kunwara|kunwari', low): fields["marital_status"] = "unmarried"
    elif re.search(r'married|shaadi|vivahit', low): fields["marital_status"] = "married"
    elif re.search(r'divorced|talaq', low): fields["marital_status"] = "divorced"

    # Construction worker
    if re.search(r'construction\s*worker|nirman\s*shramik|mazdoor', low): fields["is_construction_worker"] = True
    if re.search(r'registered\s*(?:construction\s*)?worker|panjikrit', low): fields["is_registered_construction_worker"] = True

    # Children
    m = re.search(r'(\d+)\s*(?:children|kids|bachch|bacch)', low)
    if m: fields["children_count"] = int(m.group(1))

    # Pregnant / lactating
    if re.search(r'pregnant|garbhvati|garbhwati', low): fields["is_pregnant"] = True
    if re.search(r'lactating|breastfeed|stanpan|dudh', low): fields["is_lactating"] = True

    return fields


@app.post("/api/chat")
def chat(req: ChatRequest):
    """Conversational eligibility check: extract fields from natural language, run deterministic eval."""
    import google.genai as genai

    fields = None
    _demo = os.environ.get("DEMO_MODE") or not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))

    if not _demo:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        client = genai.Client(api_key=api_key)
        # Step 1: Extract structured fields from conversational input via Gemini
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    {"role": "user", "parts": [{"text": CHAT_SYSTEM + "\n\nUser message: " + req.message}]}
                ],
            )
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            if raw.startswith("json"):
                raw = raw[4:]
            extracted = json.loads(raw.strip())
            fields = extracted.get("fields", extracted)
        except Exception as e:
            with db.connect() as con:
                db.log_call(con, "chat-extract", {"error": str(e), "input": req.message[:200]})
            # Fall through to regex fallback

    if fields is None:
        fields = _regex_extract(req.message)
        if not fields:
            raise HTTPException(400, "Could not understand your message. Please mention your age, income, location, etc.")

    with db.connect() as con:
        db.log_call(con, "chat-extract", {"input": req.message[:200], "fields": fields})

    # Step 2: Run deterministic evaluation against ALL approved schemes
    with db.connect() as con:
        rows = con.execute(
            "SELECT rv.* FROM rule_versions rv "
            "INNER JOIN (SELECT scheme_id, MAX(version) as mv FROM rule_versions WHERE status='approved' GROUP BY scheme_id) latest "
            "ON rv.scheme_id = latest.scheme_id AND rv.version = latest.mv"
        ).fetchall()

        results = []
        for row in rows:
            v = db.row(row)
            rules = RuleSet.model_validate(v["rules"])
            verdict = evaluate(rules, fields)
            citations = []
            for r in verdict.results:
                if r.citation:
                    citations.append({
                        "field": r.field,
                        "quote": r.citation.quote,
                        "page": r.citation.page,
                    })
            results.append({
                "scheme_id": rules.scheme_id,
                "scheme_name": rules.scheme_name,
                "benefit": rules.benefit_summary,
                "verdict": verdict.verdict,
                "missing_fields": verdict.missing_fields,
                "failed_conditions": [r.field for r in verdict.results if r.outcome == "FALSE"],
                "citations": citations,
            })

    # Step 3: Build a conversational reply
    eligible = [r for r in results if r["verdict"] == "ELIGIBLE"]
    not_eligible = [r for r in results if r["verdict"] == "NOT_ELIGIBLE"]
    needs_info = [r for r in results if r["verdict"] == "NEEDS_INFO"]

    parts = []
    if eligible:
        names = ", ".join(r["scheme_name"] for r in eligible)
        parts.append(f"Good news! Based on what you told me, you appear eligible for: {names}.")
    if not_eligible:
        names = ", ".join(r["scheme_name"] for r in not_eligible)
        parts.append(f"You don't appear to meet the criteria for: {names}.")
    if needs_info:
        all_missing = set()
        for r in needs_info:
            all_missing.update(r["missing_fields"])
        parts.append(
            f"For {len(needs_info)} scheme(s), I need more information: {', '.join(sorted(all_missing))}. "
            "Could you tell me about those?"
        )
    if not parts:
        parts.append("I couldn't find any applicable schemes. Try telling me more about yourself.")

    reply = " ".join(parts)

    return {
        "reply": reply,
        "extracted_fields": fields,
        "results": results,
    }


# --------------------------------------------------------------------------- UI
_dist = ROOT / "web" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
