import hashlib
import os
from pathlib import Path
from typing import Iterator, List
from src.core.config import logger
from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern

class RepoScanner:
    def __init__(self, root_path: str):
        self.root_path = Path(root_path).resolve()

        # Hardcode some defaults not to scan
        self.default_ignores = [
            ".git", ".env", "venv", "__pycache__", "node_modules", 
            "dist", "build", "*.pyc", "*.pyo", "*.pyd", ".DS_Store"
        ]

        self.ignore_spec = self._load_gitignore()
        
    def _load_gitignore(self) -> PathSpec:
        gitignore_path = self.root_path / ".gitignore"
        patterns = []
        if gitignore_path.exists():
            with open(gitignore_path, "r", encoding="utf-8") as f:
                patterns = f.read().splitlines()
        
        # Always mix in default ignores
        patterns.extend(self.default_ignores)
        return PathSpec.from_lines(GitWildMatchPattern, patterns)

    def scan(self) -> Iterator[str]:
        """Yields relative file paths of valid files to index."""
        logger.info(f"Scanning repository at {self.root_path}")
        
        for dirpath, dirnames, filenames in os.walk(self.root_path):
            dir_rel_path = Path(dirpath).relative_to(self.root_path)
            
            # Filter directories
            # We must modify dirnames in place to prevent os.walk from visiting ignored dirs
            dirnames[:] = [
                d for d in dirnames 
                if not self.ignore_spec.match_file(str(dir_rel_path / d) + "/")
            ]
            
            for f in filenames:
                file_rel_path = dir_rel_path / f
                # Skip ignored files
                if self.ignore_spec.match_file(str(file_rel_path)):
                    continue
                
                # Check for massive files or binary files by skipping if size > 1MB 
                # (Simple heuristic to prevent crashing embeddings/parsers)
                full_path = self.root_path / file_rel_path
                try:
                    if full_path.stat().st_size > 1_000_000:
                        logger.debug(f"Skipping large file: {file_rel_path}")
                        continue
                except OSError:
                    continue

                yield str(file_rel_path).replace("\\", "/")

    @staticmethod
    def get_file_content_and_hash(full_path: Path) -> tuple[str, str, int]:
        """Returns (content, sha256_hash, size_bytes). Throws UnicodeDecodeError if binary."""
        with open(full_path, "rb") as f:
            raw_bytes = f.read()
            
        sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
        size_bytes = len(raw_bytes)
        content = raw_bytes.decode("utf-8")
        
        return content, sha256_hash, size_bytes

    def get_supported_language(self, file_path: str) -> str:
        ext = Path(file_path).suffix.lower()
        if ext == ".py":
            return "python"
        elif ext in [".js", ".jsx"]:
            return "javascript"
        elif ext in [".ts", ".tsx"]:
            return "typescript"
        elif ext in [".md", ".mdx", ".txt"]:
            return "markdown"
        return "unknown"
