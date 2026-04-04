from __future__ import annotations

from pathlib import Path

from app.config import PROMPTS_DIR


_PROMPT_FILE_MAP = {
    "backend": "expert_backend.md",
    "frontend": "expert_frontend.md",
    "security": "expert_security.md",
    "architect": "expert_architect.md",
    "debugger": "expert_debugger.md",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def build_system_prompt(role: str) -> str:
    base = _read(PROMPTS_DIR / "base_system_contract.md")
    expert_name = _PROMPT_FILE_MAP.get(role.lower(), "expert_backend.md")
    expert = _read(PROMPTS_DIR / expert_name)
    return f"{base}\n\n{expert}"
