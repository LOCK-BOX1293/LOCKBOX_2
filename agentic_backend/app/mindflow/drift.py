from __future__ import annotations

import math
import re
from collections import Counter

TRANSITION_PHRASES = [
    "actually",
    "instead",
    "wait",
    "let's talk about",
    "forget that",
    "new topic",
    "switch gears",
]

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "for",
    "on",
    "is",
    "it",
    "this",
    "that",
    "i",
    "we",
    "you",
    "me",
    "my",
    "our",
    "be",
    "with",
    "about",
    "can",
    "could",
    "should",
    "would",
}


def _tokenize(text: str) -> list[str]:
    return [
        t
        for t in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower())
        if t not in STOPWORDS
    ]


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b.get(k, 0) for k in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def score_drift(
    current_message: str,
    recent_text: str,
    centroid_terms: list[str],
) -> tuple[float, dict]:
    current_tokens = _tokenize(current_message)
    recent_tokens = _tokenize(recent_text)
    centroid_counter = Counter(centroid_terms)
    current_counter = Counter(current_tokens)
    recent_counter = Counter(recent_tokens)

    similarity_to_recent = _cosine(current_counter, recent_counter)
    similarity_to_centroid = _cosine(current_counter, centroid_counter)

    transition_hit = any(p in current_message.lower() for p in TRANSITION_PHRASES)
    new_domain_terms = [t for t in current_tokens if t not in centroid_counter]
    new_domain_ratio = (
        len(new_domain_terms) / len(current_tokens) if current_tokens else 0.0
    )

    low_similarity_signal = 1.0 - max(similarity_to_recent, similarity_to_centroid)
    transition_signal = 1.0 if transition_hit else 0.0
    novelty_signal = min(1.0, new_domain_ratio)

    score = (
        0.55 * low_similarity_signal + 0.30 * transition_signal + 0.15 * novelty_signal
    )
    diagnostics = {
        "similarity_to_recent": round(similarity_to_recent, 4),
        "similarity_to_centroid": round(similarity_to_centroid, 4),
        "transition_hit": transition_hit,
        "novelty_ratio": round(new_domain_ratio, 4),
    }
    return round(score, 4), diagnostics


def update_centroid_terms(
    centroid_terms: list[str], message: str, cap: int = 80
) -> list[str]:
    tokens = _tokenize(message)
    merged = centroid_terms + tokens
    if len(merged) <= cap:
        return merged
    return merged[-cap:]
