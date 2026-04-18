"""
AskUserQuestion tool — pause and ask the user a structured question.

Mirrors OpenCode's AskUserQuestionTool.
"""

from __future__ import annotations

from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


class AskUserQuestionTool(Tool):
    @property
    def name(self) -> str:
        return "AskUserQuestion"

    @property
    def aliases(self) -> list[str]:
        return ["AskUser", "Question"]

    @property
    def description(self) -> str:
        return "Ask the user a question and wait for their response"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of choices to present",
                },
                "default": {
                    "type": "string",
                    "description": "Default answer if user presses Enter",
                },
            },
            "required": ["question"],
        }

    def get_prompt(self) -> str:
        return (
            "Ask the user a question when you need clarification or a decision. "
            "Use this when the task is ambiguous and you need user input to proceed. "
            "If options are provided, the user will be presented with a choice list. "
            "Do NOT use this for trivial confirmations — only for genuine decisions."
        )

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        question = tool_input.get("question", "")
        options = tool_input.get("options", [])
        default = tool_input.get("default", "")

        if not question:
            return ToolResult(error="Question is required")

        if not context.is_interactive:
            if default:
                return ToolResult(data=f"[Non-interactive mode] Using default: {default}")
            return ToolResult(error="Cannot ask user in non-interactive mode and no default provided")

        # Display question
        prompt_str = f"\n❓ {question}"
        if options:
            prompt_str += "\n"
            for i, opt in enumerate(options, 1):
                prompt_str += f"  {i}. {opt}\n"
            prompt_str += "Enter number or text"
        if default:
            prompt_str += f" [{default}]"
        prompt_str += ": "

        try:
            import sys
            print(prompt_str, end="", flush=True)
            answer = input("").strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""

        if not answer and default:
            answer = default

        # If numbered options, resolve
        if options and answer.isdigit():
            idx = int(answer) - 1
            if 0 <= idx < len(options):
                answer = options[idx]

        return ToolResult(data=f"User answered: {answer}")

    def get_activity_description(self, tool_input: dict[str, Any] | None = None) -> str | None:
        if tool_input:
            q = tool_input.get("question", "")[:50]
            return f"Asking: {q}"
        return "Asking user a question"
