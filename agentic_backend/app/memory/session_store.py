from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from app.models import SessionEvent


class SessionStore(ABC):
    @abstractmethod
    def recent_context(self, project_id: str, session_id: str, limit: int = 6) -> list[SessionEvent]:
        raise NotImplementedError

    @abstractmethod
    def append_event(self, event: SessionEvent) -> None:
        raise NotImplementedError


class InMemorySessionStore(SessionStore):
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], list[SessionEvent]] = {}

    def recent_context(self, project_id: str, session_id: str, limit: int = 6) -> list[SessionEvent]:
        key = (project_id, session_id)
        return self._events.get(key, [])[-limit:]

    def append_event(self, event: SessionEvent) -> None:
        key = (event.project_id, event.session_id)
        self._events.setdefault(key, []).append(event)


class MongoSessionStore(SessionStore):
    def __init__(self, mongodb_uri: str, db_name: str) -> None:
        try:
            mongo_module = importlib.import_module("pymongo")
        except ImportError as exc:
            raise RuntimeError(
                "pymongo is required for MongoSessionStore. Install dependencies from requirements.txt"
            ) from exc

        MongoClient = getattr(mongo_module, "MongoClient")
        self.client = MongoClient(mongodb_uri)
        self.db = self.client[db_name]

    def recent_context(self, project_id: str, session_id: str, limit: int = 6) -> list[SessionEvent]:
        docs = list(
            self.db.events.find(
                {"project_id": project_id, "session_id": session_id},
                {"_id": 0, "project_id": 1, "session_id": 1, "role": 1, "content": 1},
            )
            .sort("ts", -1)
            .limit(limit)
        )
        docs.reverse()
        return [SessionEvent.model_validate(doc) for doc in docs]

    def append_event(self, event: SessionEvent) -> None:
        now = datetime.now(timezone.utc)
        self.db.events.insert_one(
            {
                "project_id": event.project_id,
                "session_id": event.session_id,
                "role": event.role,
                "content": event.content,
                "ts": now,
                "expires_at": now + timedelta(days=7),
            }
        )
