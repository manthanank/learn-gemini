"""Token cost maths used in Stage 3 (caching break-even) and M4 (routing).

Prices are passed in, never hard-coded: they change between models and over
time. All prices are USD per one million tokens; cache storage is USD per one
million tokens per hour.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

PER_MILLION = 1_000_000


@dataclass(frozen=True)
class Prices:
    """USD per one million tokens. Storage is USD per one million tokens per hour."""

    input: float
    cached_input: float
    output: float
    cache_storage_per_hour: float = 0.0

    def __post_init__(self) -> None:
        for name in ("input", "cached_input", "output", "cache_storage_per_hour"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")


def request_cost(
    prices: Prices,
    *,
    prompt_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    thinking_tokens: int = 0,
) -> float:
    """Cost of one request from its usage numbers.

    `prompt_tokens` is the full prompt as reported by `usage_metadata`, which
    already includes any cached tokens. Thinking tokens are billed as output.
    """
    if min(prompt_tokens, output_tokens, cached_tokens, thinking_tokens) < 0:
        raise ValueError("token counts must not be negative")
    if cached_tokens > prompt_tokens:
        raise ValueError("cached_tokens cannot exceed prompt_tokens")
    fresh = prompt_tokens - cached_tokens
    usd = (
        fresh * prices.input
        + cached_tokens * prices.cached_input
        + (output_tokens + thinking_tokens) * prices.output
    )
    return usd / PER_MILLION


def context_cost(
    prices: Prices,
    *,
    context_tokens: int,
    queries: int,
    hours: float,
    cached: bool,
    creation_billed: bool = True,
) -> float:
    """Cost of the shared context alone across `queries` questions.

    Question and answer tokens cost the same with or without a cache, so they
    are left out; this isolates what caching changes.
    """
    if context_tokens < 0 or queries < 0 or hours < 0:
        raise ValueError("inputs must not be negative")
    millions = context_tokens / PER_MILLION
    if not cached:
        return queries * millions * prices.input
    total = queries * millions * prices.cached_input
    total += millions * prices.cache_storage_per_hour * hours
    if creation_billed:
        total += millions * prices.input
    return total


def break_even_queries(prices: Prices, hours: float, *, creation_billed: bool = True) -> int:
    """Smallest number of queries for which an explicit cache is strictly cheaper.

    Caching wins when n * (p_in - p_cached) > p_in + storage * hours.
    The context size cancels out, so it is not a parameter.
    """
    if hours < 0:
        raise ValueError("hours must not be negative")
    saving_per_query = prices.input - prices.cached_input
    if saving_per_query <= 0:
        raise ValueError("cached input must be cheaper than input")
    overhead = prices.cache_storage_per_hour * hours
    if creation_billed:
        overhead += prices.input
    return math.floor(overhead / saving_per_query) + 1
