"""
WebSearchTool — Search the web for information.

Uses a simple HTTP-based search approach as a foundation.
Can be extended with specific search API providers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class WebSearchTool(Tool):
    """Search the web for information."""

    @property
    def name(self) -> str:
        return "WebSearch"

    @property
    def aliases(self) -> list[str]:
        return ["Search", "Web"]

    @property
    def description(self) -> str:
        return "Search the web for information"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 5)",
                },
            },
            "required": ["query"],
        }

    def get_prompt(self) -> str:
        return (
            "Search the web for information. Returns summarized search results. "
            "Use this when you need current information, documentation, "
            "or anything not available in the local files."
        )

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    def is_concurrent_safe(self, tool_input: dict[str, Any]) -> bool:
        return True

    def get_activity_description(self, tool_input: dict[str, Any] | None = None) -> str | None:
        if tool_input:
            query = tool_input.get("query", "")
            return f"Searching: {query[:50]}" if query else "Searching the web"
        return "Searching the web"

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        query = tool_input.get("query", "")
        max_results = tool_input.get("max_results", 5)

        if not query:
            return ToolResult(error="query is required")

        # Try the DuckDuckGo instant answer API first (no API key needed)
        try:
            result = await _duckduckgo_search(query, max_results)
            if result:
                return ToolResult(data=result)
        except Exception as e:
            logger.debug("DuckDuckGo search failed: %s", e)

        # Fallback: use curl to search
        try:
            result = await _curl_search(query, max_results, context.cwd)
            if result:
                return ToolResult(data=result)
        except Exception as e:
            logger.debug("Curl search failed: %s", e)

        return ToolResult(
            error=(
                "Web search is not available. Possible reasons:\n"
                "- No internet connection\n"
                "- Search APIs are unreachable\n"
                "Consider using the Bash tool with curl to fetch specific URLs."
            )
        )


async def _duckduckgo_search(query: str, max_results: int) -> str | None:
    """Search using DuckDuckGo instant answer API."""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"

    proc = await asyncio.create_subprocess_exec(
        "curl", "-s", "-m", "10", url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)

    if proc.returncode != 0:
        return None

    try:
        data = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError:
        return None

    parts: list[str] = [f"Search results for: {query}\n"]

    # Abstract
    abstract = data.get("AbstractText", "")
    if abstract:
        source = data.get("AbstractSource", "")
        url_str = data.get("AbstractURL", "")
        parts.append(f"Summary ({source}): {abstract}")
        if url_str:
            parts.append(f"Source: {url_str}")
        parts.append("")

    # Related topics
    topics = data.get("RelatedTopics", [])
    count = 0
    for topic in topics:
        if count >= max_results:
            break
        text = topic.get("Text", "")
        first_url = topic.get("FirstURL", "")
        if text:
            parts.append(f"• {text}")
            if first_url:
                parts.append(f"  URL: {first_url}")
            count += 1

    # Answer
    answer = data.get("Answer", "")
    if answer:
        parts.append(f"\nDirect answer: {answer}")

    if len(parts) <= 1:
        return None

    return "\n".join(parts)


async def _curl_search(query: str, max_results: int, cwd: str) -> str | None:
    """Use curl to perform a basic search (fallback)."""
    # Use DuckDuckGo lite (text-only) as a fallback
    encoded = urllib.parse.quote_plus(query)
    url = f"https://lite.duckduckgo.com/lite/?q={encoded}"

    proc = await asyncio.create_subprocess_exec(
        "curl", "-s", "-m", "15", "-L",
        "-H", "User-Agent: Lucy Code/0.1",
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
    except asyncio.TimeoutError:
        return None

    if proc.returncode != 0:
        return None

    html = stdout.decode("utf-8", errors="replace")

    # Extract text snippets from HTML (very basic)
    import re

    # Remove tags
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) < 50:
        return None

    # Truncate to reasonable length
    if len(text) > 3000:
        text = text[:3000] + "..."

    return f"Search results for: {query}\n\n{text}"
