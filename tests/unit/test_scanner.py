import os
from pathlib import Path
from src.scanner.repo_scanner import RepoScanner

def test_scanner_ignores_gitignore(tmp_path):
    # Setup test dir
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    
    (repo_dir / ".gitignore").write_text("ignore_me.py\nvenv/")
    (repo_dir / "main.py").write_text("print('hello')")
    (repo_dir / "ignore_me.py").write_text("print('no')")
    
    venv_dir = repo_dir / "venv"
    venv_dir.mkdir()
    (venv_dir / "lib.py").write_text("print('lib')")

    scanner = RepoScanner(str(repo_dir))
    files = list(scanner.scan())
    
    # We should only find main.py and .gitignore
    file_names = [Path(f).name for f in files]
    assert "main.py" in file_names
    assert "ignore_me.py" not in file_names
    assert "lib.py" not in file_names

def test_hash_content():
    content, h, size = RepoScanner.get_file_content_and_hash(Path(__file__))
    assert isinstance(content, str)
    assert len(h) == 64
    assert size > 0
