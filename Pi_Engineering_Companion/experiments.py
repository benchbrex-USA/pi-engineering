"""Small deterministic calculations used in the Pi Engineering course."""
from __future__ import annotations
import math


def reciprocal_rank_fusion(rankings: list[list[str]], c: float = 60.0) -> list[tuple[str, float]]:
    if c < 0:
        raise ValueError("c must be nonnegative")
    scores: dict[str, float] = {}
    for ranking in rankings:
        if len(set(ranking)) != len(ranking):
            raise ValueError("a ranked list cannot contain duplicate IDs")
        for rank, doc in enumerate(ranking, 1):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (c + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


def recall_at_k(ranking: list[str], relevant: set[str], k: int) -> float:
    if k < 1 or not relevant:
        raise ValueError("k and relevant set must be nonempty")
    return len(set(ranking[:k]) & relevant) / len(relevant)


def reciprocal_rank(ranking: list[str], relevant: set[str]) -> float:
    return next((1.0 / i for i, doc in enumerate(ranking, 1) if doc in relevant), 0.0)


def wilson_interval(successes: int, n: int, z: float = 1.95996398454) -> tuple[float, float]:
    if type(n) is not int or type(successes) is not int or n <= 0 or not 0 <= successes <= n or z <= 0:
        raise ValueError("invalid binomial inputs")
    p = successes / n
    denominator = 1.0 + z*z/n
    center = (p + z*z/(2*n)) / denominator
    radius = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denominator
    return max(0.0, center-radius), min(1.0, center+radius)


def kv_cache_bytes(layers: int, kv_heads: int, head_dim: int, tokens: int,
                   batch: int, bytes_per_element: int) -> int:
    values = (layers, kv_heads, head_dim, tokens, batch, bytes_per_element)
    if any(type(x) is not int or x < 1 for x in values):
        raise ValueError("all dimensions must be positive integers")
    return 2 * math.prod(values)


if __name__ == "__main__":
    print("RRF:", reciprocal_rank_fusion([["A", "B", "C"], ["B", "D", "A"]]))
    print("Wilson 90/100:", wilson_interval(90, 100))
    print("KV GiB:", kv_cache_bytes(32, 8, 128, 8192, 4, 2) / 2**30)
