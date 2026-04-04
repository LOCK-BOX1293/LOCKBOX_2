from __future__ import annotations

from app.parser.symbol_parser import SymbolParser


def test_parser_extracts_python_symbols() -> None:
    content = "import os\n\nclass A:\n    pass\n\ndef f(x):\n    return x\n"
    parser = SymbolParser()
    symbols = parser.parse("r", "main", "c1", "a.py", "python", content)
    names = {s["name"] for s in symbols}
    assert "A" in names
    assert "f" in names
    # import symbols are disabled by default to reduce graph noise
    assert "os" not in names


def test_parser_extracts_js_symbols() -> None:
    content = "import x from 'm';\nclass Box {}\nfunction run(){}\n"
    parser = SymbolParser()
    symbols = parser.parse("r", "main", "c1", "a.ts", "typescript", content)
    names = {s["name"] for s in symbols}
    # import symbols are disabled by default to reduce graph noise
    assert "m" not in names
    assert "Box" in names
    assert "run" in names
