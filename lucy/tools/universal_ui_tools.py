"""
Universal UI Automation & Verification Tools for LucyCode.

Provides application-agnostic desktop and browser interaction tools:
- ui_inspect: Inspect frontmost application, active window, URL, buttons, and menus.
- ui_click: Deterministically click buttons or controls by label with verification.
- ui_menu: Navigate application menus (File > New, Edit > Select All, etc.) across any app.
- ui_type: Reliably paste or type text into fields without dropping characters.
- ui_verify: Verify completion conditions (window title, URL, element presence) to eliminate false positives.
"""

from __future__ import annotations

import json
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult
from lucy.services.universal_ui import get_universal_ui


class UIInspectTool(Tool):
    """Inspect active application, open windows, browser URL, buttons, and menus."""

    @property
    def name(self) -> str:
        return "ui_inspect"

    @property
    def description(self) -> str:
        return (
            "Inspect the frontmost desktop application or a named application. "
            "Returns the active window title, browser URL (if a browser), available top-level menus, "
            "visible buttons, and text fields. ALWAYS inspect the application before attempting actions "
            "to avoid false positives and verify the current state."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "app": {
                    "type": "string",
                    "description": "Optional application name to inspect (e.g. 'Safari', 'Microsoft Word', 'TextEdit'). If omitted, inspects frontmost app.",
                },
            },
        }

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    def get_prompt(self) -> str:
        return "Inspect application UI state, active window, and visible controls before taking action."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        ui = get_universal_ui()
        app = tool_input.get("app")
        data = ui.inspect(app)
        return ToolResult(data=json.dumps(data, indent=2))


class UIClickTool(Tool):
    """Click a button, link, or interactive UI control by label across any app."""

    @property
    def name(self) -> str:
        return "ui_click"

    @property
    def description(self) -> str:
        return (
            "Click an interactive UI button or control by label across any application. "
            "Verifies whether the element existed and reports failure if not found, preventing false positives."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Label, text, or accessibility name of the button or control to click (e.g. 'Compose', 'Send', 'New Document', 'Save').",
                },
                "app": {
                    "type": "string",
                    "description": "Optional application name. If omitted, targets the frontmost app.",
                },
            },
            "required": ["label"],
        }

    def get_prompt(self) -> str:
        return "Click buttons or UI elements deterministically with verification."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        ui = get_universal_ui()
        label = tool_input.get("label", "")
        app = tool_input.get("app")

        res = ui.click_element(app_name=app, label=label)
        if res.success:
            return ToolResult(data=json.dumps(res.to_dict(), indent=2))
        return ToolResult(error=res.message, data=json.dumps(res.to_dict(), indent=2))


class UIMenuTool(Tool):
    """Trigger application menu bar items deterministically (e.g. File > New)."""

    @property
    def name(self) -> str:
        return "ui_menu"

    @property
    def description(self) -> str:
        return (
            "Deterministically trigger a menu item from the macOS menu bar (e.g. ['File', 'New'], ['Edit', 'Paste'], ['File', 'Save']). "
            "Works universally on 100% of macOS applications without guessing keyboard shortcuts."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "app": {
                    "type": "string",
                    "description": "Application name containing the menu (e.g. 'Microsoft Word', 'TextEdit', 'Safari').",
                },
                "path": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Hierarchical path to the menu item (e.g. ['File', 'New'] or ['File', 'New Window']).",
                },
            },
            "required": ["app", "path"],
        }

    def get_prompt(self) -> str:
        return "Trigger menu items deterministically across any application."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        ui = get_universal_ui()
        app = tool_input.get("app", "")
        path = tool_input.get("path", [])

        res = ui.click_menu_item(app_name=app, menu_path=path)
        if res.success:
            return ToolResult(data=json.dumps(res.to_dict(), indent=2))
        return ToolResult(error=res.message, data=json.dumps(res.to_dict(), indent=2))


class UITypeTool(Tool):
    """Type or paste text into an application field or document."""

    @property
    def name(self) -> str:
        return "ui_type"

    @property
    def description(self) -> str:
        return (
            "Paste or type text into a specific labeled field or the active application window. "
            "Uses clipboard injection to guarantee zero dropped characters and instant throughput."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text, essay, message, or paragraph to write into the application.",
                },
                "field": {
                    "type": "string",
                    "description": "Optional label or description of the target field (e.g. 'To', 'Subject', 'Search').",
                },
                "app": {
                    "type": "string",
                    "description": "Target application name (e.g. 'Safari', 'Microsoft Word', 'TextEdit').",
                },
            },
            "required": ["text"],
        }

    def get_prompt(self) -> str:
        return "Type or paste text reliably into desktop applications."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        ui = get_universal_ui()
        text = tool_input.get("text", "")
        field_label = tool_input.get("field")
        app = tool_input.get("app")

        res = ui.type_into_element(app_name=app, text=text, field_label=field_label)
        if res.success:
            return ToolResult(data=json.dumps(res.to_dict(), indent=2))
        return ToolResult(error=res.message, data=json.dumps(res.to_dict(), indent=2))


class UIVerifyTool(Tool):
    """Verify task completion conditions to eliminate false positives."""

    @property
    def name(self) -> str:
        return "ui_verify"

    @property
    def description(self) -> str:
        return (
            "Verify that a task actually succeeded by checking live application state: "
            "active browser URL, window title, or element presence/absence. "
            "NEVER claim a task was completed without verifying the outcome."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "check": {
                    "type": "string",
                    "enum": ["url", "window_title", "button_exists", "button_gone", "window_closed"],
                    "description": "Verification check type.",
                },
                "expected": {
                    "type": "string",
                    "description": "Expected substring (e.g. 'mail.google.com', 'Sent', 'Document 1').",
                },
                "app": {
                    "type": "string",
                    "description": "Optional target application name (e.g. 'Safari', 'TextEdit').",
                },
            },
            "required": ["check", "expected"],
        }

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    def get_prompt(self) -> str:
        return "Verify that UI operations actually completed and prevent false positives."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        ui = get_universal_ui()
        check = tool_input.get("check", "")
        expected = tool_input.get("expected", "")
        app = tool_input.get("app")

        res = ui.verify(app_name=app, check_type=check, expected_value=expected)
        is_verified = res.get("verified", False)
        if is_verified:
            return ToolResult(data=f"Verification PASSED: {res.get('details')}")
        return ToolResult(
            error=f"Verification FAILED: {res.get('details')}. Expected '{expected}' for check '{check}'.",
            data=json.dumps(res, indent=2),
        )


UNIVERSAL_UI_TOOLS: list[Tool] = [
    UIInspectTool(),
    UIClickTool(),
    UIMenuTool(),
    UITypeTool(),
    UIVerifyTool(),
]
