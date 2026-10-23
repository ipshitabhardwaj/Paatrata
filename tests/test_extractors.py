import json
from pathlib import Path

import pytest

from paatrata_core.extractors import get_extractor
from paatrata_core.extractors.base import CallMeta, ExtractionError, Extractor, parse_json_text
from paatrata_core.ingest import load_file

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/oapc_draft_handmade.json").read_text(encoding="utf-8"))
FIXTURE.pop("_note")


class FakeExtractor(Extractor):
    backend = "fake"
    calls = 0

    def _call(self, doc):
        FakeExtractor.calls += 1
        return "```json\n" + json.dumps(FIXTURE) + "\n```", CallMeta(backend="fake", model=self.model)


def test_parse_json_text_handles_fences_and_prose():
    assert parse_json_text('Here you go:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_text('sure {"a": {"b": 2}} done') == {"a": {"b": 2}}


def test_cache_roundtrip(tmp_path):
    doc = load_file(ROOT / "samples/sources/oapc_chandigarh.txt")
    ex = FakeExtractor("m1", cache_dir=tmp_path)
    r1 = ex.extract(doc)
    r2 = ex.extract(doc)
    assert r1.draft and r2.draft and not r1.meta.cache_hit and r2.meta.cache_hit
    assert FakeExtractor.calls == 1
    replay = get_extractor("cache:fake:m1", cache_dir=tmp_path).extract(doc)
    assert replay.meta.cache_hit and len(replay.draft.conditions) == 5


def test_cache_only_miss_raises(tmp_path):
    doc = load_file(ROOT / "samples/sources/oapc_chandigarh.txt")
    with pytest.raises(ExtractionError):
        get_extractor("cache:gemini:nope", cache_dir=tmp_path).extract(doc)


def test_gemini_without_key_fails_clearly(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    doc = load_file(ROOT / "samples/sources/oapc_chandigarh.txt")
    with pytest.raises(ExtractionError, match="GEMINI_API_KEY"):
        get_extractor("gemini", cache_dir=tmp_path).extract(doc)


def test_groq_without_key_fails_clearly(monkeypatch, tmp_path):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    doc = load_file(ROOT / "samples/sources/oapc_chandigarh.txt")
    with pytest.raises(ExtractionError, match="GROQ_API_KEY"):
        get_extractor("groq", cache_dir=tmp_path).extract(doc)

