from __future__ import annotations

import re


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def extract_candidates(user_text: str, assistant_text: str) -> list[dict]:
    candidates: list[dict] = []

    for sentence in split_sentences(user_text):
        low = sentence.lower()
        if "?" in sentence or low.startswith(("what", "how", "why", "when", "where")):
            candidates.append(
                {"type": "question", "title": sentence[:100], "content": sentence}
            )
            continue

        if any(k in low for k in ["should", "decide", "let's", "we will", "i will"]):
            candidates.append(
                {"type": "decision", "title": sentence[:100], "content": sentence}
            )
            continue

        if re.search(r"\b(step|todo|next|implement|build|fix|test)\b", low):
            candidates.append(
                {"type": "step", "title": sentence[:100], "content": sentence}
            )
            continue

        candidates.append(
            {"type": "concept", "title": sentence[:100], "content": sentence}
        )

    for sentence in split_sentences(assistant_text):
        low = sentence.lower()
        if re.search(r"\b(recommend|suggest|best|should)\b", low):
            candidates.append(
                {"type": "decision", "title": sentence[:100], "content": sentence}
            )
        elif re.search(r"\b(next|step|action|plan)\b", low):
            candidates.append(
                {"type": "step", "title": sentence[:100], "content": sentence}
            )

    dedup = []
    seen = set()
    for c in candidates:
        key = (c["type"], c["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        dedup.append(c)
    return dedup[:12]


def should_search(user_text: str) -> bool:
    low = user_text.lower()
    search_triggers = [
        "latest",
        "price",
        "pricing",
        "compare",
        "what is",
        "trend",
        "news",
        "benchmark",
        "official",
        "docs",
    ]
    return any(t in low for t in search_triggers)
