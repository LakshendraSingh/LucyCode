"""
Context Engine — intelligent context window management.

Goes beyond simple compaction to provide:
- Accurate token estimation using tiktoken
- Relevance-based message pruning (keep relevant, drop obsolete bulk)
- Diff-aware context (only inject relevant changes/hunks)
- Dynamic tool selection (only include tools likely needed)
- Conversation summarization with key detail preservation
"""

from __future__ import annotations

import difflib
import json
import logging
import re
from typing import Any

from lucy.core.message import (
    AssistantMessage,
    CompactBoundaryMessage,
    Message,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from lucy.core.tool import Tool

logger = logging.getLogger(__name__)

# Attempt to load tiktoken encoding
try:
    import tiktoken
    _TIKTOKEN_ENCODING = tiktoken.get_encoding("cl100k_base")
except Exception:
    _TIKTOKEN_ENCODING = None


class ContextEngine:
    """Manages context window intelligently."""

    def __init__(self, max_tokens: int = 200_000) -> None:
        self.max_tokens = max_tokens
        self._encoding = _TIKTOKEN_ENCODING

    def estimate_tokens(self, content: list[Message] | Message | str) -> int:
        """Estimate token count for a string, single Message, or list of Messages."""
        if isinstance(content, str):
            return self._count_str_tokens(content)

        if isinstance(content, Message):
            return self._count_message_tokens(content)

        if isinstance(content, list):
            total = 0
            for m in content:
                if isinstance(m, Message):
                    total += self._count_message_tokens(m)
                elif isinstance(m, str):
                    total += self._count_str_tokens(m)
            return total

        return 0

    def _count_str_tokens(self, text: str) -> int:
        if not text:
            return 0
        if self._encoding:
            try:
                return len(self._encoding.encode(text, disallowed_special=()))
            except Exception:
                pass
        # Fallback estimation: ~4 chars per token
        return max(1, len(text) // 4)

    def _count_message_tokens(self, msg: Message) -> int:
        # Message envelope overhead
        tokens = 4

        if isinstance(msg.content, str):
            tokens += self._count_str_tokens(msg.content)
        elif isinstance(msg.content, list):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    tokens += self._count_str_tokens(block.text)
                elif isinstance(block, ThinkingBlock):
                    tokens += self._count_str_tokens(block.thinking)
                elif isinstance(block, ToolUseBlock):
                    tokens += self._count_str_tokens(block.name)
                    tokens += self._count_str_tokens(json.dumps(block.input, default=str))
                elif isinstance(block, ToolResultBlock):
                    tokens += self._count_str_tokens(str(block.content))
                elif hasattr(block, "text"):
                    tokens += self._count_str_tokens(str(block.text))

        return tokens

    def optimize_messages(self, messages: list[Message], current_task: str = "") -> list[Message]:
        """Prune messages keeping only relevant context.

        Strategy:
        - If total tokens are well within max_tokens (<= 70%), keep intact.
        - If approaching limit, preserve first user prompt and recent messages.
        - Prune large, obsolete intermediate tool result payloads (e.g. large grep/file reads).
        - Preserve all error outputs and assistant reasoning.
        """
        current_tokens = self.estimate_tokens(messages)
        target_limit = int(self.max_tokens * 0.70)

        if current_tokens <= target_limit or len(messages) <= 6:
            return list(messages)

        optimized = list(messages)
        # Always protect first message (root prompt) and last 6 messages
        protect_start = 1
        protect_end = max(1, len(optimized) - 6)

        # 1. Prune large tool results in the middle turns
        for i in range(protect_start, protect_end):
            msg = optimized[i]
            if isinstance(msg, UserMessage) and isinstance(msg.content, list):
                new_blocks = []
                modified = False
                for b in msg.content:
                    if isinstance(b, ToolResultBlock):
                        content_str = str(b.content)
                        # If tool result is huge and was not an error
                        if len(content_str) > 600 and not b.is_error:
                            # Prune to short summary
                            line_count = len(content_str.splitlines())
                            preview = "\n".join(content_str.splitlines()[:5])
                            summary = (
                                f"{preview}\n\n[... {line_count - 5} lines omitted by ContextEngine "
                                f"for token optimization ...]"
                            )
                            new_blocks.append(ToolResultBlock(
                                tool_use_id=b.tool_use_id,
                                content=summary,
                                is_error=b.is_error,
                            ))
                            modified = True
                        else:
                            new_blocks.append(b)
                    else:
                        new_blocks.append(b)

                if modified:
                    optimized[i] = UserMessage(content=new_blocks, uuid=msg.uuid)

        # Check token count again after tool pruning
        if self.estimate_tokens(optimized) <= target_limit:
            return optimized

        # 2. If still exceeding limit, apply smart compaction
        return self.smart_compact(optimized, preserve_recent=5)

    def select_tools(self, tools: list[Tool], user_prompt: str, project_type: str = "") -> list[Tool]:
        """Select only tools likely needed for this prompt to minimize schema token overhead."""
        prompt_lower = user_prompt.lower()
        selected: list[Tool] = []

        # Tool category classifiers
        search_keywords = ["search", "google", "web", "find on internet", "docs", "documentation", "fetch", "url", "http"]
        mcp_keywords = ["mcp", "model context", "external server", "resource"]
        lsp_keywords = ["lsp", "definition", "type", "references", "signature", "diagnostics"]
        notebook_keywords = ["notebook", "jupyter", ".ipynb", "cells"]
        powershell_keywords = ["powershell", "ps1", "windows command"]
        cron_keywords = ["cron", "schedule", "periodic", "timer"]
        team_keywords = ["team", "subagent", "teammate", "delegate", "worker", "coordinate"]
        plan_keywords = ["plan", "spec", "architecture", "design", "step by step"]
        worktree_keywords = ["worktree", "git worktree", "isolate"]

        for tool in tools:
            # 1. Core tools are ALWAYS enabled
            if getattr(tool, "is_core", False) or tool.name in (
                "Bash", "Read", "FileRead", "Write", "FileWrite", "Edit", "FileEdit", "Grep", "Glob"
            ):
                selected.append(tool)
                continue

            name = tool.name
            # 2. Conditional inclusion based on query relevance
            if name in ("WebSearch", "WebFetch", "WebSearchTool", "WebFetchTool"):
                if any(k in prompt_lower for k in search_keywords):
                    selected.append(tool)
            elif name in ("LSPTool", "LSP"):
                if any(k in prompt_lower for k in lsp_keywords):
                    selected.append(tool)
            elif name in ("NotebookEditTool", "NotebookEdit"):
                if any(k in prompt_lower for k in notebook_keywords) or ".ipynb" in prompt_lower:
                    selected.append(tool)
            elif name in ("PowerShellTool", "PowerShell"):
                if any(k in prompt_lower for k in powershell_keywords):
                    selected.append(tool)
            elif name in ("CronCreateTool", "CronDeleteTool", "CronListTool"):
                if any(k in prompt_lower for k in cron_keywords):
                    selected.append(tool)
            elif name in ("TeamCreateTool", "TeamDeleteTool", "SendMessageTool", "AgentTool"):
                if any(k in prompt_lower for k in team_keywords):
                    selected.append(tool)
            elif name in ("EnterPlanModeTool", "ExitPlanModeTool"):
                if any(k in prompt_lower for k in plan_keywords):
                    selected.append(tool)
            elif name in ("EnterWorktreeTool", "ExitWorktreeTool"):
                if any(k in prompt_lower for k in worktree_keywords):
                    selected.append(tool)
            elif name.startswith("mcp__") or name in ("MCPTool", "McpAuth", "ListMcpResources", "ReadMcpResource"):
                # If prompt mentions MCP or external server, or if user explicitly invoked MCP
                if any(k in prompt_lower for k in mcp_keywords) or name.startswith("mcp__"):
                    selected.append(tool)
            else:
                # Default include if ambiguous or small registry
                if len(tools) <= 25:
                    selected.append(tool)

        return selected if selected else tools

    def smart_compact(self, messages: list[Message], preserve_recent: int = 5) -> list[Message]:
        """Compact conversation into a concise summary while preserving critical details."""
        if len(messages) <= preserve_recent + 1:
            return list(messages)

        # Preserve the root user message
        root_message = messages[0]
        # Preserve the recent messages
        recent_messages = messages[-preserve_recent:]
        # Middle messages to summarize
        middle_messages = messages[1:-preserve_recent]

        files_modified: set[str] = set()
        files_read: set[str] = set()
        tools_executed: list[str] = []
        errors_encountered: list[str] = []
        key_decisions: list[str] = []

        for m in middle_messages:
            if isinstance(m, AssistantMessage):
                for b in m.content:
                    if isinstance(b, ToolUseBlock):
                        tools_executed.append(b.name)
                        fp = b.input.get("file_path", "")
                        if fp:
                            if b.name in ("Edit", "Write", "FileEdit", "FileWrite"):
                                files_modified.add(fp)
                            elif b.name in ("Read", "FileRead"):
                                files_read.add(fp)
                # Capture reasoning
                text = m.get_text().strip()
                if text and len(text) < 200:
                    key_decisions.append(text)

            elif isinstance(m, UserMessage):
                for b in m.content if isinstance(m.content, list) else []:
                    if isinstance(b, ToolResultBlock) and b.is_error:
                        err_line = str(b.content).splitlines()[0][:100]
                        errors_encountered.append(err_line)

        # Formulate structured summary
        summary_parts = [
            "## Summary of Previous Turns (Compacted)",
            f"- Tools invoked: {', '.join(set(tools_executed)) if tools_executed else 'none'}",
        ]
        if files_read:
            summary_parts.append(f"- Files inspected: {', '.join(list(files_read)[:8])}")
        if files_modified:
            summary_parts.append(f"- Files modified: {', '.join(list(files_modified)[:8])}")
        if errors_encountered:
            summary_parts.append(f"- Past errors encountered: {'; '.join(errors_encountered[:4])}")
        if key_decisions:
            summary_parts.append(f"- Key context: {'; '.join(key_decisions[:3])}")

        compact_msg = CompactBoundaryMessage(summary="\n".join(summary_parts))
        return [root_message, compact_msg] + recent_messages

    def diff_aware_context(
        self,
        file_path: str,
        original_content: str,
        new_content: str,
        context_lines: int = 3,
    ) -> str:
        """Generate unified diff context to inject only relevant changed hunks."""
        orig_lines = original_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = list(difflib.unified_diff(
            orig_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            n=context_lines,
        ))

        if not diff:
            return f"# No changes in {file_path}"

        return "".join(diff)


# Global singleton
_context_engine: ContextEngine | None = None


def get_context_engine() -> ContextEngine:
    global _context_engine
    if _context_engine is None:
        _context_engine = ContextEngine()
    return _context_engine
