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



def get_settings() -> AppSettings:
    return AppSettings(
        mongodb_uri=os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
        mongodb_db=os.getenv("MONGODB_DB", "hackbite2"),
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "local"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "hash-v1"),
        embedding_dim=int(os.getenv("EMBEDDING_DIM", "1536")),
        embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "32")),
        chunk_target_tokens=int(os.getenv("CHUNK_TARGET_TOKENS", "220")),
        chunk_overlap_tokens=int(os.getenv("CHUNK_OVERLAP_TOKENS", "35")),
        index_top_k_default=int(os.getenv("INDEX_TOP_K_DEFAULT", "8")),
        rerank_enabled=os.getenv("RERANK_ENABLED", "true").lower() == "true",
        debug_log_vectors=os.getenv("DEBUG_LOG_VECTORS", "false").lower() == "true",
    )
