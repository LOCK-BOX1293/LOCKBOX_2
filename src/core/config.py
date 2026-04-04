import logging
import sys
from typing import Literal, Optional

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "hackbite2"
    
    embedding_provider: Literal["local", "openai", "vertex", "google"] = "local"
    embedding_model: str = "all-MiniLM-L6-v2"  # default for local sentence-transformers
    embedding_dim: int = 384
    embedding_batch_size: int = 100
    
    chunk_target_tokens: int = 500
    chunk_overlap_tokens: int = 50
    
    index_top_k_default: int = 5
    rerank_enabled: bool = False

    superplane_base_url: Optional[str] = None
    guard_min_confidence: float = 0.35

    # OpenAI specific (if selected)
    openai_api_key: Optional[str] = None
    
    # Google specific
    google_api_key: Optional[str] = None
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

settings = Settings()

def configure_logging():
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

configure_logging()
logger = structlog.get_logger()
