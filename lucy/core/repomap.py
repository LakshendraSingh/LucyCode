"""
Repo-Map Engine — Structural AST code graph & PageRank repository mapping.

Inspired by Aider and PageRank AST maps:
Scans the repository, extracts classes, functions, and cross-file references,
calculates centrality scores, and formats a compact token-budgeted architectural
map that is automatically injected into the LLM system prompt.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__",
    "dist", "build", ".lucy", ".lucycode", ".idea", ".vscode",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "coverage",
}

CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".c", ".cpp", ".h", ".hpp",
}


@dataclass
class SymbolInfo:
    """A definition symbol (class, function, method, interface)."""
    name: str
    kind: str  # class, def, async_def, interface, struct, fn
    line_no: int
    parent: str | None = None
    args: list[str] = field(default_factory=list)


@dataclass
class FileSymbols:
    """Extracted symbols and identifiers for a file."""
    path: str
    symbols: list[SymbolInfo] = field(default_factory=list)
    identifiers: set[str] = field(default_factory=set)
    references: set[str] = field(default_factory=set)
    centrality: float = 0.0


class RepoMap:
    """Builds and renders structural repository maps."""

    def __init__(self, root_dir: str | Path | None = None, max_tokens: int = 1500):
        self.root = Path(root_dir or os.getcwd()).resolve()
        self.max_tokens = max_tokens
        self._cache: dict[str, FileSymbols] = {}

    def scan_repo(self, max_files: int = 300) -> dict[str, FileSymbols]:
        """Scan repository and extract code symbols across all source files."""
        file_map: dict[str, FileSymbols] = {}

        count = 0
        for dirpath, dirnames, filenames in os.walk(self.root):
            # Prune excluded directories
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith(".")]

            for f in sorted(filenames):
                if f.startswith("."):
                    continue
                ext = os.path.splitext(f)[1].lower()
                if ext not in CODE_EXTENSIONS:
                    continue

                full_path = Path(dirpath) / f
                try:
                    rel_path = str(full_path.relative_to(self.root))
                except ValueError:
                    rel_path = str(full_path)

                file_syms = self._extract_symbols(full_path, rel_path, ext)
                if file_syms:
                    file_map[rel_path] = file_syms

                count += 1
                if count >= max_files:
                    break
            if count >= max_files:
                break

        # Compute PageRank / Graph Centrality
        self._compute_centrality(file_map)
        self._cache = file_map
        return file_map

    def _extract_symbols(self, file_path: Path, rel_path: str, ext: str) -> FileSymbols | None:
        """Extract AST symbols for Python, or regex symbols for other languages."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None

        # Gather general identifiers for cross-reference graph
        words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", content))
        sym_obj = FileSymbols(path=rel_path, identifiers=words)

        if ext == ".py":
            try:
                tree = ast.parse(content, filename=str(file_path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        sym_obj.symbols.append(
                            SymbolInfo(name=node.name, kind="class", line_no=node.lineno)
                        )
                        for item in node.body:
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                kind = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                                args = [a.arg for a in item.args.args if a.arg != "self"]
                                sym_obj.symbols.append(
                                    SymbolInfo(name=item.name, kind=kind, line_no=item.lineno, parent=node.name, args=args)
                                )
                    elif isinstance(node, ast.FunctionDef) and not getattr(node, "_is_method", False):
                        args = [a.arg for a in node.args.args]
                        sym_obj.symbols.append(SymbolInfo(name=node.name, kind="def", line_no=node.lineno, args=args))
                    elif isinstance(node, ast.AsyncFunctionDef) and not getattr(node, "_is_method", False):
                        args = [a.arg for a in node.args.args]
                        sym_obj.symbols.append(SymbolInfo(name=node.name, kind="async def", line_no=node.lineno, args=args))
            except SyntaxError:
                self._extract_generic_symbols(content, sym_obj)
        else:
            self._extract_generic_symbols(content, sym_obj)

        return sym_obj

    def _extract_generic_symbols(self, content: str, sym_obj: FileSymbols) -> None:
        """Fallback regex symbol extraction for JS/TS, Rust, Go, C/C++."""
        patterns = [
            (r"class\s+([A-Za-z0-9_]+)", "class"),
            (r"interface\s+([A-Za-z0-9_]+)", "interface"),
            (r"struct\s+([A-Za-z0-9_]+)", "struct"),
            (r"function\s+([A-Za-z0-9_]+)\s*\(", "fn"),
            (r"def\s+([A-Za-z0-9_]+)\s*\(", "def"),
            (r"fn\s+([A-Za-z0-9_]+)\s*\(", "fn"),
            (r"func\s+(?:\([^\)]+\)\s+)?([A-Za-z0-9_]+)\s*\(", "func"),
            (r"enum\s+([A-Za-z0-9_]+)", "enum"),
        ]
        for line_no, line in enumerate(content.splitlines(), start=1):
            line_str = line.strip()
            for pat, kind in patterns:
                m = re.search(pat, line_str)
                if m:
                    sym_obj.symbols.append(SymbolInfo(name=m.group(1), kind=kind, line_no=line_no))

    def _compute_centrality(self, file_map: dict[str, FileSymbols]) -> None:
        """Compute PageRank-style reference centrality between files."""
        # Map symbol names to defining files
        def_to_files: dict[str, set[str]] = {}
        for path, fs in file_map.items():
            for s in fs.symbols:
                def_to_files.setdefault(s.name, set()).add(path)

        # Build in-degree counts (references from other files)
        in_degrees: dict[str, int] = {p: 1 for p in file_map}  # baseline 1

        for path, fs in file_map.items():
            for ident in fs.identifiers:
                defining_paths = def_to_files.get(ident, set())
                for def_path in defining_paths:
                    if def_path != path:
                        in_degrees[def_path] = in_degrees.get(def_path, 0) + 1

        max_deg = max(in_degrees.values()) if in_degrees else 1
        for path, deg in in_degrees.items():
            if path in file_map:
                file_map[path].centrality = deg / max_deg

    def render_map(self, max_tokens: int | None = None) -> str:
        """Render compact repository map sorted by architectural centrality."""
        budget = max_tokens or self.max_tokens
        char_budget = budget * 4  # ~4 chars per token rule of thumb

        if not self._cache:
            self.scan_repo()

        # Sort files by centrality descending
        sorted_files = sorted(self._cache.values(), key=lambda fs: fs.centrality, reverse=True)

        lines: list[str] = []
        current_chars = 0

        for fs in sorted_files:
            if not fs.symbols:
                continue

            file_header = f"{fs.path}:"
            file_lines = [file_header]

            # Group methods under classes
            seen_classes = set()
            for s in fs.symbols:
                if s.kind == "class":
                    file_lines.append(f"  class {s.name}")
                    seen_classes.add(s.name)
                elif s.parent:
                    args_str = ", ".join(s.args[:3]) + ("..." if len(s.args) > 3 else "")
                    file_lines.append(f"    {s.kind} {s.name}({args_str})")
                else:
                    args_str = ", ".join(s.args[:3]) + ("..." if len(s.args) > 3 else "")
                    file_lines.append(f"  {s.kind} {s.name}({args_str})")

            block_text = "\n".join(file_lines)
            if current_chars + len(block_text) > char_budget:
                break

            lines.append(block_text)
            current_chars += len(block_text) + 2

        if not lines:
            return "(Empty repository)"

        return "\n\n".join(lines)


# Global singleton
_GLOBAL_REPO_MAP: RepoMap | None = None


def get_repo_map(cwd: str | None = None) -> RepoMap:
    global _GLOBAL_REPO_MAP
    if _GLOBAL_REPO_MAP is None or _GLOBAL_REPO_MAP.root != Path(cwd or os.getcwd()).resolve():
        _GLOBAL_REPO_MAP = RepoMap(root_dir=cwd)
    return _GLOBAL_REPO_MAP

