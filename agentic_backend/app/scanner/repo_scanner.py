from __future__ import annotations

import subprocess
from pathlib import Path

from app.hashing import stable_hash


LANGUAGE_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".md": "markdown",
    ".mdx": "markdown",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
}

IGNORE_DIRS = {".git", "node_modules", "dist", "build", "__pycache__", ".next", ".venv", "venv"}


class RepoScanner:
    def scan(self, repo_path: Path) -> list[dict]:
        results: list[dict] = []
        for path in repo_path.rglob("*"):
            if not path.is_file():
                continue
            if any(part in IGNORE_DIRS for part in path.parts):
                continue
            language = LANGUAGE_BY_EXT.get(path.suffix.lower())
            if not language:
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            rel = path.relative_to(repo_path).as_posix()
            results.append(
                {
                    "file_path": rel,
                    "language": language,
                    "size_bytes": path.stat().st_size,
                    "content": content,
                    "file_hash": stable_hash(content),
                }
            )
        return results

    def current_commit(self, repo_path: Path) -> str:
        try:
            out = subprocess.check_output(
                ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            return out.strip()
        except Exception:
            return "no-git"

    def changed_files(self, repo_path: Path, old_commit: str, new_commit: str) -> dict[str, list[str]]:
        if old_commit in {"", "no-git", None} or new_commit in {"", "no-git", None}:
            return {"added": [], "modified": [], "deleted": []}
        try:
            out = subprocess.check_output(
                ["git", "-C", str(repo_path), "diff", "--name-status", f"{old_commit}..{new_commit}"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except Exception:
            return {"added": [], "modified": [], "deleted": []}

        added: list[str] = []
        modified: list[str] = []
        deleted: list[str] = []
        for line in out.splitlines():
            if not line.strip():
                continue
            status, path = line.split("\t", 1)
            if status.startswith("A"):
                added.append(path)
            elif status.startswith("D"):
                deleted.append(path)
            else:
                modified.append(path)
        return {"added": added, "modified": modified, "deleted": deleted}
