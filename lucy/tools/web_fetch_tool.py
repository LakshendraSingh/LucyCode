"""
WebFetch tool — fetch and convert web content.

Mirrors OpenCode's WebFetchTool (separate from WebSearchTool).
"""

from __future__ import annotations

import re
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult, PermissionBehavior, PermissionResult


class WebFetchTool(Tool):
    @property
    def name(self) -> str:
        return "WebFetch"

    @property
    def aliases(self) -> list[str]:
        return ["Fetch", "Curl"]

    @property
    def description(self) -> str:
        return "Fetch content from a URL and convert HTML to readable text"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch",
                },
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP headers",
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum response length in characters",
                    "default": 50000,
                },
                "format": {
                    "type": "string",
                    "enum": ["text", "html", "json", "raw"],
                    "description": "Output format",
                    "default": "text",
                },
            },
            "required": ["url"],
        }

    def get_prompt(self) -> str:
        return (
            "Fetch content from a URL. HTML is automatically converted to readable text. "
            "Use format='json' for API responses, 'raw' for unprocessed content. "
            "This is for reading web pages and API endpoints, not for search — "
            "use WebSearch for searching."
        )

    # Pre-approved domains that don't need permission
    PREAPPROVED = {
        "docs.python.org", "docs.rs", "developer.mozilla.org",
        "stackoverflow.com", "github.com", "raw.githubusercontent.com",
        "pypi.org", "npmjs.com", "crates.io", "pkg.go.dev",
        "en.wikipedia.org", "api.github.com",
    }

    async def check_permissions(self, tool_input: dict[str, Any], context: ToolContext) -> PermissionResult:
        if context.permission_mode == "auto_accept":
            return PermissionResult(behavior=PermissionBehavior.ALLOW, updated_input=tool_input)

        url = tool_input.get("url", "")
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            domain = parsed.hostname or ""
            if domain in self.PREAPPROVED or any(domain.endswith(f".{d}") for d in self.PREAPPROVED):
                return PermissionResult(behavior=PermissionBehavior.ALLOW, updated_input=tool_input)
        except Exception:
            pass

        return PermissionResult(
            behavior=PermissionBehavior.ASK,
            message=f"Fetch URL: {url[:100]}",
            updated_input=tool_input,
        )

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        url = tool_input.get("url", "")
        headers = tool_input.get("headers", {})
        max_length = tool_input.get("max_length", 50000)
        fmt = tool_input.get("format", "text")

        if not url:
            return ToolResult(error="URL is required")

        try:
            import aiohttp
        except ImportError:
            # Fallback to urllib
            return await self._fetch_urllib(url, headers, max_length, fmt)

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                default_headers = {"User-Agent": "LucyCode/1.0"}
                default_headers.update(headers)

                async with session.get(url, headers=default_headers) as response:
                    if response.status >= 400:
                        return ToolResult(error=f"HTTP {response.status}: {response.reason}")

                    content_type = response.headers.get("Content-Type", "")

                    if fmt == "json" or "json" in content_type:
                        data = await response.json()
                        import json
                        text = json.dumps(data, indent=2, ensure_ascii=False)
                    elif fmt == "raw":
                        text = await response.text()
                    else:
                        text = await response.text()
                        if "html" in content_type:
                            text = self._html_to_text(text)

                    if len(text) > max_length:
                        text = text[:max_length] + f"\n\n... (truncated, {len(text)} total chars)"

                    return ToolResult(data=text)

        except aiohttp.ClientError as e:
            return ToolResult(error=f"Fetch failed: {e}")
        except asyncio.TimeoutError:
            return ToolResult(error="Request timed out (30s)")

    async def _fetch_urllib(self, url, headers, max_length, fmt) -> ToolResult:
        import urllib.request
        import urllib.error

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LucyCode/1.0", **headers})
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode(errors="replace")
                content_type = resp.headers.get("Content-Type", "")

                if fmt == "json" or "json" in content_type:
                    import json
                    data = json.loads(raw)
                    text = json.dumps(data, indent=2, ensure_ascii=False)
                elif fmt == "raw":
                    text = raw
                else:
                    text = self._html_to_text(raw) if "html" in content_type else raw

                if len(text) > max_length:
                    text = text[:max_length] + f"\n\n... (truncated)"

                return ToolResult(data=text)

        except urllib.error.HTTPError as e:
            return ToolResult(error=f"HTTP {e.code}: {e.reason}")
        except Exception as e:
            return ToolResult(error=f"Fetch failed: {e}")

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Basic HTML to text conversion."""
        # Remove script and style
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # Convert common tags
        html = re.sub(r'<br\s*/?\s*>', '\n', html, flags=re.IGNORECASE)
        html = re.sub(r'<p[^>]*>', '\n\n', html, flags=re.IGNORECASE)
        html = re.sub(r'<h[1-6][^>]*>', '\n\n## ', html, flags=re.IGNORECASE)
        html = re.sub(r'</h[1-6]>', '\n', html, flags=re.IGNORECASE)
        html = re.sub(r'<li[^>]*>', '\n• ', html, flags=re.IGNORECASE)
        html = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>', r'[\1] ', html, flags=re.IGNORECASE)
        # Strip remaining tags
        html = re.sub(r'<[^>]+>', '', html)
        # Decode entities
        import html as html_mod
        text = html_mod.unescape(html)
        # Normalize whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()

    def get_activity_description(self, tool_input: dict[str, Any] | None = None) -> str | None:
        if tool_input:
            return f"Fetching {tool_input.get('url', '')[:60]}"
        return "Fetching URL"
