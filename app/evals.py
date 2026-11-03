"""Scoring helpers for Stage 4.8 (extraction accuracy) and masterclass M6
(evaluation gates and judge calibration).

Model calls produce the `actual` values; these functions decide whether the
result is good enough. Keeping them pure makes the release gate testable.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


def normalise_value(value: Any) -> Any:
    """Make equivalent answers compare equal.

    Strings: trimmed, case-folded, internal whitespace collapsed.
    Floats: rounded to 2 decimal places. Lists: normalised element-wise and
    sorted, so order does not matter. Everything else is returned unchanged.
    """
    if isinstance(value, str):
        return " ".join(value.split()).casefold()
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, list | tuple):
        return tuple(sorted((normalise_value(v) for v in value), key=repr))
    return value


def field_matches(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> dict[str, bool]:
    """Per-field correctness for one record. Missing fields count as wrong."""
    return {
        key: key in actual and normalise_value(actual[key]) == normalise_value(want)
        for key, want in expected.items()
    }


def field_accuracy(
    cases: Iterable[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> dict[str, float]:
    """Fraction of cases where each field was right, over (expected, actual) pairs."""
    right: Counter[str] = Counter()
    seen: Counter[str] = Counter()
    for expected, actual in cases:
        for key, ok in field_matches(expected, actual).items():
            seen[key] += 1
            right[key] += ok
    return {key: right[key] / seen[key] for key in sorted(seen)}


@dataclass(frozen=True)
class GateResult:
    passed: bool
    regressions: dict[str, float] = field(default_factory=dict)
    below_floor: dict[str, float] = field(default_factory=dict)


def gate(
    baseline: Mapping[str, float],
    candidate: Mapping[str, float],
    *,
    max_drop: float = 0.02,
    floors: Mapping[str, float] | None = None,
) -> GateResult:
    """Block a prompt or model change that regresses any metric.

    A metric fails if it drops by more than `max_drop` from the baseline, or
    if it lands under its absolute floor. Metrics missing from the candidate
    count as 0.0, so a broken run can never pass by omission.
    """
    regressions = {
        name: round(base - candidate.get(name, 0.0), 4)
        for name, base in baseline.items()
        if base - candidate.get(name, 0.0) > max_drop
    }
    below = {
        name: candidate.get(name, 0.0)
        for name, minimum in (floors or {}).items()
        if candidate.get(name, 0.0) < minimum
    }
    passed = not regressions and not below
    return GateResult(passed=passed, regressions=regressions, below_floor=below)


def cohens_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Agreement between two labellers corrected for chance.

    Use it to check an LLM judge against human labels: raw agreement looks
    high when one label dominates, kappa does not.
    """
    if len(a) != len(b) or not a:
        raise ValueError("label lists must be non-empty and the same length")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    count_a, count_b = Counter(a), Counter(b)
    expected = sum(count_a[label] * count_b[label] for label in count_a) / (n * n)
    if expected == 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)
