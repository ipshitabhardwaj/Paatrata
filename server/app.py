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
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
    return {"ok": True, "backends": BACKENDS, "gemini_key": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))}


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

    try:
        res = get_extractor(backend, model).extract(doc)
    except (ExtractionError, ValueError) as e:
        with db.connect() as con:
            db.log_call(con, "extract", {"backend": backend, "model": model, "error": str(e)})
        raise HTTPException(502, str(e))

    with db.connect() as con:
        db.log_call(con, "extract", res.meta.__dict__)
        if res.draft is None:
            raise HTTPException(502, f"Model returned invalid output: {res.meta.error}")
        rules, issues = compile_draft(res.draft, doc, extractor=f"{res.meta.backend}:{res.meta.model}", scheme_id=scheme_id)
        review_meta = None
        if review:
            from paatrata_core.review import review_and_apply

            more, review_meta = review_and_apply(rules, doc)
            issues += more
            if review_meta:
                db.log_call(con, "review", review_meta.__dict__)
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


# --------------------------------------------------------------------------- UI
_dist = ROOT / "web" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
