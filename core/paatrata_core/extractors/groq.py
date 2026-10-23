"""Groq backend: Llama 3.1 via the Groq API (free tier, very fast)."""
from __future__ import annotations

import json
import os
import urllib.request

from pydantic import ValidationError

from ..ingest import SourceDoc
from .base import CallMeta, ExtractionError, Extractor, parse_draft, with_retries
from .prompts import json_schema_instruction, system_prompt, user_prompt

DEFAULT_GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")


class GroqExtractor(Extractor):
    backend = "groq"

    def __init__(self, model: str | None = None, **kw):
        super().__init__(model or DEFAULT_GROQ_MODEL, **kw)

    def _call(self, doc: SourceDoc) -> tuple[str, CallMeta]:
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise ExtractionError("GROQ_API_KEY is not set (get one at https://console.groq.com).")

        if not doc.has_text:
            raise ExtractionError("Groq/Llama backends need a text layer; this document looks scanned. Use Gemini.")

        sys_prompt = system_prompt() + "\n\n" + json_schema_instruction()
        usr_prompt = user_prompt(doc.title, doc.numbered_text())

        def call():
            payload = json.dumps({
                "model": self.model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": usr_prompt},
                ],
                "temperature": 0,
                "max_tokens": 8192,
            }).encode()
            rq = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=payload,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(rq, timeout=60) as rsp:
                data = json.loads(rsp.read())
            return data

        data, attempts = with_retries(call, model=self.model)
        choice = data["choices"][0]
        text = choice["message"]["content"].strip()
        usage = data.get("usage", {})

        # one repair round if the JSON does not validate
        try:
            parse_draft(text)
        except (ValidationError, ValueError) as e:
            repair_payload = json.dumps({
                "model": self.model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": usr_prompt},
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"Your previous answer was invalid: {str(e)[:800]}\nReturn corrected JSON only."},
                ],
                "temperature": 0,
                "max_tokens": 8192,
            }).encode()
            try:
                rq2 = urllib.request.Request(
                    "https://api.groq.com/openai/v1/chat/completions",
                    data=repair_payload,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                )
                with urllib.request.urlopen(rq2, timeout=60) as rsp2:
                    data2 = json.loads(rsp2.read())
                text = data2["choices"][0]["message"]["content"].strip()
                attempts += 1
                usage = data2.get("usage", usage)
            except Exception:
                pass  # keep original text, let caller handle parse error

        return text, CallMeta(
            backend=self.backend, model=self.model, attempts=attempts,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )
