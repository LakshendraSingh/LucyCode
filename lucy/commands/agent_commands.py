"""
Agent commands — /agents.
"""

from __future__ import annotations

import json
import os
from typing import Any

from lucy.core.commands import Command, CommandResult


class AgentsCommand(Command):
    @property
    def name(self) -> str: return "agents"
    @property
    def aliases(self) -> list[str]: return ["agent"]
    @property
    def description(self) -> str: return "Manage custom agent configurations"
    @property
    def usage(self) -> str: return "/agents [list|create|edit|delete] [name]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        parts = args.strip().split(None, 1)
        action = parts[0] if parts else "list"
        target = parts[1] if len(parts) > 1 else ""

        agents_file = os.path.join(os.path.expanduser("~/.lucycode"), "agents.json")

        if action == "list":
            agents = _load_agents(agents_file)
            if not agents:
                return CommandResult(output="No custom agents configured.\nUse /agents create <name> to create one.")
            lines = ["Custom Agents:\n"]
            for name, cfg in agents.items():
                role = cfg.get("role", "assistant")
                model = cfg.get("model", "default")
                lines.append(f"  🤖 {name} ({role}) — model: {model}")
                if cfg.get("description"):
                    lines.append(f"     {cfg['description']}")
            return CommandResult(output="\n".join(lines))

        if action == "create":
            if not target:
                return CommandResult(error="Usage: /agents create <name>")
            agents = _load_agents(agents_file)
            agents[target] = {
                "name": target,
                "role": "assistant",
                "model": "",
                "description": "",
                "system_prompt": "",
            }
            _save_agents(agents_file, agents)
            return CommandResult(output=f"Created agent: {target}\nEdit with: /agents edit {target}")

        if action == "edit":
            if not target:
                return CommandResult(error="Usage: /agents edit <name>")
            agents = _load_agents(agents_file)
            if target not in agents:
                return CommandResult(error=f"Agent not found: {target}")
            import json
            return CommandResult(output=f"Agent config:\n{json.dumps(agents[target], indent=2)}")

        if action == "delete":
            if not target:
                return CommandResult(error="Usage: /agents delete <name>")
            agents = _load_agents(agents_file)
            if target in agents:
                del agents[target]
                _save_agents(agents_file, agents)
                return CommandResult(output=f"Deleted agent: {target}")
            return CommandResult(error=f"Agent not found: {target}")

        return CommandResult(error=f"Unknown action: {action}")


def _load_agents(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_agents(path: str, agents: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(agents, f, indent=2)


def get_commands() -> list[Command]:
    return [AgentsCommand()]
