"""
Advanced Swarm UI integration (tmux).
Spawns background agents into visible tmux panes when available.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Any


class SwarmUIManager:
    """Manages spawning agents in UI panes (tmux)."""

    def __init__(self):
        self.tmux_available = shutil.which("tmux") is not None
        self.in_tmux = "TMUX" in os.environ

    def spawn_agent_pane(self, agent_name: str, task: str) -> bool:
        """Attempt to spawn the agent in a new visible pane."""
        if not self.tmux_available:
            return False

        if not self.in_tmux:
            # Not currently in a tmux session. We could start one, but 
            # normally we only split if already inside.
            return False

        try:
            # We construct the command to run lucy with the task directly
            # in non-interactive mode.
            import sys
            safe_task = task.replace('"', '\\"')
            cmd = f'{sys.executable} -m lucy --prompt "{safe_task}"'
            
            # Split window horizontally, running the command and keeping it open briefly
            tmux_cmd = [
                "tmux", "split-window", "-h", "-l", "40",
                f"{cmd} ; read -t 5 -p 'Agent finished. Press enter to close...'"
            ]
            
            subprocess.run(tmux_cmd, check=True)
            return True
            
        except Exception as e:
            print(f"Failed to spawn tmux pane: {e}")
            return False


_swarm_ui: SwarmUIManager | None = None

def get_swarm_ui() -> SwarmUIManager:
    global _swarm_ui
    if _swarm_ui is None:
        _swarm_ui = SwarmUIManager()
    return _swarm_ui
