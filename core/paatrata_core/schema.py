"""Rule schema.

Two layers:

* ``SchemeDraft``  - what an LLM is asked to produce. Flat (groups reference a
  parent id) so it works with Gemini structured output without recursion, and
  values are kept as text so *code*, not the model, does the number parsing.
* ``RuleSet``      - the validated, typed, versioned rules the deterministic
  evaluator runs. Also flat, so a reviewer can edit it as a table.

Both are plain Pydantic models; ``SchemeDraft`` is passed to Gemini as the
response schema.
"""

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

from .vocabulary import ALL_OPS, FIELD_NAMES

SCHEMA_VERSION = "0.1"

FieldName = Literal.__getitem__(FIELD_NAMES)  # type: ignore[attr-defined]
Op = Literal.__getitem__(ALL_OPS)  # type: ignore[attr-defined]
Logic = Literal["ALL", "ANY"]


# --------------------------------------------------------------------------- #
# LLM-facing draft
# --------------------------------------------------------------------------- #
class DraftGroup(BaseModel):
    id: str = Field(description="Short id, e.g. 'root', 'age_or_widow'. Exactly one group must be 'root'.")
    logic: Logic = Field(description="ALL = every child must hold; ANY = at least one child must hold.")
    parent: Optional[str] = Field(default=None, description="Parent group id; null only for 'root'.")


class DraftCondition(BaseModel):
    id: str = Field(description="Short unique id, e.g. 'c1'.")
    group: str = Field(description="Id of the group this condition belongs to.")
    field: FieldName = Field(description="One field from the controlled vocabulary.")
    op: Op = Field(description="Comparison operator.")
    value: str = Field(
        description=(
            "Normalised value as text: a plain number for numeric fields (e.g. '150000', '60'), "
            "an option for categories (e.g. 'widowed'), comma-separated options for in/not_in, "
            "'true'/'false' for booleans."
        )
    )
    value_as_written: str = Field(description="The value exactly as the source writes it, e.g. 'Rs. 1.5 lakh'.")
    quote: str = Field(description="Verbatim sentence or phrase from the source that states this condition.")
    page: int = Field(description="1-based page number of the quote.")
    confidence: float = Field(description="0-1: how sure you are this condition is stated as encoded.")
    ambiguity: Optional[str] = Field(
        default=None,
        description="If the source is unclear (undefined term, conflicting statements), a question for the officer; else null.",
    )


class UnmappedCondition(BaseModel):
    text: str = Field(description="The condition in plain words.")
    quote: str = Field(description="Verbatim source text.")
    page: int
    reason: str = Field(description="Why it cannot be expressed with the vocabulary.")


class SchemeDraft(BaseModel):
    scheme_name: str
    department: Optional[str] = None
    jurisdiction: Optional[str] = Field(default=None, description="State/UT or 'Central'.")
    benefit_summary: Optional[str] = None
    groups: list[DraftGroup]
    conditions: list[DraftCondition]
    unmapped_conditions: list[UnmappedCondition] = Field(default_factory=list)
    documents_required: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Validated rules
# --------------------------------------------------------------------------- #
Value = Union[bool, float, str, list[str]]


class Citation(BaseModel):
    doc_id: Optional[str] = None
    page: int
    quote: str
    verified: bool = False  # quote found in source text by the validator
    match_score: float = 0.0


class Condition(BaseModel):
    id: str
    group: str
    field: str
    op: str
    value: Value
    citation: Citation
    confidence: float = 1.0
    ambiguity: Optional[str] = None
    ambiguity_resolution: Optional[str] = None


class Group(BaseModel):
    id: str
    logic: Logic
    parent: Optional[str] = None


class Issue(BaseModel):
    level: Literal["error", "warning", "info"]
    code: str
    message: str
    condition_id: Optional[str] = None


class RuleSet(BaseModel):
    schema_version: str = SCHEMA_VERSION
    scheme_id: str
    scheme_name: str
    department: Optional[str] = None
    jurisdiction: Optional[str] = None
    benefit_summary: Optional[str] = None
    groups: list[Group]
    conditions: list[Condition]
    unmapped_conditions: list[UnmappedCondition] = Field(default_factory=list)
    documents_required: list[str] = Field(default_factory=list)
    source_doc_ids: list[str] = Field(default_factory=list)
    extractor: str = "manual"  # gemini:<model> | gemma:<model> | manual | gold


class ConditionResult(BaseModel):
    condition_id: str
    field: str
    op: str
    expected: Value
    actual: Optional[Value] = None
    outcome: Literal["TRUE", "FALSE", "UNKNOWN"]
    citation: Citation


class Verdict(BaseModel):
    scheme_id: str
    verdict: Literal["ELIGIBLE", "NOT_ELIGIBLE", "NEEDS_INFO"]
    missing_fields: list[str] = Field(default_factory=list)
    failed_conditions: list[str] = Field(default_factory=list)
    results: list[ConditionResult]
    unmapped_conditions: list[UnmappedCondition] = Field(default_factory=list)
    disclaimer: str = "Informational only. This is not an official eligibility decision."
