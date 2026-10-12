"""Look up scheme ids and provenance from samples/sources/sources.csv."""
import csv
from pathlib import Path
from typing import Optional


def read_sources(csv_path: Path) -> list[dict[str, str]]:
    if not Path(csv_path).exists():
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def lookup(filename: str, csv_path: Path) -> Optional[dict[str, str]]:
    """Row for a source file name (case-insensitive basename match), or None."""
    name = str(filename).replace("\\", "/").rsplit("/", 1)[-1].lower()
    return next((r for r in read_sources(csv_path) if r.get("file", "").lower() == name), None)
