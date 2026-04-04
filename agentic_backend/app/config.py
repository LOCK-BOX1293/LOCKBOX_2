from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
PROMPTS_DIR = ROOT_DIR.parent / "prompts"

load_dotenv(ROOT_DIR.parent / ".env")


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    retrieval_service_url: str | None
    mongodb_uri: str | None
    mongodb_db: str
    retrieval_top_k: int



def get_settings() -> Settings:
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip(),
        retrieval_service_url=os.getenv("RETRIEVAL_SERVICE_URL", "").strip() or None,
        mongodb_uri=os.getenv("MONGODB_URI", "").strip() or None,
        mongodb_db=os.getenv("MONGODB_DB", "hackbite2").strip(),
        retrieval_top_k=int(os.getenv("RETRIEVAL_TOP_K", "8")),
    )
