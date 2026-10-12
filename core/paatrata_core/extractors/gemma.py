"""Gemma backends (open weights, Apache-2.0 for Gemma 4).

* ``GemmaStudioExtractor`` - Gemma hosted on the Gemini API / AI Studio. Gemma on
  the API has historically not supported JSON mode or system instructions, so the
  schema goes into the prompt and the JSON is parsed + validated by us.
* ``OllamaExtractor``      - Gemma running locally through Ollama; Ollama's
  ``format`` parameter constrains output to the JSON schema.

Model names change; set GEMMA_MODEL / OLLAMA_MODEL to what AI Studio / `ollama list` shows.
"""
from __future__ import annotations

import os

from pydantic import ValidationError

from ..ingest import SourceDoc
from ..schema import SchemeDraft
from .base import CallMeta, ExtractionError, Extractor, parse_draft, with_retries
from .gemini import _client
from .prompts import json_schema_instruction, system_prompt, user_prompt

DEFAULT_GEMMA_MODEL = os.environ.get("GEMMA_MODEL", "gemma-4-31b-it")
DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e2b")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def _require_text(doc: SourceDoc) -> str:
    if not doc.has_text:
        raise ExtractionError("Gemma backends need a text layer; this document looks scanned. Use Gemini.")
    return doc.numbered_text()


class GemmaStudioExtractor(Extractor):
    backend = "gemma-studio"

    def __init__(self, model: str | None = None, **kw):
        super().__init__(model or DEFAULT_GEMMA_MODEL, **kw)

    def _call(self, doc: SourceDoc) -> tuple[str, CallMeta]:
        from google.genai import types

        client = _client()
        prompt = "\n\n".join([system_prompt(), json_schema_instruction(), user_prompt(doc.title, _require_text(doc))])
        config = types.GenerateContentConfig(temperature=0.0)
        resp, attempts = with_retries(lambda: client.models.generate_content(model=self.model, contents=[prompt], config=config), model=self.model)
        text = resp.text or ""
        # one repair round if the JSON does not validate
        try:
            parse_draft(text)
        except (ValidationError, ValueError) as e:
            repair = prompt + f"\n\nYour previous answer was invalid: {str(e)[:800]}\nReturn corrected JSON only."
            resp, more = with_retries(lambda: client.models.generate_content(model=self.model, contents=[repair], config=config), model=self.model)
            text, attempts = resp.text or "", attempts + more
        usage = getattr(resp, "usage_metadata", None)
        return text, CallMeta(backend=self.backend, model=self.model, attempts=attempts,
                              input_tokens=getattr(usage, "prompt_token_count", None),
                              output_tokens=getattr(usage, "candidates_token_count", None))


class OllamaExtractor(Extractor):
    backend = "ollama"

    def __init__(self, model: str | None = None, host: str | None = None, **kw):
        super().__init__(model or DEFAULT_OLLAMA_MODEL, **kw)
        self.host = (host or OLLAMA_HOST).rstrip("/")

    def _call(self, doc: SourceDoc) -> tuple[str, CallMeta]:
        import requests

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt()},
                {"role": "user", "content": user_prompt(doc.title, _require_text(doc))},
            ],
            "format": SchemeDraft.model_json_schema(),
            "stream": False,
            "options": {"temperature": 0, "num_ctx": 8192},
        }

        def go():
            r = requests.post(f"{self.host}/api/chat", json=body, timeout=600)
            r.raise_for_status()
            return r.json()

        try:
            data, attempts = with_retries(go, attempts=2)
        except ExtractionError as e:
            raise ExtractionError(f"Ollama call failed ({self.host}, model {self.model}). Is `ollama serve` running? {e}")
        return data.get("message", {}).get("content", ""), CallMeta(
            backend=self.backend, model=self.model, attempts=attempts,
            input_tokens=data.get("prompt_eval_count"), output_tokens=data.get("eval_count"),
        )
