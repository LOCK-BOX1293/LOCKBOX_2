from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import request

from src.core.config import settings


@dataclass(frozen=True)
class ArmorIQConfig:
    api_key: str
    base_url: str
    scan_path: str
    timeout_seconds: float
    fail_closed: bool
    app_name: str


class ArmorIQClient:
    def __init__(self, config: ArmorIQConfig) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return bool(self.config.api_key and self.config.base_url)

    def sanitize_text(
        self,
        text: str,
        *,
        provider: str,
        model: str,
        operation: str,
        role: str = "user",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not self.enabled or not text.strip():
            return text

        payload = {
            "text": text,
            "input": text,
            "content": text,
            "provider": provider,
            "model": model,
            "operation": operation,
            "role": role,
            "application": self.config.app_name,
            "metadata": metadata or {},
        }
        req = request.Request(
            f"{self.config.base_url.rstrip('/')}/{self.config.scan_path.lstrip('/')}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
                "x-api-key": self.config.api_key,
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            if self.config.fail_closed:
                raise RuntimeError(
                    f"ArmorIQ scan failed for {provider}/{operation}: {exc}"
                ) from exc
            return text

        return self._resolve_text(body, original_text=text)

    def _resolve_text(self, body: Any, *, original_text: str) -> str:
        if not isinstance(body, dict):
            return original_text

        if self._is_blocked(body):
            raise RuntimeError(self._extract_message(body) or "ArmorIQ blocked content.")

        for key in (
            "sanitized_text",
            "sanitizedText",
            "redacted_text",
            "rewritten_text",
            "output_text",
            "text",
            "content",
            "result",
        ):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value

        nested = body.get("data")
        if isinstance(nested, dict):
            for key in (
                "sanitized_text",
                "sanitizedText",
                "redacted_text",
                "rewritten_text",
                "output_text",
                "text",
                "content",
                "result",
            ):
                value = nested.get(key)
                if isinstance(value, str) and value.strip():
                    return value

        return original_text

    def _is_blocked(self, body: dict[str, Any]) -> bool:
        blocked = body.get("blocked")
        if isinstance(blocked, bool):
            return blocked

        allowed = body.get("allowed")
        if isinstance(allowed, bool):
            return not allowed

        safe = body.get("safe")
        if isinstance(safe, bool):
            return not safe

        verdict = body.get("verdict")
        if isinstance(verdict, str):
            return verdict.strip().lower() in {"block", "blocked", "deny", "denied"}

        action = body.get("action")
        if isinstance(action, str):
            return action.strip().lower() in {"block", "blocked", "deny", "denied"}

        return False

    def _extract_message(self, body: dict[str, Any]) -> str:
        for key in ("message", "reason", "detail", "error"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value
        nested = body.get("data")
        if isinstance(nested, dict):
            for key in ("message", "reason", "detail", "error"):
                value = nested.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return ""


def build_armoriq_client() -> ArmorIQClient | None:
    if not settings.armoriq_api_key:
        return None

    return ArmorIQClient(
        ArmorIQConfig(
            api_key=settings.armoriq_api_key,
            base_url=settings.armoriq_base_url,
            scan_path=settings.armoriq_scan_path,
            timeout_seconds=settings.armoriq_timeout_seconds,
            fail_closed=settings.armoriq_fail_closed,
            app_name=settings.armoriq_app_name,
        )
    )
