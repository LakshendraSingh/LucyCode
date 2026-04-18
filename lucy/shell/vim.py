"""
Vim emulation mode using prompt_toolkit.
"""

from __future__ import annotations

from typing import Any

from prompt_toolkit.enums import EditingMode
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.vi_state import InputMode
from prompt_toolkit.filters import Condition
from prompt_toolkit.application import get_app


class VimManager:
    """Manages Vim emulation for the prompt_toolkit session."""

    def __init__(self, theme: Any = None):
        self.enabled = False
        self.theme = theme

    def toggle(self) -> bool:
        """Toggle Vim mode. Returns new state."""
        self.enabled = not self.enabled
        return self.enabled

    def get_editing_mode(self) -> EditingMode:
        """Get the current prompt_toolkit editing mode."""
        return EditingMode.VI if self.enabled else EditingMode.EMACS

    def get_bottom_toolbar(self, vi_state: Any) -> Any:
        """Return a formatted string for the bottom toolbar indicating Vi mode."""
        if not self.enabled or not vi_state:
            return None

        # vi_state is from prompt_toolkit application
        if vi_state.input_mode == InputMode.INSERT:
            mode = "INSERT"
            color = "ansigreen"
        elif vi_state.input_mode == InputMode.NAVIGATION:
            mode = "NORMAL"
            color = "ansiblue"
        elif vi_state.input_mode == InputMode.REPLACE:
            mode = "REPLACE"
            color = "ansired"
        else:
            mode = "VIM"
            color = "ansiwhite"

        from prompt_toolkit.formatted_text import HTML
        return HTML(f'<style bg="{color}" fg="ansiwhite"> -- {mode} -- </style>')

    def get_key_bindings(self) -> KeyBindings:
        """Get custom key bindings if needed."""
        kb = KeyBindings()
        
        # Example: bind 'jj' to Escape in Insert mode
        @kb.add('j', 'j', filter=Condition(lambda: self.enabled and get_app().vi_state.input_mode == InputMode.INSERT))
        def _(event):
            event.app.vi_state.input_mode = InputMode.NAVIGATION

        return kb


_manager: VimManager | None = None

def get_vim_manager(theme: Any = None) -> VimManager:
    global _manager
    if _manager is None:
        _manager = VimManager(theme)
    return _manager
