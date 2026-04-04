from __future__ import annotations

import hashlib
import json
import math
import random
import time
from abc import ABC, abstractmethod
from urllib import parse
from urllib import request


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class LocalHashEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str, dimension: int) -> None:
        self.model = model
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            seed_bytes = hashlib.sha256(f"{self.model}:{text}".encode("utf-8")).digest()
            seed = int.from_bytes(seed_bytes[:8], "big", signed=False)
            rnd = random.Random(seed)
            vec = [rnd.uniform(-1.0, 1.0) for _ in range(self._dimension)]
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str, dimension: int) -> None:
        import os

        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for EMBEDDING_PROVIDER=openai"
            )
        self.api_key = api_key
        self.model = model
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.model, "input": texts}
        req = request.Request(
            "https://api.openai.com/v1/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=40) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        vectors = [item["embedding"] for item in body.get("data", [])]
        if vectors and len(vectors[0]) != self._dimension:
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {self._dimension}, got {len(vectors[0])}"
            )
        return vectors


class VertexEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str, dimension: int) -> None:
        import os

        self.endpoint = os.getenv("VERTEX_EMBEDDING_ENDPOINT", "")
        self.api_key = os.getenv("VERTEX_API_KEY", "")
        if not self.endpoint or not self.api_key:
            raise RuntimeError(
                "VERTEX_EMBEDDING_ENDPOINT and VERTEX_API_KEY are required for EMBEDDING_PROVIDER=vertex"
            )
        self.model = model
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.model, "inputs": texts}
        req = request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=40) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        vectors = body.get("vectors", [])
        if vectors and len(vectors[0]) != self._dimension:
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {self._dimension}, got {len(vectors[0])}"
            )
        return vectors


class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str, dimension: int) -> None:
        import os

        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is required for EMBEDDING_PROVIDER=gemini"
            )
        self.api_key = api_key
        self.model = model
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def _embed_one(self, text: str) -> list[float]:
        model_path = (
            self.model if self.model.startswith("models/") else f"models/{self.model}"
        )
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/{model_path}:embedContent"
            f"?key={parse.quote(self.api_key)}"
        )
        payload = {"content": {"parts": [{"text": text}]}}
        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=40) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        vector = body.get("embedding", {}).get("values", [])
        if vector and len(vector) != self._dimension:
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {self._dimension}, got {len(vector)}"
            )
        return vector

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Keep simple and reliable in Python stdlib: call embedContent per text.
        return [self._embed_one(t) for t in texts]


class EmbeddingClient:
    def __init__(self, provider: EmbeddingProvider, batch_size: int = 32) -> None:
        self.provider = provider
        self.batch_size = batch_size

    def embed_with_retry(self, texts: list[str], retries: int = 3) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            for attempt in range(1, retries + 1):
                try:
                    vectors.extend(self.provider.embed(batch))
                    break
                except Exception:
                    if attempt == retries:
                        raise
                    time.sleep(0.4 * attempt)
        return vectors


def build_provider(name: str, model: str, dimension: int) -> EmbeddingProvider:
    key = name.lower()
    if key == "local":
        return LocalHashEmbeddingProvider(model=model, dimension=dimension)
    if key == "gemini":
        return GeminiEmbeddingProvider(model=model, dimension=dimension)
    if key == "openai":
        return OpenAIEmbeddingProvider(model=model, dimension=dimension)
    if key == "vertex":
        return VertexEmbeddingProvider(model=model, dimension=dimension)
    raise ValueError(f"Unsupported embedding provider: {name}")
