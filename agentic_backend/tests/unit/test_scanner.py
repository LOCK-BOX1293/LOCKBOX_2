from __future__ import annotations

from pathlib import Path

from app.scanner.repo_scanner import RepoScanner



def test_scanner_filters_supported_files(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("print('x')", encoding="utf-8")
    (tmp_path / "b.ts").write_text("export const a=1", encoding="utf-8")
    (tmp_path / "c.bin").write_bytes(b"\x00\x01")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "skip.js").write_text("x", encoding="utf-8")

    scanner = RepoScanner()
    items = scanner.scan(tmp_path)
    paths = {i["file_path"] for i in items}

    assert "a.py" in paths
    assert "b.ts" in paths
    assert "c.bin" not in paths
    assert "node_modules/skip.js" not in paths
