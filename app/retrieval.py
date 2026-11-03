"""Vector maths for masterclass M5: normalising, truncating, cosine search,
reciprocal rank fusion and paragraph chunking.

Pure Python on purpose. The embeddings come from `client.models.embed_content`;
everything after that is arithmetic you should be able to test without a
network or a vector database.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence


def _norm(vec: Sequence[float]) -> float:
    return math.sqrt(sum(v * v for v in vec))


def normalise(vec: Sequence[float]) -> list[float]:
    """Scale a vector to unit length so a dot product equals cosine similarity."""
    norm = _norm(vec)
    if norm == 0:
        raise ValueError("cannot normalise a zero vector")
    return [v / norm for v in vec]


def truncate(vec: Sequence[float], dims: int) -> list[float]:
    """Keep the first `dims` values and renormalise.

    Gemini embedding models are trained so that a prefix of the vector is
    itself a usable embedding (Matryoshka representation learning). A
    truncated prefix is no longer unit length, so it must be renormalised.
    """
    if not 0 < dims <= len(vec):
        raise ValueError(f"dims must be between 1 and {len(vec)}")
    return normalise(vec[:dims])


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"dimension mismatch: {len(a)} vs {len(b)}")
    na, nb = _norm(a), _norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)


def top_k(
    query: Sequence[float], index: Mapping[str, Sequence[float]], k: int = 3
) -> list[tuple[str, float]]:
    """Exact nearest neighbours by cosine similarity. Ties break by id."""
    if k < 1:
        raise ValueError("k must be at least 1")
    scored = [(doc_id, cosine(query, vec)) for doc_id, vec in index.items()]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored[:k]


def reciprocal_rank_fusion(
    rankings: Iterable[Sequence[str]], k: int = 60
) -> list[tuple[str, float]]:
    """Merge ranked lists (for example keyword and vector results).

    Each document scores sum(1 / (k + rank)) over the lists it appears in.
    Only ranks are used, so scores from different retrievers never need to be
    put on the same scale.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def chunk_paragraphs(text: str, max_chars: int = 1200) -> list[str]:
    """Pack whole paragraphs into chunks of at most `max_chars` characters.

    Paragraphs longer than the limit are split hard, so no chunk exceeds it.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(para[i : i + max_chars] for i in range(0, len(para), max_chars))
            continue
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    return chunks
