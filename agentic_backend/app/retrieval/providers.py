from __future__ import annotations

import json
from abc import ABC, abstractmethod
from urllib import error, request

from app.models import RetrievalResult


class RetrievalProvider(ABC):
    @abstractmethod
    def retrieve(self, project_id: str, query: str, top_k: int) -> RetrievalResult:
        raise NotImplementedError


class EmptyRetrievalProvider(RetrievalProvider):
    def retrieve(self, project_id: str, query: str, top_k: int) -> RetrievalResult:
        return RetrievalResult(chunks=[])


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
            raise RuntimeError(f"Retrieval service HTTP error: {exc.code} {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Retrieval service call failed: {exc.reason}") from exc

        return RetrievalResult.model_validate(payload)
