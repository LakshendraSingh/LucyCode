"""
Computer Use tool for interacting with the desktop.
"""

from __future__ import annotations

from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


class ComputerUseTool(Tool):
    """Tool for controlling the mouse and keyboard and taking screenshots."""

    @property
    def name(self) -> str:
        return "computer"

    @property
    def description(self) -> str:
        return "Control the mouse and keyboard, and take screenshots of the desktop."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "key", "type", "mouse_move", "left_click",
                        "right_click", "middle_click", "double_click",
                        "left_click_drag", "cursor_position", "screenshot"
                    ]
                },
                "text": {"type": "string"},
                "coordinate": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 2
                }
            },
            "required": ["action"]
        }

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.computer_use import get_computer_use_service
        service = get_computer_use_service()
        
        action = tool_input.get("action")
        
        try:
            if action == "screenshot":
                b64 = service.take_screenshot()
                return ToolResult(data=f"Screenshot taken. Base64 (first 50 chars): {b64[:50]}...")
                
            elif action == "mouse_move":
                coords = tool_input.get("coordinate")
                if not coords or len(coords) < 2:
                    return ToolResult(error="coordinate required for mouse_move")
                service.mouse_move(coords[0], coords[1])
                return ToolResult(data=f"Mouse moved to {coords[0]}, {coords[1]}")
                
            elif action == "left_click":
                service.mouse_click("left", 1)
                return ToolResult(data="Left clicked")
                
            elif action == "right_click":
                service.mouse_click("right", 1)
                return ToolResult(data="Right clicked")
                
            elif action == "double_click":
                service.mouse_click("left", 2)
                return ToolResult(data="Double clicked")
                
            elif action == "left_click_drag":
                coords = tool_input.get("coordinate")
                if not coords or len(coords) < 2:
                    return ToolResult(error="coordinate required for left_click_drag")
                service.mouse_drag(coords[0], coords[1])
                return ToolResult(data=f"Dragged to {coords[0]}, {coords[1]}")
                
            elif action == "type":
                text = tool_input.get("text", "")
                service.type_text(text)
                return ToolResult(data=f"Typed text: {text}")
                
            elif action == "key":
                text = tool_input.get("text", "")
                service.press_key(text)
                return ToolResult(data=f"Pressed key: {text}")
                
            else:
                return ToolResult(error=f"Unknown action: {action}")
                
        except Exception as e:
            return ToolResult(error=f"Computer use failed: {e}")

    def get_prompt(self) -> str:
        return (
            "Use this tool to interact with the user's desktop environment.\n"
            "You can take screenshots, move the mouse, click, and type text.\n"
            "Respect the user's desktop and only take actions when necessary to complete the task."
        )

    def is_destructive(self, tool_input: dict[str, Any]) -> bool:
        # Clicking and typing are destructive/state-changing
        return tool_input.get("action") not in ("screenshot", "cursor_position")
