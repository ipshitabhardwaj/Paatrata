"""Load a source document into page-numbered text (needed to verify quotes)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SourceDoc:
    doc_id: str
    title: str
    mime_type: str
    data: bytes
    pages: list[str] = field(default_factory=list)
    url: str | None = None
    is_primary_source: bool = False

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @property
    def has_text(self) -> bool:
        return any(p.strip() for p in self.pages)

    def numbered_text(self) -> str:
        return "\n\n".join(f"=== PAGE {i} ===\n{t}" for i, t in enumerate(self.pages, start=1))


def _pdf_pages(data: bytes) -> list[str]:
    import io

    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return [(p.extract_text() or "") for p in pdf.pages]


def load_bytes(data: bytes, filename: str, url: str | None = None, is_primary_source: bool = False) -> SourceDoc:
    name = Path(filename).name
    suffix = Path(filename).suffix.lower()
    doc_id = hashlib.sha256(data).hexdigest()[:12]
    if suffix == ".pdf":
        mime, pages = "application/pdf", _pdf_pages(data)
    else:
        text = data.decode("utf-8", errors="replace")
        mime, pages = "text/plain", text.split("\f")
    return SourceDoc(doc_id=doc_id, title=name, mime_type=mime, data=data, pages=pages,
                     url=url, is_primary_source=is_primary_source)


def load_file(path: str | Path, url: str | None = None, is_primary_source: bool = False) -> SourceDoc:
    p = Path(path)
    return load_bytes(p.read_bytes(), p.name, url=url, is_primary_source=is_primary_source)


def load_text(text: str, title: str = "pasted.txt") -> SourceDoc:
    return load_bytes(text.encode("utf-8"), title)
