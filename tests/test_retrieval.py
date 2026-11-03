from __future__ import annotations

import math

import pytest

from app.retrieval import (
    chunk_paragraphs,
    cosine,
    normalise,
    reciprocal_rank_fusion,
    top_k,
    truncate,
)


def test_normalise_gives_unit_length() -> None:
    vec = normalise([3.0, 4.0])
    assert vec == pytest.approx([0.6, 0.8])
    assert math.hypot(*vec) == pytest.approx(1.0)


def test_normalise_rejects_zero_vector() -> None:
    with pytest.raises(ValueError):
        normalise([0.0, 0.0])


def test_truncate_renormalises_the_prefix() -> None:
    vec = truncate([1.0, 1.0, 5.0], dims=2)
    assert vec == pytest.approx([1 / math.sqrt(2), 1 / math.sqrt(2)])
    with pytest.raises(ValueError):
        truncate([1.0], dims=2)


def test_cosine_handles_direction_and_mismatch() -> None:
    assert cosine([1.0, 0.0], [2.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0
    with pytest.raises(ValueError):
        cosine([1.0], [1.0, 2.0])


def test_top_k_orders_by_similarity_then_id() -> None:
    index = {"b": [1.0, 0.0], "a": [1.0, 0.0], "c": [0.0, 1.0]}
    assert [doc for doc, _ in top_k([1.0, 0.1], index, k=2)] == ["a", "b"]


def test_rrf_rewards_documents_ranked_by_both_retrievers() -> None:
    keyword = ["refund-policy", "shipping", "warranty"]
    vector = ["warranty", "refund-policy", "returns"]
    fused = [doc for doc, _ in reciprocal_rank_fusion([keyword, vector])]
    assert fused[0] == "refund-policy"
    assert set(fused) == {"refund-policy", "shipping", "warranty", "returns"}


def test_chunk_paragraphs_respects_the_limit() -> None:
    text = "alpha " * 10 + "\n\n" + "beta " * 10 + "\n\n" + "x" * 50
    chunks = chunk_paragraphs(text, max_chars=40)
    assert all(len(c) <= 40 for c in chunks)
    assert "".join(chunks).count("x") == 50
