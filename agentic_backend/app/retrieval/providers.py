from __future__ import annotations

import json
from abc import ABC, abstractmethod
from urllib import error, request

from app.models import RetrievalResult, RetrievedChunk
from app.retrieval.hybrid import HybridRetriever
from app.settings import get_settings
from app.storage.mongo_store import MongoStore


class RetrievalProvider(ABC):
    @abstractmethod
    def retrieve(self, project_id: str, query: str, top_k: int) -> RetrievalResult:
        raise NotImplementedError


class EmptyRetrievalProvider(RetrievalProvider):
    def retrieve(self, project_id: str, query: str, top_k: int) -> RetrievalResult:
        return RetrievalResult(chunks=[])


class LocalHybridRetrievalProvider(RetrievalProvider):
    """Use in-process Mongo + HybridRetriever when no HTTP service is configured."""

    def __init__(self) -> None:
        settings = get_settings()
        store = MongoStore(settings.mongodb_uri, settings.mongodb_db)
        self.hybrid = HybridRetriever(settings=settings, store=store)

    def retrieve(self, project_id: str, query: str, top_k: int) -> RetrievalResult:
        payload = self.hybrid.query(
            repo_id=project_id,
            branch="main",
            q=query,
            top_k=top_k,
            path_prefix="src/",
            include_tests=False,
            include_graph=True,
        )
        chunks = [
            RetrievedChunk(
                chunk_id=c.get("chunk_id", ""),
                file_path=c.get("file_path", ""),
                start_line=int(c.get("start_line", 1)),
                end_line=int(c.get("end_line", 1)),
                text=c.get("content", ""),
                score=float(c.get("score", 0.0)),
                symbol_name=c.get("symbol_name"),
            )
            for c in payload.get("chunks", [])
        ]
        return RetrievalResult(chunks=chunks)


class HttpRetrievalProvider(RetrievalProvider):
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def retrieve(self, project_id: str, query: str, top_k: int) -> RetrievalResult:
        endpoint = f"{self.base_url}/retrieve"
        req = request.Request(
            endpoint,
            data=json.dumps(
                {"project_id": project_id, "query": query, "top_k": top_k}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Retrieval service HTTP error: {exc.code} {detail}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"Retrieval service call failed: {exc.reason}") from exc

        return RetrievalResult.model_validate(payload)
