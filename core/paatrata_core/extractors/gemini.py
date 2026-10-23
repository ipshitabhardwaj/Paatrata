"""Gemini backend: native structured output with ``SchemeDraft`` as response schema."""
from __future__ import annotations

import os

from ..ingest import SourceDoc
from ..schema import SchemeDraft
from .base import CallMeta, ExtractionError, Extractor, with_retries
from .prompts import system_prompt, user_prompt

DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")


def _client():
    try:
        from google import genai
    except ImportError as e:  # pragma: no cover
        raise ExtractionError("google-genai is not installed: pip install google-genai") from e
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise ExtractionError("GEMINI_API_KEY is not set (get one at https://aistudio.google.com/apikey).")
    return genai.Client(api_key=key)


def build_contents(doc: SourceDoc):
    """Send page-numbered text when the PDF has a text layer (quotes then match
    exactly); send the PDF itself when it is scanned, so Gemini can read it."""
    from google.genai import types

    if doc.has_text:
        return [user_prompt(doc.title, doc.numbered_text())]
    if doc.mime_type == "application/pdf":
        return [types.Part.from_bytes(data=doc.data, mime_type="application/pdf"), user_prompt(doc.title, None)]
    raise ExtractionError("Document has no text and is not a PDF.")


class GeminiExtractor(Extractor):
    backend = "gemini"

    def __init__(self, model: str | None = None, **kw):
        super().__init__(model or DEFAULT_GEMINI_MODEL, **kw)

    def _call(self, doc: SourceDoc) -> tuple[str, CallMeta]:
        from google.genai import types

        client = _client()
        config = types.GenerateContentConfig(
            system_instruction=system_prompt(),
            response_mime_type="application/json",
            response_schema=SchemeDraft,
            temperature=0.0,
        )
        resp, attempts = with_retries(
            lambda: client.models.generate_content(model=self.model, contents=build_contents(doc), config=config),
            model=self.model,
        )
        usage = getattr(resp, "usage_metadata", None)
        meta = CallMeta(
            backend=self.backend, model=self.model, attempts=attempts,
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
        )
        return resp.text or "", meta


def generate_structured(prompt: str, schema, model: str | None = None, temperature: float = 0.0) -> tuple[str, CallMeta]:
    """Gemini call constrained to a Pydantic response schema."""
    from google.genai import types

    client = _client()
    model = model or DEFAULT_GEMINI_MODEL
    config = types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema,
                                         temperature=temperature)
    resp, attempts = with_retries(lambda: client.models.generate_content(model=model, contents=[prompt], config=config),
                                  model=model)
    usage = getattr(resp, "usage_metadata", None)
    return resp.text or "", CallMeta(
        backend="gemini", model=model, attempts=attempts,
        input_tokens=getattr(usage, "prompt_token_count", None),
        output_tokens=getattr(usage, "candidates_token_count", None),
    )


def generate_json(prompt: str, model: str | None = None, temperature: float = 0.0, system: str | None = None) -> tuple[str, CallMeta]:
    """Small helper for other Gemini calls (explanations, RAG baseline)."""
    from google.genai import types

    client = _client()
    model = model or DEFAULT_GEMINI_MODEL
    config = types.GenerateContentConfig(
        system_instruction=system, response_mime_type="application/json", temperature=temperature,
    )
    resp, attempts = with_retries(lambda: client.models.generate_content(model=model, contents=[prompt], config=config), model=model)
    usage = getattr(resp, "usage_metadata", None)
    return resp.text or "", CallMeta(
        backend="gemini", model=model, attempts=attempts,
        input_tokens=getattr(usage, "prompt_token_count", None),
        output_tokens=getattr(usage, "candidates_token_count", None),
    )
