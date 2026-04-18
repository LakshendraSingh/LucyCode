"""
Notebook edit tool — edit Jupyter .ipynb notebooks.

Mirrors OpenCode's NotebookEditTool.
"""

from __future__ import annotations

import json
import os
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


class NotebookEditTool(Tool):
    @property
    def name(self) -> str:
        return "NotebookEdit"

    @property
    def aliases(self) -> list[str]:
        return ["Notebook"]

    @property
    def description(self) -> str:
        return "Edit Jupyter notebook (.ipynb) cells"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the .ipynb file",
                },
                "action": {
                    "type": "string",
                    "enum": ["read", "edit_cell", "add_cell", "delete_cell",
                             "move_cell", "set_cell_type", "clear_outputs"],
                    "description": "Action to perform on the notebook",
                },
                "cell_index": {
                    "type": "integer",
                    "description": "Index of the cell to operate on (0-based)",
                },
                "content": {
                    "type": "string",
                    "description": "New content for the cell",
                },
                "cell_type": {
                    "type": "string",
                    "enum": ["code", "markdown", "raw"],
                    "description": "Type of cell",
                    "default": "code",
                },
                "position": {
                    "type": "integer",
                    "description": "Target position for move_cell",
                },
            },
            "required": ["file_path", "action"],
        }

    def get_prompt(self) -> str:
        return (
            "Edit Jupyter notebook (.ipynb) files. Actions:\n"
            "- 'read': Read all cells with their indices\n"
            "- 'edit_cell': Edit the content of a cell at cell_index\n"
            "- 'add_cell': Add a new cell with content at cell_index\n"
            "- 'delete_cell': Delete a cell at cell_index\n"
            "- 'move_cell': Move cell from cell_index to position\n"
            "- 'set_cell_type': Change cell type at cell_index\n"
            "- 'clear_outputs': Clear all cell outputs"
        )

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return tool_input.get("action") == "read"

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        file_path = tool_input.get("file_path", "")
        action = tool_input.get("action", "")

        if not file_path:
            return ToolResult(error="file_path is required")

        if not os.path.isabs(file_path):
            file_path = os.path.join(context.cwd, file_path)

        if action == "read":
            return self._read_notebook(file_path)
        elif action == "edit_cell":
            return self._edit_cell(file_path, tool_input)
        elif action == "add_cell":
            return self._add_cell(file_path, tool_input)
        elif action == "delete_cell":
            return self._delete_cell(file_path, tool_input)
        elif action == "move_cell":
            return self._move_cell(file_path, tool_input)
        elif action == "set_cell_type":
            return self._set_cell_type(file_path, tool_input)
        elif action == "clear_outputs":
            return self._clear_outputs(file_path)
        else:
            return ToolResult(error=f"Unknown action: {action}")

    def _load_notebook(self, path: str) -> tuple[dict | None, str | None]:
        try:
            with open(path) as f:
                return json.load(f), None
        except FileNotFoundError:
            return None, f"File not found: {path}"
        except json.JSONDecodeError:
            return None, f"Invalid notebook format: {path}"

    def _save_notebook(self, path: str, nb: dict) -> str | None:
        try:
            with open(path, "w") as f:
                json.dump(nb, f, indent=1, ensure_ascii=False)
                f.write("\n")
            return None
        except OSError as e:
            return f"Failed to save: {e}"

    def _read_notebook(self, path: str) -> ToolResult:
        nb, err = self._load_notebook(path)
        if err:
            return ToolResult(error=err)

        cells = nb.get("cells", [])
        lines = [f"Notebook: {os.path.basename(path)} ({len(cells)} cells)\n"]

        for i, cell in enumerate(cells):
            ct = cell.get("cell_type", "code")
            source = "".join(cell.get("source", []))
            preview = source[:200].replace("\n", "\\n")
            outputs = cell.get("outputs", [])
            out_summary = f" [{len(outputs)} outputs]" if outputs else ""
            lines.append(f"[{i}] ({ct}){out_summary}: {preview}")

        return ToolResult(data="\n".join(lines))

    def _edit_cell(self, path: str, inp: dict) -> ToolResult:
        nb, err = self._load_notebook(path)
        if err:
            return ToolResult(error=err)

        idx = inp.get("cell_index", 0)
        content = inp.get("content", "")
        cells = nb.get("cells", [])

        if idx < 0 or idx >= len(cells):
            return ToolResult(error=f"Cell index {idx} out of range (0-{len(cells)-1})")

        cells[idx]["source"] = content.split("\n") if "\n" in content else [content]
        err = self._save_notebook(path, nb)
        if err:
            return ToolResult(error=err)

        return ToolResult(data=f"Updated cell [{idx}]")

    def _add_cell(self, path: str, inp: dict) -> ToolResult:
        nb, err = self._load_notebook(path)
        if err:
            # Create new notebook
            nb = {
                "nbformat": 4, "nbformat_minor": 5,
                "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
                "cells": [],
            }

        idx = inp.get("cell_index", len(nb.get("cells", [])))
        content = inp.get("content", "")
        cell_type = inp.get("cell_type", "code")

        new_cell = {
            "cell_type": cell_type,
            "metadata": {},
            "source": content.split("\n") if "\n" in content else [content],
        }
        if cell_type == "code":
            new_cell["outputs"] = []
            new_cell["execution_count"] = None

        cells = nb.get("cells", [])
        cells.insert(idx, new_cell)
        nb["cells"] = cells

        err = self._save_notebook(path, nb)
        if err:
            return ToolResult(error=err)

        return ToolResult(data=f"Added {cell_type} cell at [{idx}]")

    def _delete_cell(self, path: str, inp: dict) -> ToolResult:
        nb, err = self._load_notebook(path)
        if err:
            return ToolResult(error=err)

        idx = inp.get("cell_index", 0)
        cells = nb.get("cells", [])

        if idx < 0 or idx >= len(cells):
            return ToolResult(error=f"Cell index {idx} out of range")

        removed = cells.pop(idx)
        err = self._save_notebook(path, nb)
        if err:
            return ToolResult(error=err)

        return ToolResult(data=f"Deleted cell [{idx}] ({removed.get('cell_type', 'unknown')})")

    def _move_cell(self, path: str, inp: dict) -> ToolResult:
        nb, err = self._load_notebook(path)
        if err:
            return ToolResult(error=err)

        idx = inp.get("cell_index", 0)
        pos = inp.get("position", 0)
        cells = nb.get("cells", [])

        if idx < 0 or idx >= len(cells):
            return ToolResult(error=f"Source index {idx} out of range")

        cell = cells.pop(idx)
        cells.insert(pos, cell)

        err = self._save_notebook(path, nb)
        if err:
            return ToolResult(error=err)

        return ToolResult(data=f"Moved cell from [{idx}] to [{pos}]")

    def _set_cell_type(self, path: str, inp: dict) -> ToolResult:
        nb, err = self._load_notebook(path)
        if err:
            return ToolResult(error=err)

        idx = inp.get("cell_index", 0)
        cell_type = inp.get("cell_type", "code")
        cells = nb.get("cells", [])

        if idx < 0 or idx >= len(cells):
            return ToolResult(error=f"Cell index {idx} out of range")

        cells[idx]["cell_type"] = cell_type
        if cell_type == "code" and "outputs" not in cells[idx]:
            cells[idx]["outputs"] = []
            cells[idx]["execution_count"] = None
        elif cell_type != "code":
            cells[idx].pop("outputs", None)
            cells[idx].pop("execution_count", None)

        err = self._save_notebook(path, nb)
        if err:
            return ToolResult(error=err)

        return ToolResult(data=f"Cell [{idx}] type set to {cell_type}")

    def _clear_outputs(self, path: str) -> ToolResult:
        nb, err = self._load_notebook(path)
        if err:
            return ToolResult(error=err)

        cleared = 0
        for cell in nb.get("cells", []):
            if cell.get("cell_type") == "code":
                cell["outputs"] = []
                cell["execution_count"] = None
                cleared += 1

        err = self._save_notebook(path, nb)
        if err:
            return ToolResult(error=err)

        return ToolResult(data=f"Cleared outputs from {cleared} code cells")
