"""
Unit tests for Revert / Undo functionality:
- UndoManager
- RevertTool (revert_change)
- /undo, /revert, /rollback slash command
- Automatic change recording in FileEditTool and FileWriteTool
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lucy.core.commands import find_command
from lucy.core.tool import ToolContext
from lucy.tools.file_edit_tool import FileEditTool
from lucy.tools.file_write_tool import FileWriteTool
from lucy.tools.revert_tool import RevertTool
from lucy.utils.diff_preview import get_undo_manager


class TestRevert(unittest.TestCase):
    """Test suite for Revert & Undo operations."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mgr = get_undo_manager()
        self.mgr.clear()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.mgr.clear()

    def test_undo_manager_edit_and_undo_last(self):
        """Test recording an edit and undoing the last change."""
        test_file = Path(self.temp_dir) / "sample.txt"
        test_file.write_text("Hello World\nLine 2\n")

        # Record edit
        self.mgr.record_change(
            filepath=str(test_file),
            original_content="Hello World\nLine 2\n",
            new_content="Hello Agentic World\nLine 2\n",
            change_type="edit",
        )
        test_file.write_text("Hello Agentic World\nLine 2\n")

        # Check preview diff
        diff = self.mgr.preview_last()
        self.assertIsNotNone(diff)
        self.assertIn("-Hello World", diff)
        self.assertIn("+Hello Agentic World", diff)

        # Undo last
        change = self.mgr.undo_last()
        self.assertIsNotNone(change)
        self.assertEqual(change.filepath, str(test_file))
        # Content should be restored
        self.assertEqual(test_file.read_text(), "Hello World\nLine 2\n")

    def test_undo_manager_undo_all(self):
        """Test undoing all recorded changes in reverse order."""
        f1 = Path(self.temp_dir) / "f1.txt"
        f2 = Path(self.temp_dir) / "f2.txt"

        f1.write_text("Original 1")
        f2.write_text("Original 2")

        # Record changes
        self.mgr.record_change(str(f1), "Original 1", "Modified 1", "edit")
        f1.write_text("Modified 1")

        self.mgr.record_change(str(f2), "Original 2", "Modified 2", "edit")
        f2.write_text("Modified 2")

        undone = self.mgr.undo_all()
        self.assertEqual(len(undone), 2)
        self.assertEqual(f1.read_text(), "Original 1")
        self.assertEqual(f2.read_text(), "Original 2")

    def test_revert_tool_actions(self):
        """Test RevertTool with actions: list, diff, last, file, and all."""
        tool = RevertTool()
        self.assertEqual(tool.name, "revert_change")
        self.assertIn("undo", tool.aliases)
        self.assertIn("revert", tool.aliases)

        test_file = Path(self.temp_dir) / "test_doc.py"
        test_file.write_text("def foo(): return 1\n")

        self.mgr.record_change(
            str(test_file),
            "def foo(): return 1\n",
            "def foo(): return 2\n",
            "edit",
        )
        test_file.write_text("def foo(): return 2\n")

        async def run_tests():
            ctx = ToolContext(cwd=self.temp_dir)

            # 1. list
            res_list = await tool.call({"action": "list"}, ctx)
            self.assertIn("test_doc.py", res_list.data)

            # 2. diff
            res_diff = await tool.call({"action": "diff"}, ctx)
            self.assertIn("def foo()", res_diff.data)

            # 3. revert file
            res_rev = await tool.call({"action": "file", "file_path": str(test_file)}, ctx)
            self.assertIn("Successfully reverted", res_rev.data)
            self.assertEqual(test_file.read_text(), "def foo(): return 1\n")

        asyncio.run(run_tests())

    def test_file_edit_and_write_auto_record(self):
        """Test that FileEditTool and FileWriteTool automatically record changes in UndoManager."""
        test_file = Path(self.temp_dir) / "auto_record.txt"
        test_file.write_text("Initial Content\nSecond Line\n")

        edit_tool = FileEditTool()
        write_tool = FileWriteTool()
        revert_tool = RevertTool()

        async def run_integration():
            ctx = ToolContext(cwd=self.temp_dir, permission_mode="auto_accept")

            # Perform an edit via FileEditTool
            edit_res = await edit_tool.call(
                {
                    "file_path": str(test_file),
                    "old_text": "Initial Content",
                    "new_text": "Updated Content",
                },
                ctx,
            )
            self.assertFalse(edit_res.is_error)
            self.assertIn("Updated Content", test_file.read_text())

            # Verify that UndoManager tracked it
            history = self.mgr.get_history()
            self.assertGreaterEqual(len(history), 1)

            # Revert the edit using RevertTool
            rev_res = await revert_tool.call({"action": "last"}, ctx)
            self.assertIn("Successfully reverted", rev_res.data)
            self.assertIn("Initial Content", test_file.read_text())

            # Perform a write (create new file)
            new_file = Path(self.temp_dir) / "created.txt"
            write_res = await write_tool.call(
                {"file_path": str(new_file), "content": "Brand new file"},
                ctx,
            )
            self.assertFalse(write_res.is_error)
            self.assertTrue(new_file.exists())

            # Revert the write (deletes created file)
            rev_write = await revert_tool.call({"action": "last"}, ctx)
            self.assertIn("Successfully reverted", rev_write.data)
            self.assertFalse(new_file.exists())

        asyncio.run(run_integration())

    def test_revert_slash_command(self):
        """Test /revert and /undo command aliases and execution."""
        cmd_undo = find_command("undo")
        self.assertIsNotNone(cmd_undo)
        self.assertIn("revert", cmd_undo.aliases)

        cmd_revert = find_command("revert")
        self.assertIsNotNone(cmd_revert)

        test_file = Path(self.temp_dir) / "cmd_test.txt"
        test_file.write_text("Version 1")
        self.mgr.record_change(str(test_file), "Version 1", "Version 2", "edit")
        test_file.write_text("Version 2")

        async def run_cmd_test():
            res_list = await cmd_revert.execute("list", None)
            self.assertIn("cmd_test.txt", res_list.output)

            res_diff = await cmd_revert.execute("diff", None)
            self.assertIn("Version", res_diff.output)

            res_undo = await cmd_revert.execute("", None)
            self.assertIn("Undone", res_undo.output)
            self.assertEqual(test_file.read_text(), "Version 1")

        asyncio.run(run_cmd_test())


if __name__ == "__main__":
    unittest.main()
