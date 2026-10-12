"""Boundary test generation.

From a RuleSet, build profiles that sit exactly on and just past every numeric
threshold, flip every category/boolean, and drop each field. Expected verdicts
come from a *reference* rule set:

* officer review:  reference = the draft itself -> a readable table of
  "a 59-year-old is NOT_ELIGIBLE, a 60-year-old is ELIGIBLE" to sanity-check
  and keep as regression tests when the rules change.
* evaluation:      reference = gold rules, run against extracted rules ->
  decision accuracy where it matters most (the boundaries).
"""

import copy
import random
from typing import Any

from pydantic import BaseModel

from .evaluator import evaluate, root_group_id
from .schema import Condition, RuleSet
from .vocabulary import FIELDS


class TestCase(BaseModel):
    id: str
    description: str
    profile: dict[str, Any]
    expected: str
    origin: str = "generated"


class TestResult(BaseModel):
    test: TestCase
    actual: str
    passed: bool


def _step(field: str) -> float:
    return 1.0  # ages, years, rupees, percent, counts are all integer-stepped in practice


def _satisfying_value(c: Condition):
    spec = FIELDS[c.field]
    v = c.value
    if spec.type == "number":
        v = float(v)
        return {">=": v, ">": v + _step(c.field), "<=": v, "<": v - _step(c.field),
                "==": v, "!=": v + _step(c.field)}[c.op]
    if spec.type == "boolean":
        return bool(v)
    opts = list(spec.options)
    if c.op == "==":
        return v
    if c.op == "in":
        return v[0]
    if c.op == "!=":
        return next(o for o in opts if o != v)
    if c.op == "not_in":
        return next(o for o in opts if o not in v)
    raise ValueError(c.op)


def _violating_values(c: Condition) -> list[Any]:
    spec = FIELDS[c.field]
    v = c.value
    if spec.type == "number":
        v = float(v)
        s = _step(c.field)
        return {">=": [v - s], ">": [v], "<=": [v + s], "<": [v], "==": [v - s, v + s], "!=": [v]}[c.op]
    if spec.type == "boolean":
        return [not bool(v)]
    opts = list(spec.options)
    if c.op == "==":
        return [o for o in opts if o != v][:1]
    if c.op == "in":
        return [o for o in opts if o not in v][:1]
    if c.op == "!=":
        return [v]
    if c.op == "not_in":
        return [v[0]]
    return []


def satisfying_profile(rules: RuleSet) -> dict[str, Any] | None:
    """Try to build one ELIGIBLE profile by picking a branch per ANY group."""
    groups = {g.id: g for g in rules.groups}
    children_groups = {g.id: [x.id for x in rules.groups if x.parent == g.id] for g in rules.groups}
    children_conds = {g.id: [c for c in rules.conditions if c.group == g.id] for g in rules.groups}

    def options(gid: str) -> list[dict[str, Any]]:
        kids: list[list[dict[str, Any]]] = []
        for c in children_conds[gid]:
            kids.append([{c.field: _satisfying_value(c)}])
        for sub in children_groups[gid]:
            kids.append(options(sub))
        if groups[gid].logic == "ANY":
            return [o for k in kids for o in k] or [{}]
        combos: list[dict[str, Any]] = [{}]
        for k in kids:
            combos = [{**a, **b} for a in combos for b in k][:64]
        return combos

    for cand in options(root_group_id(rules)):
        if evaluate(rules, cand).verdict == "ELIGIBLE":
            return _complete(rules, cand)
    return None


def _complete(rules: RuleSet, profile: dict[str, Any]) -> dict[str, Any]:
    """Give every remaining field a value that keeps the profile ELIGIBLE (prefer values that
    fail the unused ANY branches), so single-field changes flip the verdict instead of
    turning it into NEEDS_INFO."""
    out = dict(profile)
    for c in rules.conditions:
        if c.field in out:
            continue
        for val in _violating_values(c) + [_satisfying_value(c)]:
            trial = {**out, c.field: val}
            if evaluate(rules, trial).verdict == "ELIGIBLE":
                out = trial
                break
    return out


def generate_tests(rules: RuleSet, reference: RuleSet | None = None, origin: str = "generated") -> list[TestCase]:
    reference = reference or rules
    base = satisfying_profile(rules) or {}
    tests: list[TestCase] = []
    n = 0

    def add(desc: str, profile: dict[str, Any]):
        nonlocal n
        n += 1
        tests.append(TestCase(id=f"t{n}", description=desc, profile=profile,
                              expected=evaluate(reference, profile).verdict, origin=origin))

    if base:
        add("All conditions satisfied", dict(base))
    for c in rules.conditions:
        on = copy.deepcopy(base)
        on[c.field] = _satisfying_value(c)
        add(f"{c.field} {c.op} {c.value}: boundary, satisfied ({on[c.field]})", on)
        for bad in _violating_values(c):
            off = copy.deepcopy(base)
            off[c.field] = bad
            add(f"{c.field} {c.op} {c.value}: just violated ({bad})", off)
        missing = {k: v for k, v in base.items() if k != c.field}
        add(f"{c.field} missing", missing)
    # dedupe identical profiles
    unique, seen = [], set()
    for t in tests:
        key = tuple(sorted((k, str(v)) for k, v in t.profile.items()))
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


def run_tests(rules: RuleSet, tests: list[TestCase]) -> list[TestResult]:
    out = []
    for t in tests:
        actual = evaluate(rules, t.profile).verdict
        out.append(TestResult(test=t, actual=actual, passed=actual == t.expected))
    return out


def random_profiles(rules_list: list[RuleSet], n: int, seed: int = 7, boundary_share: float = 0.5) -> list[dict[str, Any]]:
    """Synthetic profiles over the fields used by `rules_list`, oversampled near thresholds.

    SYNTHETIC: these are not real people; use only for measuring agreement.
    """
    rng = random.Random(seed)
    thresholds: dict[str, list[float]] = {}
    fields: list[str] = []
    for r in rules_list:
        for c in r.conditions:
            if c.field not in fields:
                fields.append(c.field)
            if FIELDS[c.field].type == "number":
                thresholds.setdefault(c.field, []).append(float(c.value))
    profiles = []
    for _ in range(n):
        p: dict[str, Any] = {}
        for f in fields:
            spec = FIELDS[f]
            if rng.random() < 0.05:
                continue  # leave some fields missing
            if spec.type == "number":
                if thresholds.get(f) and rng.random() < boundary_share:
                    t = rng.choice(thresholds[f])
                    p[f] = t + rng.choice([-2, -1, 0, 1, 2]) * _step(f)
                else:
                    p[f] = float(rng.randint(int(spec.min_value or 0), int(spec.max_value or 100)))
            elif spec.type == "boolean":
                p[f] = rng.random() < 0.6
            else:
                p[f] = rng.choice(spec.options)
        profiles.append(p)
    return profiles
