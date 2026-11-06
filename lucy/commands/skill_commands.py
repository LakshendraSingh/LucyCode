"""
Skill commands — /skill, /skills.

Commands for managing declarative, context-aware skills:
- /skill list — List all discovered skills (active and inactive)
- /skill activate <name> — Manually activate a skill
- /skill deactivate <name> — Manually deactivate a skill
- /skill info <name> — Show detailed skill metadata and instructions
- /skill create <name> [description] — Create a new skill in the workspace
- /skill refresh — Re-scan for skills across all directories
"""

from __future__ import annotations

import logging
from typing import Any

from lucy.core.commands import Command, CommandResult

logger = logging.getLogger(__name__)


class SkillCommand(Command):
    """Slash command to manage declarative skills."""

    @property
    def name(self) -> str:
        return "skill"

    @property
    def aliases(self) -> list[str]:
        return ["skills"]

    @property
    def description(self) -> str:
        return "Manage skills and domain-specific knowledge"

    @property
    def usage(self) -> str:
        return "/skill [list|activate|deactivate|info|create|refresh] [name]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.core.skills_engine import get_skills_engine

        engine = get_skills_engine()
        cwd = getattr(state, "cwd", None)
        engine.discover(cwd)

        parts = args.strip().split(None, 1)
        action = parts[0].lower() if parts else "list"
        target = parts[1].strip() if len(parts) > 1 else ""

        # ── 1. List skills ──
        if action == "list":
            skills = engine.list_skills()
            if not skills:
                return CommandResult(
                    output="No skills discovered.\nUse '/skill create <name>' to create one."
                )

            lines = ["Discovered Skills:\n"]
            active_count = 0
            for s in skills:
                is_active = s["is_active"]
                if is_active:
                    active_count += 1
                status = "🟢 [ACTIVE]" if is_active else "⚪ [      ]"
                source = f"({s['source_type']}, prio: {s['priority']})"
                lines.append(f"  {status} {s['name']} v{s['version']} {source}")
                if s["description"]:
                    lines.append(f"      {s['description']}")

                # Detail triggers
                triggers = []
                if s["always"]:
                    triggers.append("always")
                if s["project_files"]:
                    triggers.append(f"projects: {', '.join(s['project_files'][:3])}")
                if s["file_patterns"]:
                    triggers.append(f"files: {', '.join(s['file_patterns'][:3])}")
                if s["keywords"]:
                    kw_preview = ", ".join(s["keywords"][:4])
                    if len(s["keywords"]) > 4:
                        kw_preview += f" (+{len(s['keywords']) - 4} more)"
                    triggers.append(f"keywords: {kw_preview}")

                if triggers:
                    lines.append(f"      Triggers: {' | '.join(triggers)}")
                lines.append("")

            lines.append(
                f"Active: {active_count}/{len(skills)} skills.\n"
                "Use '/skill activate <name>' or '/skill deactivate <name>' to manage skills."
            )
            return CommandResult(output="\n".join(lines).strip())

        # ── 2. Activate skill ──
        if action == "activate":
            if not target:
                return CommandResult(error="Usage: /skill activate <name>")

            success = engine.activate(target)
            if success:
                skill = engine.get_skill(target)
                name = skill.metadata.name if skill else target
                return CommandResult(output=f"✅ Activated skill: {name}")
            return CommandResult(
                error=f"Skill not found: {target}\nUse '/skill list' to view available skills."
            )

        # ── 3. Deactivate skill ──
        if action == "deactivate":
            if not target:
                return CommandResult(error="Usage: /skill deactivate <name>")

            success = engine.deactivate(target)
            if success:
                return CommandResult(output=f"✅ Deactivated skill: {target}")
            return CommandResult(
                error=f"Skill not found or not active: {target}"
            )

        # ── 4. Show skill info ──
        if action == "info":
            if not target:
                return CommandResult(error="Usage: /skill info <name>")

            skill = engine.get_skill(target)
            if not skill:
                return CommandResult(error=f"Skill not found: {target}")

            meta = skill.metadata
            status_str = "🟢 Active" if skill.is_active else "⚪ Inactive"
            lines = [
                f"Skill: {meta.name} (v{meta.version})",
                f"Status:      {status_str}",
                f"Description: {meta.description or '(none)'}",
                f"Author:      {meta.author or '(unknown)'}",
                f"Source:      {skill.source_type} ({skill.source_path})",
                f"Priority:    {meta.priority}",
            ]
            if meta.tags:
                lines.append(f"Tags:        {', '.join(meta.tags)}")
            if meta.depends_on:
                lines.append(f"Depends On:  {', '.join(meta.depends_on)}")

            lines.append("\nActivation Triggers:")
            lines.append(f"  Always Active:  {meta.activates_on.always}")
            if meta.activates_on.project_files:
                lines.append(f"  Project Files:  {', '.join(meta.activates_on.project_files)}")
            if meta.activates_on.file_patterns:
                lines.append(f"  File Patterns:  {', '.join(meta.activates_on.file_patterns)}")
            if meta.activates_on.keywords:
                lines.append(f"  Keywords:       {', '.join(meta.activates_on.keywords)}")

            lines.append("\nInstructions:")
            instructions_preview = skill.instructions.strip()
            if len(instructions_preview) > 1000:
                instructions_preview = instructions_preview[:1000] + "\n... (truncated)"
            lines.append(instructions_preview or "(none)")

            return CommandResult(output="\n".join(lines))

        # ── 5. Create skill ──
        if action == "create":
            if not target:
                return CommandResult(error="Usage: /skill create <name> [description]")

            create_parts = target.split(None, 1)
            skill_name = create_parts[0]
            desc = create_parts[1] if len(create_parts) > 1 else f"Custom skill for {skill_name}"
            default_instructions = f"""# {skill_name.title()} Skill

## Purpose
{desc}

## Guidelines
- Follow domain-specific best practices
- Ensure thorough validation and error handling
"""
            try:
                created = engine.create_skill(
                    name=skill_name,
                    description=desc,
                    instructions=default_instructions,
                )
                return CommandResult(
                    output=f"✅ Created skill '{created.metadata.name}' at:\n{created.source_path}\n"
                           f"Edit the SKILL.md file to customize instructions and activation triggers."
                )
            except Exception as e:
                return CommandResult(error=f"Failed to create skill: {e}")

        # ── 6. Refresh skills ──
        if action in ("refresh", "reload"):
            skills = engine.discover(cwd, force_refresh=True)
            return CommandResult(
                output=f"✅ Refreshed skills. Discovered {len(skills)} skill(s)."
            )

        return CommandResult(
            error=f"Unknown skill action: '{action}'\nUsage: {self.usage}"
        )


def get_commands() -> list[Command]:
    """Return all skill command instances."""
    return [SkillCommand()]
