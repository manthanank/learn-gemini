from __future__ import annotations

import pytest

from app.evals import cohens_kappa, field_accuracy, field_matches, gate, normalise_value


def test_normalise_value_ignores_case_space_and_order() -> None:
    assert normalise_value("  ACME   Holdings ") == "acme holdings"
    assert normalise_value(1240.499) == 1240.5
    assert normalise_value(["b", "A"]) == normalise_value(["a", "B"])


def test_missing_fields_count_as_wrong() -> None:
    assert field_matches({"total": 10.0, "currency": "EUR"}, {"total": 10.0}) == {
        "total": True,
        "currency": False,
    }


def test_field_accuracy_per_field() -> None:
    cases = [
        ({"vendor": "Acme", "total": 99.5}, {"vendor": "ACME", "total": 99.5}),
        ({"vendor": "Initech", "total": 12.0}, {"vendor": "Initech", "total": 21.0}),
    ]
    assert field_accuracy(cases) == {"total": 0.5, "vendor": 1.0}


def test_gate_blocks_regressions_and_floors() -> None:
    baseline = {"vendor": 0.98, "total": 0.95}
    assert gate(baseline, {"vendor": 0.97, "total": 0.96}).passed
    failed = gate(baseline, {"vendor": 0.90, "total": 0.96}, floors={"total": 0.97})
    assert not failed.passed
    assert failed.regressions == {"vendor": 0.08}
    assert failed.below_floor == {"total": 0.96}


def test_gate_treats_missing_metric_as_zero() -> None:
    assert not gate({"vendor": 0.9}, {}).passed


def test_kappa_is_low_when_agreement_is_only_chance() -> None:
    human = ["pass"] * 9 + ["fail"]
    judge = ["pass"] * 10
    assert cohens_kappa(human, judge) == pytest.approx(0.0)
    assert cohens_kappa(["a", "b"], ["a", "b"]) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        cohens_kappa([], [])
