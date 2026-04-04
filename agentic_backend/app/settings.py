from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR.parent / ".env")


@dataclass(frozen=True)
class AppSettings:
    mongodb_uri: str
    mongodb_db: str
    embedding_provider: str
    embedding_model: str
    embedding_dim: int
    embedding_batch_size: int
    chunk_target_tokens: int
    chunk_overlap_tokens: int
    index_top_k_default: int
    rerank_enabled: bool
    debug_log_vectors: bool


def _clean_env(value: str | None, default: str) -> str:
    raw = (value or default).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
        return raw[1:-1]
    return raw


def get_settings() -> AppSettings:
    mongo_uri = _clean_env(
        os.getenv("MONGODB_URI") or os.getenv("MONGODB_URI_HACKBITE2"),
        "mongodb://localhost:27017",
    )
    mongo_db_env = os.getenv("MONGODB_DB") or os.getenv("MONGODB_DB_HACKBITE2")
    mongo_db = _clean_env(
        mongo_db_env,
        "hackbite2",
    )

    return AppSettings(
        mongodb_uri=mongo_uri,
        mongodb_db=mongo_db,
        embedding_provider=_clean_env(os.getenv("EMBEDDING_PROVIDER"), "local"),
        embedding_model=_clean_env(os.getenv("EMBEDDING_MODEL"), "hash-v1"),
        embedding_dim=int(os.getenv("EMBEDDING_DIM", "1536")),
        embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "32")),
        chunk_target_tokens=int(os.getenv("CHUNK_TARGET_TOKENS", "220")),
        chunk_overlap_tokens=int(os.getenv("CHUNK_OVERLAP_TOKENS", "35")),
        index_top_k_default=int(os.getenv("INDEX_TOP_K_DEFAULT", "8")),
        rerank_enabled=_clean_env(os.getenv("RERANK_ENABLED"), "true").lower()
        == "true",
        debug_log_vectors=_clean_env(os.getenv("DEBUG_LOG_VECTORS"), "false").lower()
        == "true",
    )
