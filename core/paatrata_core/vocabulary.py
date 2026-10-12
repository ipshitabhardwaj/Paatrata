"""Controlled vocabulary of computable eligibility fields.

Every condition the compiler accepts must use one of these fields. Anything else
goes to `unmapped_conditions` and needs a human. Add fields here (and only here)
when a new scheme needs them; the LLM schema, validator, evaluator and UI all
read from this table.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str  # "number" | "category" | "boolean"
    unit: str | None = None
    description: str = ""
    options: tuple[str, ...] = field(default_factory=tuple)  # for categories
    # sensible range used by the test generator and synthetic profiles
    min_value: float | None = None
    max_value: float | None = None


FIELDS: dict[str, FieldSpec] = {
    f.name: f
    for f in [
        FieldSpec("age_years", "number", "years", "Applicant age in completed years", min_value=0, max_value=100),
        FieldSpec(
            "family_annual_income_inr", "number", "INR",
            "Total annual income of the applicant's family from all sources, in rupees",
            min_value=0, max_value=1_000_000,
        ),
        FieldSpec(
            "applicant_annual_income_inr", "number", "INR",
            "Annual income of the applicant alone, in rupees", min_value=0, max_value=1_000_000,
        ),
        FieldSpec(
            "residence_years_in_jurisdiction", "number", "years",
            "Years the applicant has lived in the scheme's state/UT", min_value=0, max_value=60,
        ),
        FieldSpec("disability_percent", "number", "percent", "Certified disability percentage", min_value=0, max_value=100),
        FieldSpec("number_of_children", "number", "count", "Number of living children", min_value=0, max_value=10),
        FieldSpec(
            "gender", "category", None, "Gender of the applicant",
            options=("female", "male", "transgender"),
        ),
        FieldSpec(
            "marital_status", "category", None, "Marital status",
            options=("unmarried", "married", "widowed", "divorced", "separated", "deserted"),
        ),
        FieldSpec(
            "social_category", "category", None, "Social category",
            options=("general", "sc", "st", "obc", "ews"),
        ),
        FieldSpec("is_domicile_of_jurisdiction", "boolean", None, "Applicant is a resident/domicile of the scheme's state/UT"),
        FieldSpec("has_bpl_card", "boolean", None, "Household holds a BPL card"),
        FieldSpec("is_government_employee", "boolean", None, "Applicant is a serving government employee"),
        FieldSpec("receives_other_pension", "boolean", None, "Applicant already receives another government pension"),
        FieldSpec("is_student", "boolean", None, "Applicant is currently enrolled as a student"),
        FieldSpec("is_pregnant", "boolean", None, "Applicant is pregnant"),
        FieldSpec("is_lactating", "boolean", None, "Applicant is a lactating (breastfeeding) mother"),
        FieldSpec("applicant_is_legal_guardian", "boolean", None, "Applicant is the legal guardian of the beneficiary child"),
        FieldSpec("child_age_years", "number", "years", "Age of the beneficiary child in completed years", min_value=0, max_value=25),
        FieldSpec("child_receives_family_pension", "boolean", None, "The beneficiary child receives a family pension from any State/Central Government"),
        FieldSpec("child_in_institutional_care", "boolean", None, "The beneficiary child is in institutional care of government or an NGO"),
        FieldSpec("covered_under_epf", "boolean", None, "Applicant (or deceased member) is covered under EPF"),
        FieldSpec("board_membership_months", "number", "months", "Months the worker was a registered member of the welfare board", min_value=0, max_value=480),
        FieldSpec("months_since_spouse_death", "number", "months", "Months elapsed since the death of the spouse", min_value=0, max_value=240),
    ]
}

FIELD_NAMES: tuple[str, ...] = tuple(FIELDS.keys())

OPS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "number": (">=", ">", "<=", "<", "==", "!="),
    "category": ("==", "!=", "in", "not_in"),
    "boolean": ("==",),
}

ALL_OPS: tuple[str, ...] = (">=", ">", "<=", "<", "==", "!=", "in", "not_in")


def vocabulary_as_text() -> str:
    """Human/LLM readable description used inside prompts."""
    lines = []
    for f in FIELDS.values():
        extra = f" options={list(f.options)}" if f.options else ""
        unit = f" unit={f.unit}" if f.unit else ""
        lines.append(f"- {f.name} ({f.type}{unit}{extra}): {f.description}")
    return "\n".join(lines)
