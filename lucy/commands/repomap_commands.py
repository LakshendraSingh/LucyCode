"""
RepoMap command — /repomap.

Displays or refreshes the structural repository symbol map.
"""

from __future__ import annotations

import os
from typing import Any

from lucy.core.commands import Command, CommandResult


class RepoMapCommand(Command):
    """Slash command to view or refresh the architectural repo map."""

    @property
    def name(self) -> str:
        return "repomap"

    @property
    def aliases(self) -> list[str]:
        return ["map", "astmap"]

    @property
    def description(self) -> str:
        return "View or refresh the PageRank structural repository map"

    @property
    def usage(self) -> str:
        return "/repomap [refresh|stats]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.core.repomap import get_repo_map

        cwd = getattr(state, "cwd", os.getcwd())
        rm = get_repo_map(cwd)

        sub = args.strip().lower()
        if sub == "refresh":
            rm.scan_repo()
            return CommandResult(output=f"Repo map refreshed for {cwd}.")

        if sub == "stats":
            if not rm._cache:
                rm.scan_repo()
            total_files = len(rm._cache)
            total_symbols = sum(len(fs.symbols) for fs in rm._cache.values())
            top_files = sorted(rm._cache.values(), key=lambda fs: fs.centrality, reverse=True)[:5]
            top_str = "\n".join(f"  • {fs.path} (centrality: {fs.centrality:.2f})" for fs in top_files)
            return CommandResult(
                output=(
                    f"RepoMap Statistics:\n"
                    f"  Total Indexed Files: {total_files}\n"
                    f"  Total Extracted Symbols: {total_symbols}\n"
                    f"  Top Central Files:\n{top_str}"
                )
            )

        map_text = rm.render_map(max_tokens=1500)
        return CommandResult(output=f"=== Architectural Repository Map ===\n\n{map_text}")


def get_commands() -> list[Command]:
    return [RepoMapCommand()]

