"""Deterministic eligibility evaluator.

Pure function: ``evaluate(rules, profile) -> Verdict``. No LLM, no I/O.
Uses Kleene three-valued logic so a missing fact yields NEEDS_INFO instead of a
guess:

    ALL: FALSE if any child FALSE, else UNKNOWN if any UNKNOWN, else TRUE
    ANY: TRUE  if any child TRUE,  else UNKNOWN if any UNKNOWN, else FALSE
"""
from __future__ import annotations

from typing import Any

from .schema import ConditionResult, Condition, RuleSet, Verdict
from .vocabulary import FIELDS

TRUE, FALSE, UNKNOWN = "TRUE", "FALSE", "UNKNOWN"


def _coerce(field: str, value: Any):
    spec = FIELDS.get(field)
    if value is None or spec is None:
        return value
    if spec.type == "number":
        return float(value)
    if spec.type == "boolean":
        if isinstance(value, str):
            return value.strip().lower() in {"true", "yes", "1"}
        return bool(value)
    if spec.type == "category":
        return str(value).strip().lower()
    return value


def eval_condition(cond: Condition, profile: dict[str, Any]) -> str:
    if cond.field not in profile or profile[cond.field] in (None, ""):
        return UNKNOWN
    actual = _coerce(cond.field, profile[cond.field])
    expected = cond.value
    op = cond.op
    if op == ">=":
        ok = actual >= float(expected)
    elif op == ">":
        ok = actual > float(expected)
    elif op == "<=":
        ok = actual <= float(expected)
    elif op == "<":
        ok = actual < float(expected)
    elif op == "==":
        ok = actual == _coerce(cond.field, expected)
    elif op == "!=":
        ok = actual != _coerce(cond.field, expected)
    elif op == "in":
        ok = actual in [str(v).lower() for v in expected]
    elif op == "not_in":
        ok = actual not in [str(v).lower() for v in expected]
    else:
        raise ValueError(f"unknown operator {op}")
    return TRUE if ok else FALSE


def _combine(logic: str, outcomes: list[str]) -> str:
    if logic == "ALL":
        if FALSE in outcomes:
            return FALSE
        return UNKNOWN if UNKNOWN in outcomes else TRUE
    if TRUE in outcomes:
        return TRUE
    return UNKNOWN if UNKNOWN in outcomes else FALSE


def root_group_id(rules: RuleSet) -> str:
    roots = [g.id for g in rules.groups if g.parent is None]
    if len(roots) != 1:
        raise ValueError(f"rules must have exactly one root group, found {roots}")
    return roots[0]


def evaluate(rules: RuleSet, profile: dict[str, Any]) -> Verdict:
    groups = {g.id: g for g in rules.groups}
    cond_out = {c.id: eval_condition(c, profile) for c in rules.conditions}

    def group_outcome(gid: str, seen: frozenset = frozenset()) -> str:
        if gid in seen:
            raise ValueError(f"cycle in groups at {gid}")
        children = [cond_out[c.id] for c in rules.conditions if c.group == gid]
        children += [group_outcome(g.id, seen | {gid}) for g in rules.groups if g.parent == gid]
        if not children:  # empty group is vacuous
            return TRUE if groups[gid].logic == "ALL" else FALSE
        return _combine(groups[gid].logic, children)

    top = group_outcome(root_group_id(rules))
    results = [
        ConditionResult(
            condition_id=c.id, field=c.field, op=c.op, expected=c.value,
            actual=profile.get(c.field), outcome=cond_out[c.id], citation=c.citation,
        )
        for c in rules.conditions
    ]
    verdict = {TRUE: "ELIGIBLE", FALSE: "NOT_ELIGIBLE", UNKNOWN: "NEEDS_INFO"}[top]
    # Unmapped (non-computable) conditions can never make someone ELIGIBLE on their own;
    # surface them so the UI says "also requires verification of ...".
    return Verdict(
        scheme_id=rules.scheme_id,
        verdict=verdict,
        missing_fields=sorted({r.field for r in results if r.outcome == UNKNOWN}),
        failed_conditions=[r.condition_id for r in results if r.outcome == FALSE],
        results=results,
        unmapped_conditions=rules.unmapped_conditions,
    )


def fields_used(rules: RuleSet) -> list[str]:
    seen: list[str] = []
    for c in rules.conditions:
        if c.field not in seen:
            seen.append(c.field)
    return seen
