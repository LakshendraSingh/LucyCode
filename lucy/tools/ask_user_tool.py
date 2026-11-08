"""
AskUserQuestion tool — pause and ask the user a structured question when unsure.

Allows the agent to prompt the user in the middle of its execution process
when facing ambiguous requirements, multiple valid options, or unexpected states.
"""

from __future__ import annotations

import sys
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


class AskUserQuestionTool(Tool):
    """Ask the user a question in the middle of execution when unsure."""

    @property
    def name(self) -> str:
        return "AskUserQuestion"

    @property
    def aliases(self) -> list[str]:
        return ["AskUser", "Question", "ask_user", "ask_user_question"]

    @property
    def description(self) -> str:
        return (
            "Prompt the user for input or a decision in the middle of execution if you are unsure, "
            "face ambiguous choices, or need human guidance to proceed. "
            "You can provide a list of structured options and a recommended default."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The specific question or decision for the user",
                },
                "context": {
                    "type": "string",
                    "description": "Brief explanation of why you are asking and what choices exist",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of choices or actions for the user to pick from",
                },
                "default": {
                    "type": "string",
                    "description": "Recommended default answer if the user presses Enter without typing",
                },
            },
            "required": ["question"],
        }

    def get_prompt(self) -> str:
        return (
            "Prompt the user whenever you are unsure, encounter ambiguity, or need clarification "
            "before proceeding with a critical or irreversible action. "
            "Always include structured options and a clear recommended default."
        )

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        question = tool_input.get("question") or tool_input.get("message", "")
        explanation = tool_input.get("context", "")
        raw_options = tool_input.get("options", [])
        default = tool_input.get("default", "")

        # Normalize options if passed as dicts or objects
        options: list[str] = []
        if isinstance(raw_options, list):
            for opt in raw_options:
                if isinstance(opt, dict):
                    options.append(str(opt.get("label") or opt.get("value") or opt))
                else:
                    options.append(str(opt))

        if not question:
            return ToolResult(error="Question is required")

        # Check if autonomous mode is active
        is_autonomous = (
            getattr(context, "autonomous", False)
            or context.permission_mode in ("auto_accept", "autonomous")
            or not context.is_interactive
        )

        if is_autonomous:
            chosen = default if default else (options[0] if options else "Proceed with standard best-practice default")
            return ToolResult(
                data=(
                    f"[Autonomous Mode Active] The user has enabled autonomous mode and cannot be prompted mid-task. "
                    f"Selected recommended default: '{chosen}'. "
                    "Do NOT pause for human confirmation or ask further questions; "
                    "make executive decisions autonomously and complete the assigned task."
                )
            )

        # Determine if we can interact with a live user
        can_prompt = context.is_interactive and (hasattr(sys.stdin, "isatty") and sys.stdin.isatty())

        if not can_prompt:
            chosen = default if default else (options[0] if options else "Proceed with standard default")
            return ToolResult(
                data=f"[Non-interactive mode] User unavailable. Selected recommended default: '{chosen}'."
            )

        # Format clean, prominent user prompt
        lines = [""]
        lines.append("────────────────────────────────────────────────────────────")
        lines.append(f"❓ Lucy Question: {question}")
        if explanation:
            lines.append(f"   Context: {explanation}")
        if options:
            lines.append("\nOptions:")
            for i, opt in enumerate(options, 1):
                is_def = " (Default)" if opt == default or (not default and i == 1) else ""
                lines.append(f"  {i}. {opt}{is_def}")
            lines.append("")
            prompt_label = "Select option number or enter text"
        else:
            prompt_label = "Your answer"

        if default:
            prompt_label += f" [{default}]"
        prompt_label += ": "

        prompt_str = "\n".join(lines) + "\n" + prompt_label

        try:
            print(prompt_str, end="", flush=True)
            answer = input("").strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""

        # Default resolution on empty Enter
        if not answer:
            if default:
                answer = default
            elif options:
                answer = options[0]

        # Numbered option resolution
        if options and answer.isdigit():
            idx = int(answer) - 1
            if 0 <= idx < len(options):
                answer = options[idx]

        return ToolResult(data=f"User selected / answered: '{answer}'")

    def get_activity_description(self, tool_input: dict[str, Any] | None = None) -> str | None:
        if tool_input:
            q = tool_input.get("question", "")[:50]
            return f"Prompting user: {q}"
        return "Prompting user for decision"
