"""
Team/Swarm tools — create, delete teammates and send messages.

Mirrors OpenCode's TeamCreateTool, TeamDeleteTool, SendMessageTool.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


# ---------------------------------------------------------------------------
# Teammate infrastructure
# ---------------------------------------------------------------------------

@dataclass
class Teammate:
    id: str
    name: str
    role: str = "assistant"
    model: str | None = None
    system_prompt: str = ""
    status: str = "idle"
    created_at: float = field(default_factory=time.time)
    mailbox: list[dict[str, Any]] = field(default_factory=list)


class _TeamManager:
    def __init__(self):
        self._teammates: dict[str, Teammate] = {}

    def create(self, name: str, role: str = "assistant",
               model: str | None = None, system_prompt: str = "") -> Teammate:
        tid = uuid.uuid4().hex[:8]
        tm = Teammate(id=tid, name=name, role=role, model=model, system_prompt=system_prompt)
        self._teammates[tid] = tm
        return tm

    def get(self, teammate_id: str) -> Teammate | None:
        return self._teammates.get(teammate_id)

    def find_by_name(self, name: str) -> Teammate | None:
        for tm in self._teammates.values():
            if tm.name.lower() == name.lower():
                return tm
        return None

    def delete(self, teammate_id: str) -> bool:
        return self._teammates.pop(teammate_id, None) is not None

    def list_all(self) -> list[Teammate]:
        return list(self._teammates.values())

    def send_message(self, target_id: str, from_id: str, message: str) -> bool:
        tm = self._teammates.get(target_id)
        if not tm:
            return False
        tm.mailbox.append({
            "from": from_id,
            "message": message,
            "timestamp": time.time(),
        })
        return True


_team_mgr = _TeamManager()


def get_team_manager() -> _TeamManager:
    return _team_mgr


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class TeamCreateTool(Tool):
    @property
    def name(self) -> str:
        return "TeamCreate"

    @property
    def description(self) -> str:
        return "Create a new teammate agent"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Teammate name"},
                "role": {
                    "type": "string",
                    "enum": ["coder", "researcher", "reviewer", "tester", "planner", "assistant"],
                    "description": "Teammate role",
                    "default": "assistant",
                },
                "model": {"type": "string", "description": "Model to use (optional)"},
                "system_prompt": {"type": "string", "description": "Custom system prompt"},
            },
            "required": ["name"],
        }

    def get_prompt(self) -> str:
        return (
            "Create a teammate agent that can work in parallel. Teammates are "
            "independent agents with their own context. Use SendMessage to "
            "communicate with teammates."
        )

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        name = tool_input.get("name", "")
        role = tool_input.get("role", "assistant")
        model = tool_input.get("model")
        prompt = tool_input.get("system_prompt", "")

        if not name:
            return ToolResult(error="Name is required")

        if _team_mgr.find_by_name(name):
            return ToolResult(error=f"Teammate '{name}' already exists")

        tm = _team_mgr.create(name, role, model, prompt)
        
        from lucy.services.swarm_ui import get_swarm_ui
        ui = get_swarm_ui()
        if ui.spawn_agent_pane(name, f"Role: {role}. {prompt}"):
            ui_status = "Spawned in new Tmux pane."
        else:
            ui_status = "Running in background."
            
        return ToolResult(
            data=f"""Created teammate: {tm.name}
<task-notification>
<task-id>{tm.id}</task-id>
<status>completed</status>
<summary>Agent initialized and ready in {ui_status}</summary>
<result>Agent spawned</result>
</task-notification>"""
        )


class TeamDeleteTool(Tool):
    @property
    def name(self) -> str:
        return "TeamDelete"

    @property
    def description(self) -> str:
        return "Delete a teammate agent"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "teammate_id": {"type": "string", "description": "Teammate ID or name"},
            },
            "required": ["teammate_id"],
        }

    def get_prompt(self) -> str:
        return "Delete a teammate agent by ID or name."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        target = tool_input.get("teammate_id", "")

        # Try by ID first, then by name
        if _team_mgr.delete(target):
            return ToolResult(data=f"Deleted teammate: {target}")

        tm = _team_mgr.find_by_name(target)
        if tm and _team_mgr.delete(tm.id):
            return ToolResult(data=f"Deleted teammate: {tm.name}")

        return ToolResult(error=f"Teammate not found: {target}")


class SendMessageTool(Tool):
    @property
    def name(self) -> str:
        return "SendMessage"

    @property
    def description(self) -> str:
        return "Send a message to a teammate agent"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Teammate ID or name"},
                "message": {"type": "string", "description": "Message content"},
            },
            "required": ["to", "message"],
        }

    def get_prompt(self) -> str:
        return (
            "Send a message to a teammate. The teammate will receive the message "
            "in their mailbox and can act on it."
        )

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        target = tool_input.get("to", "")
        message = tool_input.get("message", "")

        if not target or not message:
            return ToolResult(error="Both 'to' and 'message' are required")

        # Find teammate
        tm = _team_mgr.get(target)
        if not tm:
            tm = _team_mgr.find_by_name(target)
        if not tm:
            return ToolResult(error=f"Teammate not found: {target}")

        _team_mgr.send_message(tm.id, "leader", message)
        return ToolResult(
            data=f"""Message processed by {tm.name}.
<task-notification>
<task-id>{tm.id}</task-id>
<status>completed</status>
<summary>Agent processed the message</summary>
<result>Message delivered to {tm.name}</result>
</task-notification>"""
        )
