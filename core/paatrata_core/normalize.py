"""Deterministic value normalisation (the model writes text, code makes numbers).

Handles forms that appear in Indian scheme documents:
"1,50,000", "Rs. 1.5 lakh", "₹2 lakhs", "one lakh fifty thousand", "sixty", "60 years",
"2.5 crore", "15k".
"""
from __future__ import annotations

import re

from .vocabulary import FIELDS

_UNITS = {
    "thousand": 1_000,
    "k": 1_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "cr": 10_000_000,
}

_SMALL = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALE_WORDS = {"hundred": 100, "thousand": 1_000, "lakh": 100_000, "lakhs": 100_000,
                "lac": 100_000, "crore": 10_000_000, "crores": 10_000_000}


class NormalizationError(ValueError):
    pass


def _words_to_number(text: str) -> float | None:
    tokens = re.findall(r"[a-z]+", text.lower())
    tokens = [t for t in tokens if t not in {"and", "rs", "rupees", "inr", "only", "years", "year", "of", "age"}]
    if not tokens or not all(t in _SMALL or t in _SCALE_WORDS for t in tokens):
        return None
    total, current = 0, 0
    for t in tokens:
        if t in _SMALL:
            current += _SMALL[t]
        elif t == "hundred":
            current = (current or 1) * 100
        else:
            total += (current or 1) * _SCALE_WORDS[t]
            current = 0
    return float(total + current)


def parse_number(text: str) -> float:
    """Parse a number written in any of the common Indian styles."""
    if text is None:
        raise NormalizationError("empty value")
    s = str(text).strip().lower()
    s = s.replace("₹", " ").replace("/-", " ")
    s = re.sub(r"\b(rs\.?|inr|rupees|per annum|p\.a\.)", " ", s)
    s = s.strip()
    words = None if re.search(r"\d", s) else _words_to_number(s)
    if words is not None:
        return words
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(thousand|lakhs?|lacs?|crores?|cr|k)?\b", s)
    if not m:
        raise NormalizationError(f"no number found in {text!r}")
    num = float(m.group(1).replace(",", ""))
    unit = m.group(2)
    if unit:
        num *= _UNITS[unit]
    return num


def parse_bool(text: str) -> bool:
    s = str(text).strip().lower()
    if s in {"true", "yes", "y", "1", "required", "must"}:
        return True
    if s in {"false", "no", "n", "0", "not required", "must not"}:
        return False
    raise NormalizationError(f"not a boolean: {text!r}")


def parse_category(text: str, field: str, many: bool) -> str | list[str]:
    spec = FIELDS[field]
    raw = [p.strip().lower() for p in re.split(r"[,/;|]| or ", str(text)) if p.strip()]
    aliases = {"widow": "widowed", "widower": "widowed", "divorcee": "divorced", "women": "female",
               "woman": "female", "men": "male", "man": "male", "single": "unmarried"}
    vals = [aliases.get(v, v) for v in raw]
    bad = [v for v in vals if spec.options and v not in spec.options]
    if bad:
        raise NormalizationError(f"{bad} not in options {list(spec.options)} for {field}")
    if many:
        return vals
    if len(vals) != 1:
        raise NormalizationError(f"expected one option for {field}, got {vals}")
    return vals[0]


def normalize_value(field: str, op: str, value: str, value_as_written: str | None = None):
    """Return a typed value for (field, op). Tries `value`, then `value_as_written`."""
    spec = FIELDS[field]
    last_err: Exception | None = None
    for candidate in (value, value_as_written):
        if candidate is None or str(candidate).strip() == "":
            continue
        try:
            if spec.type == "number":
                return parse_number(candidate)
            if spec.type == "boolean":
                return parse_bool(candidate)
            return parse_category(candidate, field, many=op in ("in", "not_in"))
        except NormalizationError as e:  # try next candidate
            last_err = e
    raise NormalizationError(str(last_err) if last_err else "no value")
