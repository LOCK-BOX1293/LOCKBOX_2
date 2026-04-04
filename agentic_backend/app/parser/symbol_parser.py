from __future__ import annotations

import ast
import re
from pathlib import Path

from app.hashing import stable_hash


_JS_IMPORT = re.compile(r"^\s*import\s+.*from\s+['\"]([^'\"]+)['\"]", re.MULTILINE)
_JS_CLASS = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
_JS_FUNCTION = re.compile(
    r"^\s*(?:function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(|const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\(?.*?\)?\s*=>)",
    re.MULTILINE,
)


class SymbolParser:
    def parse(self, repo_id: str, branch: str, commit_sha: str, file_path: str, language: str, content: str) -> list[dict]:
        if language == "python":
            return self._parse_python(repo_id, branch, commit_sha, file_path, content)
        if language in {"javascript", "typescript"}:
            return self._parse_js_ts(repo_id, branch, commit_sha, file_path, content)
        return [
            self._build_symbol(repo_id, branch, commit_sha, file_path, "module", Path(file_path).stem, "", 1, max(1, len(content.splitlines())))
        ]

    def _build_symbol(
        self,
        repo_id: str,
        branch: str,
        commit_sha: str,
        file_path: str,
        symbol_type: str,
        name: str,
        signature: str,
        start_line: int,
        end_line: int,
    ) -> dict:
        symbol_id = stable_hash(f"{repo_id}:{branch}:{commit_sha}:{file_path}:{symbol_type}:{name}:{start_line}:{end_line}")
        symbol_fqn = f"{commit_sha}:{file_path}:{name}:{start_line}:{end_line}"
        return {
            "repo_id": repo_id,
            "project_id": repo_id,
            "branch": branch,
            "commit_sha": commit_sha,
            "symbol_id": symbol_id,
            "symbol_fqn": symbol_fqn,
            "file_path": file_path,
            "symbol_type": symbol_type,
            "name": name,
            "signature": signature,
            "start_line": start_line,
            "end_line": end_line,
            "metadata": {},
        }

    def _parse_python(self, repo_id: str, branch: str, commit_sha: str, file_path: str, content: str) -> list[dict]:
        symbols: list[dict] = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return [self._build_symbol(repo_id, branch, commit_sha, file_path, "module", Path(file_path).stem, "", 1, max(1, len(content.splitlines())))]

        symbols.append(self._build_symbol(repo_id, branch, commit_sha, file_path, "module", Path(file_path).stem, "", 1, max(1, len(content.splitlines()))))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                symbols.append(self._build_symbol(repo_id, branch, commit_sha, file_path, "class", node.name, f"class {node.name}", node.lineno, getattr(node, "end_lineno", node.lineno)))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(self._build_symbol(repo_id, branch, commit_sha, file_path, "function", node.name, f"def {node.name}(...) ", node.lineno, getattr(node, "end_lineno", node.lineno)))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                name = node.names[0].name if node.names else "import"
                symbols.append(self._build_symbol(repo_id, branch, commit_sha, file_path, "import", name, "import", node.lineno, node.lineno))
        return symbols

    def _parse_js_ts(self, repo_id: str, branch: str, commit_sha: str, file_path: str, content: str) -> list[dict]:
        lines = content.splitlines()
        total = max(1, len(lines))
        symbols: list[dict] = [self._build_symbol(repo_id, branch, commit_sha, file_path, "module", Path(file_path).stem, "", 1, total)]

        for m in _JS_IMPORT.finditer(content):
            line = content[: m.start()].count("\n") + 1
            symbols.append(self._build_symbol(repo_id, branch, commit_sha, file_path, "import", m.group(1), "import", line, line))

        for m in _JS_CLASS.finditer(content):
            line = content[: m.start()].count("\n") + 1
            symbols.append(self._build_symbol(repo_id, branch, commit_sha, file_path, "class", m.group(1), f"class {m.group(1)}", line, min(total, line + 20)))

        for m in _JS_FUNCTION.finditer(content):
            name = m.group(1) or m.group(2)
            line = content[: m.start()].count("\n") + 1
            symbols.append(self._build_symbol(repo_id, branch, commit_sha, file_path, "function", name, f"function {name}(...) ", line, min(total, line + 20)))

        return symbols
