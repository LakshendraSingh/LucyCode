"""
Tree-Sitter based Code Indexer for resolving symbols and building an AST cache.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser

logger = logging.getLogger(__name__)

class TreeSitterIndexer:
    def __init__(self):
        self.parser = Parser()
        self.languages = {}
        self._load_languages()

    def _load_languages(self):
        try:
            import tree_sitter_python
            import tree_sitter_javascript
            import tree_sitter_typescript

            self.languages['.py'] = Language(tree_sitter_python.language(), "python")
            self.languages['.js'] = Language(tree_sitter_javascript.language(), "javascript")
            self.languages['.ts'] = Language(tree_sitter_typescript.language_typescript(), "typescript")
            self.languages['.tsx'] = Language(tree_sitter_typescript.language_tsx(), "tsx")
        except ImportError as e:
            logger.warning(f"Tree-sitter languages could not be loaded: {e}. Semantic indexing will be disabled.")

    def parse_file(self, filepath: str) -> dict[str, Any] | None:
        """Parse a file and return its AST mapping of classes and functions."""
        ext = Path(filepath).suffix
        if ext not in self.languages:
            return None
        
        self.parser.set_language(self.languages[ext])
        
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            tree = self.parser.parse(content)
            
            # Simple top-level structural extraction
            symbols = []
            
            def traverse(node):
                if node.type in ["function_definition", "class_definition", "method_definition", "arrow_function", "function_declaration"]:
                    # Find the generic wrapper or identifier
                    identifier = None
                    for child in node.children:
                        if child.type == "identifier":
                            identifier = child.text.decode('utf8')
                            break
                    if identifier:
                        symbols.append({
                            "name": identifier,
                            "type": node.type,
                            "line": node.start_point[0] + 1,  # 1-indexed
                        })
                for child in node.children:
                    traverse(child)

            traverse(tree.root_node)
            
            return {
                "file": filepath,
                "symbols": symbols
            }
        except Exception as e:
            logger.error(f"Failed to parse {filepath}: {e}")
            return None


_indexer = None

def get_indexer() -> TreeSitterIndexer:
    global _indexer
    if _indexer is None:
        _indexer = TreeSitterIndexer()
    return _indexer
