"""
Companion command — /companion, /pet, /dog.

Allows users to interact with their pixel art dog companion in the terminal:
petting, feeding treats, getting developer advice, or launching the live animated view.
"""

from __future__ import annotations

from typing import Any

from lucy.core.commands import Command, CommandResult


# Global singleton instance across REPL session
_GLOBAL_COMPANION = None


def _get_companion():
    global _GLOBAL_COMPANION
    if _GLOBAL_COMPANION is None:
        from lucy.tui.companion import DogCompanion
        _GLOBAL_COMPANION = DogCompanion(name="Pixel")
    return _GLOBAL_COMPANION


class CompanionCommand(Command):
    """Slash command to interact with the pixel art dog companion."""

    @property
    def name(self) -> str:
        return "companion"

    @property
    def aliases(self) -> list[str]:
        return ["pet", "dog", "puppy"]

    @property
    def description(self) -> str:
        return "Pixel art dog terminal companion (/companion [pet|feed|bark|sleep|live])"

    @property
    def usage(self) -> str:
        return "/companion [pet|feed|bark|sleep|say <text>|live]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        comp = _get_companion()
        sub = args.strip().lower()

        if sub in ("live", "play", "interactive", "run"):
            # Launch interactive animation loop
            comp.run_interactive()
            return CommandResult(output="")

        if sub in ("pet", "pat", "hug"):
            comp.pet()
            return CommandResult(output=comp.render_tui())

        if sub in ("feed", "treat", "bone", "snack"):
            comp.feed()
            return CommandResult(output=comp.render_tui())

        if sub in ("bark", "speak", "talk", "tip", "quote"):
            comp.bark()
            return CommandResult(output=comp.render_tui())

        if sub in ("sleep", "nap", "snooze", "wake"):
            comp.toggle_sleep()
            return CommandResult(output=comp.render_tui())

        if sub.startswith("say "):
            custom_msg = args.strip()[4:].strip()
            if custom_msg:
                comp.state.message = custom_msg
                comp.state.mood = "happy"
                return CommandResult(output=comp.render_tui())

        # Default: display companion
        return CommandResult(output=comp.render_tui())


def get_commands() -> list[Command]:
    """Return companion command instances."""
    return [CompanionCommand()]
