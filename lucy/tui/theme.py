"""
Color themes for the TUI.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """Color palette for the terminal UI."""
    name: str
    # Core
    primary: str       # Main accent color
    secondary: str     # Secondary accent
    text: str          # Default text
    dim: str           # Dimmed text
    error: str         # Error messages
    warning: str       # Warnings
    success: str       # Success messages
    info: str          # Info/hints
    # Prompt
    prompt_user: str   # User prompt indicator
    prompt_ai: str     # AI response indicator
    # Tool colors
    tool_name: str     # Tool name
    tool_input: str    # Tool input
    tool_result: str   # Tool result
    tool_error: str    # Tool error
    # Thinking
    thinking: str      # Thinking text
    # Code
    code_bg: str       # Code block bg (not used in terminal)


THEMES: dict[str, Theme] = {
    "dark": Theme(
        name="dark",
        primary="bright_cyan",
        secondary="bright_magenta",
        text="white",
        dim="bright_black",
        error="red",
        warning="yellow",
        success="green",
        info="bright_blue",
        prompt_user="bright_green",
        prompt_ai="bright_cyan",
        tool_name="bright_yellow",
        tool_input="bright_black",
        tool_result="white",
        tool_error="bright_red",
        thinking="bright_black",
        code_bg="grey11",
    ),
    "light": Theme(
        name="light",
        primary="blue",
        secondary="magenta",
        text="black",
        dim="grey50",
        error="red",
        warning="dark_orange",
        success="dark_green",
        info="blue",
        prompt_user="dark_green",
        prompt_ai="blue",
        tool_name="dark_orange",
        tool_input="grey50",
        tool_result="black",
        tool_error="red",
        thinking="grey50",
        code_bg="grey93",
    ),
    "monokai": Theme(
        name="monokai",
        primary="#66d9ef",
        secondary="#ae81ff",
        text="#f8f8f2",
        dim="#75715e",
        error="#f92672",
        warning="#e6db74",
        success="#a6e22e",
        info="#66d9ef",
        prompt_user="#a6e22e",
        prompt_ai="#66d9ef",
        tool_name="#e6db74",
        tool_input="#75715e",
        tool_result="#f8f8f2",
        tool_error="#f92672",
        thinking="#75715e",
        code_bg="#272822",
    ),
}


def get_theme(name: str = "dark") -> Theme:
    return THEMES.get(name, THEMES["dark"])
