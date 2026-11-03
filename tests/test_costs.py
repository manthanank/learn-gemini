from __future__ import annotations

import pytest

from app.costs import Prices, break_even_queries, context_cost, request_cost

# Illustrative prices, the same ones the README uses in section 3.8.
PRICES = Prices(input=0.30, cached_input=0.03, output=2.50, cache_storage_per_hour=1.00)


def test_request_cost_bills_thinking_as_output() -> None:
    plain = request_cost(PRICES, prompt_tokens=1_000, output_tokens=500)
    thinking = request_cost(PRICES, prompt_tokens=1_000, output_tokens=500, thinking_tokens=500)
    assert plain == pytest.approx((1_000 * 0.30 + 500 * 2.50) / 1_000_000)
    assert thinking - plain == pytest.approx(500 * 2.50 / 1_000_000)


def test_request_cost_discounts_cached_tokens() -> None:
    full = request_cost(PRICES, prompt_tokens=100_000, output_tokens=0)
    cached = request_cost(PRICES, prompt_tokens=100_000, output_tokens=0, cached_tokens=90_000)
    assert full == pytest.approx(0.03)
    assert cached == pytest.approx((10_000 * 0.30 + 90_000 * 0.03) / 1_000_000)


def test_request_cost_rejects_impossible_usage() -> None:
    with pytest.raises(ValueError):
        request_cost(PRICES, prompt_tokens=10, output_tokens=0, cached_tokens=11)
    with pytest.raises(ValueError):
        request_cost(PRICES, prompt_tokens=-1, output_tokens=0)


@pytest.mark.parametrize(("hours", "expected"), [(1, 5), (2, 9), (8, 31)])
def test_break_even_matches_readme(hours: float, expected: int) -> None:
    assert break_even_queries(PRICES, hours=hours) == expected


def test_break_even_is_the_first_query_count_where_caching_wins() -> None:
    n = break_even_queries(PRICES, hours=3)
    for queries, should_win in ((n - 1, False), (n, True)):
        cached = context_cost(PRICES, context_tokens=50_000, queries=queries, hours=3, cached=True)
        plain = context_cost(PRICES, context_tokens=50_000, queries=queries, hours=3, cached=False)
        assert (cached < plain) is should_win


def test_break_even_does_not_depend_on_context_size() -> None:
    n = break_even_queries(PRICES, hours=1)
    for size in (10_000, 200_000, 900_000):
        cached = context_cost(PRICES, context_tokens=size, queries=n, hours=1, cached=True)
        plain = context_cost(PRICES, context_tokens=size, queries=n, hours=1, cached=False)
        assert cached < plain


def test_readme_worked_example() -> None:
    uncached = context_cost(PRICES, context_tokens=200_000, queries=50, hours=1, cached=False)
    cached = context_cost(PRICES, context_tokens=200_000, queries=50, hours=1, cached=True)
    assert round(uncached, 2) == 3.00
    assert round(cached, 2) == 0.56


def test_without_creation_charge_break_even_is_lower() -> None:
    assert break_even_queries(PRICES, hours=1, creation_billed=False) == 4


def test_invalid_prices_are_rejected() -> None:
    with pytest.raises(ValueError):
        Prices(input=-1, cached_input=0, output=0)
    with pytest.raises(ValueError):
        break_even_queries(Prices(input=0.1, cached_input=0.1, output=0.4), hours=1)
