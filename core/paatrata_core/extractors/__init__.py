"""Extractor factory. Backends: gemini | groq | gemma-studio | ollama | cache:<backend>:<model>."""
from __future__ import annotations

from .base import CacheOnlyExtractor, ExtractionError, ExtractionResult, Extractor
from .gemini import GeminiExtractor
from .gemma import GemmaStudioExtractor, OllamaExtractor
from .groq import GroqExtractor

BACKENDS = ("gemini", "groq", "gemma-studio", "ollama")


def get_extractor(backend: str = "gemini", model: str | None = None, **kw) -> Extractor:
    if backend == "gemini":
        return GeminiExtractor(model, **kw)
    if backend == "groq":
        return GroqExtractor(model, **kw)
    if backend == "gemma-studio":
        return GemmaStudioExtractor(model, **kw)
    if backend == "ollama":
        return OllamaExtractor(model, **kw)
    if backend.startswith("cache:"):
        _, b, m = backend.split(":", 2)
        return CacheOnlyExtractor(b, m, **kw)
    raise ValueError(f"unknown backend {backend!r}; choose from {BACKENDS} or cache:<backend>:<model>")


__all__ = ["get_extractor", "Extractor", "ExtractionResult", "ExtractionError", "BACKENDS"]
