"""Load hand-labelled gold rules as approved versions so the Check screen works
with no API key. These are labelled extractor='gold' everywhere in the UI.

    python -m server.seed            # seed if empty
    python -m server.seed --force    # add gold versions again
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from paatrata_core.ingest import load_file
from paatrata_core.registry import read_sources
from paatrata_core.schema import RuleSet

from . import db

ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = ROOT / "evaluation" / "gold"
SOURCES = ROOT / "samples" / "sources"


def seed_gold(force: bool = False) -> int:
    db.init()
    n = 0
    sources = {r["scheme_id"]: r for r in read_sources(SOURCES / "sources.csv")}
    with db.connect() as con:
        for p in sorted(GOLD_DIR.glob("*.json")):
            rules = RuleSet.model_validate(json.loads(p.read_text(encoding="utf-8")))
            exists = con.execute("SELECT 1 FROM rule_versions WHERE scheme_id=? AND extractor='gold'", (rules.scheme_id,)).fetchone()
            if exists and not force:
                continue
            con.execute("INSERT OR IGNORE INTO schemes VALUES (?,?,?,?,?)",
                        (rules.scheme_id, rules.scheme_name, rules.department, rules.jurisdiction, db.now()))
            doc_id = None
            row = sources.get(rules.scheme_id)
            if row and (SOURCES / row["file"]).exists():
                doc = load_file(SOURCES / row["file"], url=row.get("url"), is_primary_source=row.get("source_type") == "primary")
                doc_id = doc.doc_id
                con.execute("INSERT OR REPLACE INTO source_docs VALUES (?,?,?,?,?,?,?,?,?)",
                            (doc.doc_id, doc.title, doc.mime_type, doc.sha256, doc.url, int(doc.is_primary_source),
                             json.dumps(doc.pages, ensure_ascii=False), str(SOURCES / row["file"]), db.now()))
            ver = con.execute("SELECT COALESCE(MAX(version),0)+1 FROM rule_versions WHERE scheme_id=?", (rules.scheme_id,)).fetchone()[0]
            con.execute("UPDATE rule_versions SET status='superseded' WHERE scheme_id=? AND status='approved'", (rules.scheme_id,))
            con.execute(
                "INSERT INTO rule_versions(scheme_id, version, status, rules_json, issues_json, extractor, source_doc_id, created_at, approved_at, approved_by)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (rules.scheme_id, ver, "approved", rules.model_dump_json(), "[]", "gold", doc_id, db.now(), db.now(), "seed (hand-labelled gold)"),
            )
            n += 1
    return n


def seed_gold_if_empty() -> int:
    db.init()
    with db.connect() as con:
        if con.execute("SELECT COUNT(*) FROM rule_versions").fetchone()[0]:
            return 0
    return seed_gold()


if __name__ == "__main__":
    print(f"seeded {seed_gold(force='--force' in sys.argv)} scheme(s)")
