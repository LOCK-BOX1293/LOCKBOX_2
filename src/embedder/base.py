from abc import ABC, abstractmethod
from typing import List
from src.core.config import settings, logger
from src.security import build_armoriq_client
import time

class BaseEmbedder(ABC):
    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        pass

    def embed_queries(self, queries: List[str]) -> List[List[float]]:
        # Sometimes query embedding differs from document embedding
        return self.embed_texts(queries)

class LocalEmbedder(BaseEmbedder):
    def __init__(self):
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading Local Embedder Model", model=settings.embedding_model)
            self.model = SentenceTransformer(settings.embedding_model)
        except Exception as e:
            logger.error("Failed to load sentence-transformers. Check if it is installed.", error=str(e))
            raise

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        
        # sentence-transformers outputs NumPy arrays, so we convert to float lists
        embeddings = self.model.encode(texts, batch_size=settings.embedding_batch_size, show_progress_bar=False)
        return [e.tolist() for e in embeddings]

class OpenAIEmbedder(BaseEmbedder):
    def __init__(self):
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set when using openai embedding provider")
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=settings.openai_api_key)
            self.model = settings.embedding_model
            self.armoriq = build_armoriq_client()
        except Exception as e:
            logger.error("Failed to initialize OpenAI client.", error=str(e))
            raise

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self.armoriq:
            texts = [
                self.armoriq.sanitize_text(
                    text,
                    provider="openai",
                    model=self.model,
                    operation="embedding",
                )
                for text in texts
            ]
        
        # Handling retry and backoff in batch
        max_retries = 3
        for attempt in range(max_retries):
            try:
                res = self.client.embeddings.create(input=texts, model=self.model)
                embeddings = [data.embedding for data in res.data]
                return embeddings
            except Exception as e:
                logger.warning(f"OpenAI embedding failed attempt {attempt+1}/{max_retries}", error=str(e))
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
        return []

class GoogleEmbedder(BaseEmbedder):
    def __init__(self):
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY must be set when using google embedding provider")
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.google_api_key)
            self.model = settings.embedding_model
            self.armoriq = build_armoriq_client()
        except Exception as e:
            logger.error("Failed to initialize Google Generative AI client.", error=str(e))
            raise

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self.armoriq:
            texts = [
                self.armoriq.sanitize_text(
                    text,
                    provider="google",
                    model=self.model,
                    operation="embedding",
                )
                for text in texts
            ]
        
        import google.generativeai as genai
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # The texts need to go into the generic `content` mapping, but `embed_content` accepts List[str]
                # It returns a dictionary `{'embedding': [[...], [...]]}` or similar list depending on batching
                result = genai.embed_content(
                    model=self.model,
                    content=texts,
                    task_type="retrieval_document"
                )
                embeddings = result.get('embedding', [])
                if isinstance(embeddings, list) and len(embeddings) > 0 and not isinstance(embeddings[0], list):
                    # In case of single text string or edge case packaging, wrap it properly but the API gives List[List[float]] for batch texts
                    return [embeddings]
                return embeddings
            except Exception as e:
                logger.warning(f"Google embedding failed attempt {attempt+1}/{max_retries}", error=str(e))
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
        return []

def get_embedder() -> BaseEmbedder:
    if settings.embedding_provider == "local":
        return LocalEmbedder()
    elif settings.embedding_provider == "openai":
        return OpenAIEmbedder()
    elif settings.embedding_provider == "google":
        return GoogleEmbedder()
    else:
        raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")
