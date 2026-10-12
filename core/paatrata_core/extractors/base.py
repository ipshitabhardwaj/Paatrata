"""Extractor interface + on-disk response cache.

Every backend returns an ``ExtractionResult``. Responses are cached on disk,
keyed by (backend, model, prompt version, schema version, document hash), so the
evaluation can be re-run with no API key and no quota.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..ingest import SourceDoc
from ..schema import SCHEMA_VERSION, SchemeDraft
from .prompts import prompt_fingerprint

DEFAULT_CACHE_DIR = Path(os.environ.get("PAATRATA_CACHE_DIR", "evaluation/cache"))


@dataclass
class CallMeta:
    backend: str
    model: str
    latency_ms: int = 0
    cache_hit: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    attempts: int = 1
    error: str | None = None


@dataclass
class ExtractionResult:
    draft: SchemeDraft | None
    raw_text: str
    meta: CallMeta
    cache_key: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"raw_text": self.raw_text, "meta": asdict(self.meta), "cache_key": self.cache_key}


class ExtractionError(RuntimeError):
    def __init__(self, message: str, meta: CallMeta | None = None, raw_text: str = ""):
        super().__init__(message)
        self.meta = meta
        self.raw_text = raw_text


def parse_json_text(text: str) -> dict[str, Any]:
    """Parse a JSON object from model text, tolerating ``` fences and leading prose."""
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if fence:
        t = fence.group(1)
    else:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            t = t[start : end + 1]
    return json.loads(t)


def parse_draft(text: str) -> SchemeDraft:
    return SchemeDraft.model_validate(parse_json_text(text))


class Extractor(ABC):
    backend: str = "base"

    def __init__(self, model: str, cache_dir: Path | None = None, use_cache: bool = True):
        self.model = model
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.use_cache = use_cache

    # ---- cache ---------------------------------------------------------------
    def cache_key(self, doc: SourceDoc) -> str:
        payload = json.dumps(
            {"backend": self.backend, "model": self.model, "prompt": prompt_fingerprint(),
             "schema": SCHEMA_VERSION, "doc": doc.sha256},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:24]

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / "extract" / f"{key}.json"

    def _load_cache(self, key: str, doc: SourceDoc) -> ExtractionResult | None:
        p = self._cache_path(key)
        if not (self.use_cache and p.exists()):
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        meta = CallMeta(**{**data["meta"], "cache_hit": True, "latency_ms": 0})
        try:
            draft = parse_draft(data["raw_text"])
        except (ValidationError, ValueError):
            draft = None
        return ExtractionResult(draft=draft, raw_text=data["raw_text"], meta=meta, cache_key=key)

    def _save_cache(self, res: ExtractionResult, doc: SourceDoc) -> None:
        p = self._cache_path(res.cache_key)
        p.parent.mkdir(parents=True, exist_ok=True)
        record = res.to_json() | {"doc_title": doc.title, "doc_sha256": doc.sha256,
                                  "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        p.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- public --------------------------------------------------------------
    def extract(self, doc: SourceDoc) -> ExtractionResult:
        key = self.cache_key(doc)
        cached = self._load_cache(key, doc)
        if cached is not None:
            return cached
        t0 = time.time()
        raw, meta = self._call(doc)
        meta.latency_ms = int((time.time() - t0) * 1000)
        try:
            draft = parse_draft(raw)
        except (ValidationError, ValueError) as e:
            meta.error = f"invalid JSON from model: {e}"[:500]
            draft = None
        res = ExtractionResult(draft=draft, raw_text=raw, meta=meta, cache_key=key)
        if draft is not None:
            self._save_cache(res, doc)
        return res

    @abstractmethod
    def _call(self, doc: SourceDoc) -> tuple[str, CallMeta]:
        """Return (raw model text, meta)."""


class CacheOnlyExtractor(Extractor):
    """Replays cached responses of another backend/model; never calls a model."""

    def __init__(self, backend: str, model: str, cache_dir: Path | None = None):
        super().__init__(model, cache_dir)
        self.backend = backend

    def _call(self, doc: SourceDoc) -> tuple[str, CallMeta]:
        raise ExtractionError(
            f"No cached response for {doc.title} ({self.backend}:{self.model}). "
            "Run once with a live backend to populate evaluation/cache."
        )


def friendly_error(e: Exception, model: str | None = None) -> str:
    """Turn SDK errors into messages that say what to do."""
    msg = str(e)
    if "API_KEY_INVALID" in msg or "API key not valid" in msg:
        return "Gemini rejected the API key. Check GEMINI_API_KEY in .env (no quotes or spaces) and restart."
    if "PERMISSION_DENIED" in msg:
        return f"The API key has no access to model '{model}'. Try another model name from AI Studio."
    if "NOT_FOUND" in msg or "is not found" in msg or " 404" in msg:
        return f"Model '{model}' was not found. Set GEMINI_MODEL / GEMMA_MODEL in .env to a name listed in AI Studio."
    if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
        return ("Rate limit / free-tier quota reached. Wait a minute, or check limits in AI Studio. "
                "Cached results keep working (backend cache:<backend>:<model>).")
    if "INVALID_ARGUMENT" in msg and "schema" in msg.lower():
        return f"The model rejected the response schema: {msg[:300]}"
    return f"Model call failed: {msg[:500]}"


def with_retries(fn, attempts: int = 3, base_delay: float = 2.0, model: str | None = None):
    """Retry on rate-limit / server errors with exponential backoff."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn(), i + 1
        except Exception as e:  # noqa: BLE001 - SDKs raise varied types
            msg = str(e)
            retryable = any(s in msg for s in ("429", "RESOURCE_EXHAUSTED", "500", "503", "UNAVAILABLE", "timed out"))
            last = e
            if not retryable or i == attempts - 1:
                break
            time.sleep(base_delay * (2 ** i))
    raise ExtractionError(friendly_error(last, model) if last else "model call failed")
