"""
LSP tool — Language Server Protocol queries.

Go-to-definition, find references, diagnostics, symbol search.
Mirrors OpenCode's LSPTool.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


class LSPTool(Tool):
    @property
    def name(self) -> str:
        return "LSP"

    @property
    def aliases(self) -> list[str]:
        return ["LanguageServer"]

    @property
    def description(self) -> str:
        return "Query language servers for definitions, references, diagnostics, and symbols"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["definition", "references", "diagnostics", "symbols", "hover"],
                    "description": "LSP action to perform",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to the file",
                },
                "line": {
                    "type": "integer",
                    "description": "Line number (0-indexed)",
                },
                "character": {
                    "type": "integer",
                    "description": "Character offset (0-indexed)",
                },
                "query": {
                    "type": "string",
                    "description": "Symbol query for workspace symbol search",
                },
            },
            "required": ["action", "file_path"],
        }

    def get_prompt(self) -> str:
        return (
            "Query language servers for code intelligence. Actions:\n"
            "- 'definition': Go to the definition of a symbol at line:character\n"
            "- 'references': Find all references to a symbol at line:character\n"
            "- 'diagnostics': Get diagnostics (errors/warnings) for a file\n"
            "- 'symbols': Search for symbols in a file or workspace\n"
            "- 'hover': Get hover information for a symbol\n"
            "Note: Requires a language server to be available for the file's language."
        )

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        action = tool_input.get("action", "")
        file_path = tool_input.get("file_path", "")
        line = tool_input.get("line", 0)
        character = tool_input.get("character", 0)
        query = tool_input.get("query", "")

        if not file_path:
            return ToolResult(error="file_path is required")

        # Resolve path
        if not os.path.isabs(file_path):
            file_path = os.path.join(context.cwd, file_path)

        if not os.path.exists(file_path):
            return ToolResult(error=f"File not found: {file_path}")

        # Detect language
        ext = os.path.splitext(file_path)[1].lower()
        language = _detect_language(ext)

        if action == "diagnostics":
            return await self._get_diagnostics(file_path, language, context)
        elif action == "definition":
            return await self._goto_definition(file_path, line, character, language, context)
        elif action == "references":
            return await self._find_references(file_path, line, character, language, context)
        elif action == "symbols":
            return await self._find_symbols(file_path, query, language, context)
        elif action == "hover":
            return await self._get_hover(file_path, line, character, language, context)
        else:
            return ToolResult(error=f"Unknown action: {action}")

    async def _get_diagnostics(self, file_path: str, language: str, context: ToolContext) -> ToolResult:
        """Get diagnostics using language-specific tools."""
        diagnostics = []

        if language == "python":
            # Try pyflakes, flake8, or mypy
            for tool_cmd in [["python", "-m", "py_compile", file_path],
                             ["python", "-m", "pyflakes", file_path]]:
                try:
                    result = subprocess.run(
                        tool_cmd, capture_output=True, text=True,
                        cwd=context.cwd, timeout=30,
                    )
                    if result.stderr:
                        diagnostics.append(result.stderr.strip())
                    if result.stdout:
                        diagnostics.append(result.stdout.strip())
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue

        elif language == "typescript" or language == "javascript":
            try:
                result = subprocess.run(
                    ["npx", "tsc", "--noEmit", file_path],
                    capture_output=True, text=True, cwd=context.cwd, timeout=60,
                )
                if result.stdout:
                    diagnostics.append(result.stdout.strip())
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        elif language == "rust":
            try:
                result = subprocess.run(
                    ["cargo", "check", "--message-format=short"],
                    capture_output=True, text=True, cwd=context.cwd, timeout=60,
                )
                if result.stderr:
                    diagnostics.append(result.stderr.strip())
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        if not diagnostics:
            return ToolResult(data=f"No diagnostics found for {os.path.basename(file_path)}")

        return ToolResult(data="\n".join(diagnostics))

    async def _handle_go_to_definition(self, target: str, root_dir: Path) -> ToolResult:
        # We perform a dumb walk and parse files with tree-sitter since it's much more accurate
        from lucy.utils.tree_sitter_indexer import get_indexer
        indexer = get_indexer()
        
        results = []
        for p in root_dir.rglob("*.py"):
            ast_data = indexer.parse_file(str(p))
            if ast_data:
                for sym in ast_data.get("symbols", []):
                    if sym["name"] == target:
                        results.append(f"{p}:{sym['line']} - {sym['type']} {sym['name']}")
        
        for p in root_dir.rglob("*.ts"):
            ast_data = indexer.parse_file(str(p))
            if ast_data:
                for sym in ast_data.get("symbols", []):
                    if sym["name"] == target:
                        results.append(f"{p}:{sym['line']} - {sym['type']} {sym['name']}")

        if not results:
            return ToolResult(error=f"Could not find definition for '{target}'.")

        return ToolResult(data="Definitions found:\n" + "\n".join(results))

    async def _goto_definition(self, file_path: str, line: int, char: int,
                               language: str, context: ToolContext) -> ToolResult:
        """Find the definition of a symbol using grep-based analysis."""
        # Read the file and find the symbol at position
        try:
            with open(file_path) as f:
                lines = f.readlines()
        except OSError as e:
            return ToolResult(error=f"Cannot read file: {e}")

        if line >= len(lines):
            return ToolResult(error=f"Line {line} out of range (file has {len(lines)} lines)")

        # Extract symbol at position
        line_text = lines[line]
        symbol = _extract_symbol(line_text, char)

        return await self._handle_go_to_definition(symbol, Path(context.cwd))

    async def _find_references(self, file_path: str, line: int, char: int,
                               language: str, context: ToolContext) -> ToolResult:
        """Find all references to a symbol."""
        try:
            with open(file_path) as f:
                lines = f.readlines()
        except OSError as e:
            return ToolResult(error=f"Cannot read file: {e}")

        if line >= len(lines):
            return ToolResult(error=f"Line {line} out of range")

        symbol = _extract_symbol(lines[line], char)
        if not symbol:
            return ToolResult(error=f"No symbol found at position")

        try:
            ext = os.path.splitext(file_path)[1]
            result = subprocess.run(
                ["grep", "-rn", f"\\b{symbol}\\b", context.cwd,
                 "--include=*" + ext, "-l"],
                capture_output=True, text=True, timeout=15,
            )
            if result.stdout:
                files = result.stdout.strip().split("\n")
                ref_lines = []
                for f_path in files[:20]:
                    line_result = subprocess.run(
                        ["grep", "-n", f"\\b{symbol}\\b", f_path],
                        capture_output=True, text=True, timeout=5,
                    )
                    if line_result.stdout:
                        for ml in line_result.stdout.strip().split("\n")[:5]:
                            ref_lines.append(f"{f_path}:{ml.strip()}")

                return ToolResult(
                    data=f"References to '{symbol}' ({len(ref_lines)} found):\n" +
                         "\n".join(ref_lines[:50])
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return ToolResult(data=f"No references found for '{symbol}'")

    async def _find_symbols(self, file_path: str, query: str,
                            language: str, context: ToolContext) -> ToolResult:
        """Find symbols in file."""
        try:
            with open(file_path) as f:
                content = f.read()
        except OSError as e:
            return ToolResult(error=f"Cannot read file: {e}")

        symbols = []
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            is_symbol = False

            if language == "python":
                is_symbol = (stripped.startswith(("def ", "class ", "async def ")) or
                             ("=" in stripped and not stripped.startswith("#")))
            elif language in ("javascript", "typescript"):
                is_symbol = (stripped.startswith(("function ", "class ", "const ", "let ", "var ",
                                                  "export ", "interface ", "type ")) or
                             "=>" in stripped)
            elif language == "rust":
                is_symbol = stripped.startswith(("fn ", "struct ", "enum ", "impl ", "trait ",
                                                 "pub fn ", "pub struct ", "mod "))
            elif language in ("c", "cpp"):
                is_symbol = (stripped.endswith("{") and "(" in stripped and
                             not stripped.startswith(("//", "/*", "if", "for", "while")))
            else:
                is_symbol = stripped.startswith(("def ", "class ", "function ", "fn "))

            if is_symbol:
                if not query or query.lower() in stripped.lower():
                    symbols.append(f"  L{i}: {stripped[:100]}")

        if symbols:
            return ToolResult(data=f"Symbols in {os.path.basename(file_path)}:\n" + "\n".join(symbols[:50]))
        return ToolResult(data=f"No symbols found in {os.path.basename(file_path)}")

    async def _get_hover(self, file_path: str, line: int, char: int,
                         language: str, context: ToolContext) -> ToolResult:
        """Get hover info for a symbol."""
        try:
            with open(file_path) as f:
                lines = f.readlines()
        except OSError as e:
            return ToolResult(error=f"Cannot read file: {e}")

        if line >= len(lines):
            return ToolResult(error=f"Line {line} out of range")

        symbol = _extract_symbol(lines[line], char)
        if not symbol:
            return ToolResult(error="No symbol at position")

        # Look for docstring/comment above definition
        definition = await self._goto_definition(file_path, line, char, language, context)
        return ToolResult(data=f"Symbol: {symbol}\n{definition.to_content_string()}")


def _detect_language(ext: str) -> str:
    mapping = {
        ".py": "python", ".pyi": "python",
        ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".rs": "rust",
        ".go": "go",
        ".c": "c", ".h": "c",
        ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
        ".java": "java",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
    }
    return mapping.get(ext, "unknown")


def _extract_symbol(line: str, char: int) -> str:
    if char >= len(line):
        char = max(0, len(line) - 1)
    # Find word boundaries
    start = char
    while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
        start -= 1
    end = char
    while end < len(line) and (line[end].isalnum() or line[end] == "_"):
        end += 1
    return line[start:end]


def _definition_patterns(symbol: str, language: str) -> list[str]:
    if language == "python":
        return [f"def {symbol}", f"class {symbol}", f"{symbol} ="]
    elif language in ("javascript", "typescript"):
        return [f"function {symbol}", f"class {symbol}", f"const {symbol}",
                f"let {symbol}", f"var {symbol}", f"interface {symbol}"]
    elif language == "rust":
        return [f"fn {symbol}", f"struct {symbol}", f"enum {symbol}"]
    elif language == "go":
        return [f"func {symbol}", f"type {symbol}"]
    else:
        return [f"def {symbol}", f"class {symbol}", f"function {symbol}", f"fn {symbol}"]
