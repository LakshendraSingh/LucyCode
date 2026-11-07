"""
Browser automation service for LucyCode workstation automation.

Supports Playwright (when available), Selenium fallback, and native macOS
AppleScript/system default browser interaction with zero required external dependencies.
"""

from __future__ import annotations

import asyncio
import base64
import enum
import html
import logging
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Check optional drivers
try:
    from playwright.async_api import async_playwright
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class BrowserBackend(enum.Enum):
    PLAYWRIGHT = "playwright"
    SELENIUM = "selenium"
    SYSTEM_DEFAULT = "system_default"


@dataclass
class BrowserTab:
    """Represents an open browser tab."""
    id: str
    url: str
    title: str
    is_active: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "is_active": self.is_active,
        }


@dataclass
class PageElement:
    """DOM node descriptor."""
    selector: str
    tag: str
    text: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    visible: bool = True


@dataclass
class BrowserResult:
    """Return envelope for browser operations."""
    success: bool
    output: str
    error: str | None = None
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "data": self.data,
        }


class BrowserAutomationService:
    """Cross-backend browser automation manager."""

    def __init__(self) -> None:
        self._backend = BrowserBackend.PLAYWRIGHT if _HAS_PLAYWRIGHT else BrowserBackend.SYSTEM_DEFAULT
        self._pw_instance: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._active_page: Any = None

    @property
    def backend(self) -> BrowserBackend:
        return self._backend

    async def _ensure_playwright(self) -> bool:
        """Initialize playwright browser instance if installed."""
        if not _HAS_PLAYWRIGHT:
            return False
        if self._browser is None:
            try:
                self._pw_instance = await async_playwright().start()
                self._browser = await self._pw_instance.chromium.launch(headless=False)
                self._context = await self._browser.new_context()
                self._active_page = await self._context.new_page()
            except Exception as e:
                logger.debug("Failed to start Playwright: %s, falling back to system default", e)
                self._backend = BrowserBackend.SYSTEM_DEFAULT
                return False
        return True

    async def open_url(self, url: str, new_tab: bool = False, browser_name: str | None = None) -> BrowserResult:
        """Open web URL in active browser, specific browser, or system default."""
        if not url.startswith(("http://", "https://", "file://")):
            url = f"https://{url}"

        if self._backend == BrowserBackend.PLAYWRIGHT and await self._ensure_playwright():
            try:
                if new_tab:
                    self._active_page = await self._context.new_page()
                await self._active_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                title = await self._active_page.title()
                return BrowserResult(success=True, output=f"Opened {url} (Title: {title})")
            except Exception as e:
                return BrowserResult(success=False, output="", error=f"Playwright navigation failed: {e}")

        # Native macOS browser open fallback
        try:
            if browser_name:
                cmd = ["open", "-a", browser_name, url]
            else:
                cmd = ["open", url]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if proc.returncode == 0:
                bname = browser_name or "default workstation"
                return BrowserResult(success=True, output=f"Opened {url} in {bname} browser.")
            return BrowserResult(success=False, output="", error=proc.stderr)
        except Exception as e:
            return BrowserResult(success=False, output="", error=str(e))

    async def get_tabs(self) -> list[BrowserTab]:
        """List open tabs across Chrome/Safari or Playwright."""
        tabs: list[BrowserTab] = []
        if self._backend == BrowserBackend.PLAYWRIGHT and self._context:
            for i, p in enumerate(self._context.pages):
                tabs.append(
                    BrowserTab(
                        id=str(i),
                        url=p.url,
                        title=await p.title(),
                        is_active=(p == self._active_page),
                    )
                )
            return tabs

        # macOS AppleScript query for Chrome
        ascript_chrome = """
        tell application "System Events"
            set isRunning to (name of processes) contains "Google Chrome"
        end tell
        if isRunning then
            tell application "Google Chrome"
                set output to ""
                repeat with w in windows
                    repeat with t in tabs of w
                        set output to output & (id of t) & "|||" & (URL of t) & "|||" & (title of t) & "\n"
                    end repeat
                end repeat
                return output
            end tell
        end if
        return ""
        """
        try:
            proc = subprocess.run(["osascript", "-e", ascript_chrome], capture_output=True, text=True, timeout=5)
            if proc.returncode == 0 and proc.stdout.strip():
                for line in proc.stdout.strip().splitlines():
                    parts = line.split("|||")
                    if len(parts) >= 3:
                        tabs.append(BrowserTab(id=parts[0].strip(), url=parts[1].strip(), title=parts[2].strip()))
        except Exception:
            pass

        return tabs

    async def get_current_url(self) -> str:
        """Return the URL of the active webpage."""
        if self._backend == BrowserBackend.PLAYWRIGHT and self._active_page:
            return self._active_page.url

        # AppleScript query for active tab in Safari or Chrome
        ascript = """
        tell application "System Events"
            set isSafari to (name of processes) contains "Safari"
            set isChrome to (name of processes) contains "Google Chrome"
        end tell
        if isSafari then
            tell application "Safari"
                if (count of windows) > 0 then
                    return URL of front document
                end if
            end tell
        else if isChrome then
            tell application "Google Chrome"
                if (count of windows) > 0 then
                    return URL of active tab of front window
                end if
            end tell
        end if
        return ""
        """
        try:
            proc = subprocess.run(["osascript", "-e", ascript], capture_output=True, text=True, timeout=3)
            return proc.stdout.strip()
        except Exception:
            return ""

    async def get_page_title(self) -> str:
        """Return current page title."""
        if self._backend == BrowserBackend.PLAYWRIGHT and self._active_page:
            return await self._active_page.title()

        ascript = """
        tell application "Google Chrome"
            if (count of windows) > 0 then
                return title of active tab of front window
            end if
        end tell
        return ""
        """
        try:
            proc = subprocess.run(["osascript", "-e", ascript], capture_output=True, text=True, timeout=3)
            return proc.stdout.strip()
        except Exception:
            return ""

    async def get_page_text(self) -> str:
        """Extract primary readable plain text from current page."""
        if self._backend == BrowserBackend.PLAYWRIGHT and self._active_page:
            try:
                return await self._active_page.inner_text("body")
            except Exception as e:
                return f"Error reading text: {e}"

        # URL extraction fallback via urllib
        url = await self.get_current_url()
        if url.startswith("http"):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "LucyCode-Workstation/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw_html = resp.read().decode("utf-8", errors="ignore")
                # Strip scripts and tags
                clean = re.sub(r"<script.*?</script>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
                clean = re.sub(r"<style.*?</style>", "", clean, flags=re.DOTALL | re.IGNORECASE)
                clean = re.sub(r"<[^>]+>", " ", clean)
                return html.unescape(re.sub(r"\s+", " ", clean).strip())
            except Exception as e:
                return f"Could not fetch page text: {e}"

        return "No active webpage found or unsupported browser backend."

    async def get_page_html(self) -> str:
        """Fetch full HTML DOM."""
        if self._backend == BrowserBackend.PLAYWRIGHT and self._active_page:
            return await self._active_page.content()
        url = await self.get_current_url()
        if url.startswith("http"):
            req = urllib.request.Request(url, headers={"User-Agent": "LucyCode-Workstation/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        return ""

    async def click(self, selector: str) -> BrowserResult:
        """Click DOM element matching selector."""
        if self._backend == BrowserBackend.PLAYWRIGHT and self._active_page:
            try:
                await self._active_page.click(selector, timeout=10000)
                return BrowserResult(success=True, output=f"Clicked element: {selector}")
            except Exception as e:
                return BrowserResult(success=False, output="", error=str(e))

        # Native DOM click fallback for Safari and Chrome via AppleScript evaluate_js
        js_code = f"(() => {{ const el = document.querySelector('{selector}'); if (el) {{ el.click(); return 'OK'; }} return 'NOT_FOUND'; }})()"
        res = await self.evaluate_js(js_code)
        if res == "OK":
            return BrowserResult(success=True, output=f"Clicked element: {selector}")
        return BrowserResult(success=False, output="", error=f"Could not click '{selector}': {res}")

    async def type_text(self, selector: str, text: str, clear_first: bool = True) -> BrowserResult:
        """Input text into form element."""
        if self._backend == BrowserBackend.PLAYWRIGHT and self._active_page:
            try:
                if clear_first:
                    await self._active_page.fill(selector, text, timeout=10000)
                else:
                    await self._active_page.type(selector, text, timeout=10000)
                return BrowserResult(success=True, output=f"Typed text into {selector}")
            except Exception as e:
                return BrowserResult(success=False, output="", error=str(e))

        # Native DOM input fallback for Safari and Chrome via AppleScript evaluate_js
        escaped_val = text.replace('\\', '\\\\').replace('"', '\\"')
        js_code = f"(() => {{ const el = document.querySelector('{selector}'); if (el) {{ el.focus(); el.value = '{escaped_val}'; el.dispatchEvent(new Event('input', {{bubbles: true}})); el.dispatchEvent(new Event('change', {{bubbles: true}})); return 'OK'; }} return 'NOT_FOUND'; }})()"
        res = await self.evaluate_js(js_code)
        if res == "OK":
            return BrowserResult(success=True, output=f"Typed text into {selector}")
        return BrowserResult(success=False, output="", error=f"Could not type into '{selector}': {res}")

    async def scroll(self, x: int = 0, y: int = 500) -> BrowserResult:
        """Scroll viewport."""
        if self._backend == BrowserBackend.PLAYWRIGHT and self._active_page:
            try:
                await self._active_page.evaluate(f"window.scrollBy({x}, {y})")
                return BrowserResult(success=True, output=f"Scrolled by ({x}, {y})")
            except Exception as e:
                return BrowserResult(success=False, output="", error=str(e))

        # Desktop scroll fallback
        from lucy.services.computer_use import get_computer_use_service
        get_computer_use_service().mouse_scroll(dx=x, dy=-max(1, y // 100))
        return BrowserResult(success=True, output=f"Dispatched desktop mouse scroll ({x}, {y})")

    async def wait_for_selector(self, selector: str, timeout: float = 10.0) -> bool:
        """Wait until element is attached and visible."""
        if self._backend == BrowserBackend.PLAYWRIGHT and self._active_page:
            try:
                await self._active_page.wait_for_selector(selector, timeout=int(timeout * 1000))
                return True
            except Exception:
                return False
        return False

    async def take_screenshot(self, path: str = "/tmp/lucy_browser.png") -> str:
        """Capture browser viewport screenshot and return base64 string."""
        if self._backend == BrowserBackend.PLAYWRIGHT and self._active_page:
            raw = await self._active_page.screenshot(path=path)
            return base64.b64encode(raw).decode("utf-8")

        # Desktop screenshot fallback
        from lucy.services.screen_automation import get_screen_automation
        b64 = get_screen_automation().screenshot()
        with open(path, "wb") as f:
            f.write(base64.b64decode(b64))
        return b64

    async def evaluate_js(self, script: str) -> Any:
        """Run JavaScript in active page context in Safari or Chrome."""
        if self._backend == BrowserBackend.PLAYWRIGHT and self._active_page:
            return await self._active_page.evaluate(script)

        # AppleScript JS injection into Safari or Chrome
        escaped_script = script.replace('"', '\\"')
        ascript = f"""
        tell application "System Events"
            set isSafari to (name of processes) contains "Safari"
            set isChrome to (name of processes) contains "Google Chrome"
        end tell
        if isSafari then
            tell application "Safari"
                if (count of windows) > 0 then
                    return do JavaScript "{escaped_script}" in current tab of front window
                end if
            end tell
        else if isChrome then
            tell application "Google Chrome"
                if (count of windows) > 0 then
                    return execute active tab of front window javascript "{escaped_script}"
                end if
            end tell
        end if
        return ""
        """
        try:
            proc = subprocess.run(["osascript", "-e", ascript], capture_output=True, text=True, timeout=5)
            return proc.stdout.strip()
        except Exception as e:
            return f"Error executing JS via AppleScript: {e}"

    async def search_web_and_read(self, query: str, engine: str = "duckduckgo") -> str:
        """
        Execute web search via DuckDuckGo Lite and parse clean textual summaries.
        Zero third-party library dependencies.
        """
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://lite.duckduckgo.com/lite/?q={encoded_query}"

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept": "text/html",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="ignore")

            # Extract result snippets from DuckDuckGo lite HTML
            snippets: list[str] = []
            links = re.findall(r'<a[^>]+class=[\'"]result-link[\'"][^>]*href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>', content)
            summaries = re.findall(r'<td[^>]+class=[\'"]result-snippet[\'"][^>]*>(.*?)</td>', content, flags=re.DOTALL)

            for i, (link, title) in enumerate(links[:8]):
                clean_title = re.sub(r"<[^>]+>", "", title).strip()
                summary_text = re.sub(r"<[^>]+>", "", summaries[i]).strip() if i < len(summaries) else ""
                snippets.append(f"{i+1}. {clean_title}\n   URL: {link}\n   {summary_text}\n")

            if snippets:
                return "\n".join(snippets)

            # Fallback text cleaner
            plain = re.sub(r"<[^>]+>", " ", content)
            return re.sub(r"\s+", " ", plain)[:2000]
        except Exception as e:
            return f"Search failed: {e}"

    def _verify_youtube_playable(self, video_id: str) -> tuple[bool, str]:
        """Verify that a YouTube video is live, public, and playable (not deleted, private, or region-blocked)."""
        v_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            req = urllib.request.Request(
                v_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")

            status_match = re.search(r'\"playabilityStatus\":\{.*?\"status\":\"(.*?)\"', raw)
            status = status_match.group(1) if status_match else "UNKNOWN"
            if status != "OK":
                return False, ""

            t_match = re.search(r"<title>(.*?)</title>", raw)
            title = t_match.group(1).replace(" - YouTube", "").strip() if t_match else ""
            if not title or title.lower() in ("youtube", "video unavailable"):
                return False, ""

            return True, title
        except Exception:
            return False, ""

    async def play_youtube(
        self,
        query_or_url: str,
        timestamp: str | int = 0,
        browser_name: str | None = None,
    ) -> BrowserResult:
        """
        Search for a YouTube video, verify its playability, append the exact timestamp,
        and open/play it in the browser.
        Guarantees that broken/unavailable videos are filtered out.
        """
        # Parse timestamp string or int into total seconds
        def _parse_timestamp(ts: str | int) -> int:
            if isinstance(ts, (int, float)):
                return max(0, int(ts))
            s = str(ts).strip().lower()
            if not s:
                return 0
            if s.endswith("s"):
                s = s[:-1]
            if ":" in s:
                parts = s.split(":")
                try:
                    if len(parts) == 2:
                        return int(parts[0]) * 60 + int(parts[1])
                    elif len(parts) == 3:
                        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                except ValueError:
                    pass
            try:
                return max(0, int(float(s)))
            except ValueError:
                return 0

        seconds = _parse_timestamp(timestamp)
        target_video_id = ""
        target_title = ""

        # 1. Check if input is a direct YouTube video URL
        direct_match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", query_or_url)
        if direct_match:
            candidate_id = direct_match.group(1)
            is_ok, title = self._verify_youtube_playable(candidate_id)
            if is_ok:
                target_video_id = candidate_id
                target_title = title

        # 2. If not direct or direct video is unavailable, search YouTube dynamically
        if not target_video_id:
            search_query = query_or_url
            # Clean natural language prefixes/suffixes
            search_query = re.sub(r"^(?:play|open|watch)\s+", "", search_query, flags=re.IGNORECASE)
            search_query = re.sub(r"\s+at\s+\d+[:\d+]*.*$", "", search_query, flags=re.IGNORECASE)
            search_query = re.sub(r"\s+on\s+youtube.*$", "", search_query, flags=re.IGNORECASE).strip()

            encoded_q = urllib.parse.quote_plus(search_query)
            search_url = f"https://www.youtube.com/results?search_query={encoded_q}"
            try:
                req = urllib.request.Request(
                    search_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    html_content = resp.read().decode("utf-8", errors="ignore")

                # Extract candidates in rank order
                candidate_ids = list(dict.fromkeys(re.findall(r"/watch\?v=([a-zA-Z0-9_-]{11})", html_content)))
                for vid in candidate_ids[:8]:
                    is_ok, title = self._verify_youtube_playable(vid)
                    if is_ok:
                        target_video_id = vid
                        target_title = title
                        break
            except Exception as e:
                logger.warning("YouTube search request failed: %s", e)

        if not target_video_id:
            return BrowserResult(
                success=False,
                output="",
                error=f"Could not find an available YouTube video for query: '{query_or_url}'.",
            )

        # 3. Construct direct URL with timestamp parameter
        final_url = f"https://www.youtube.com/watch?v={target_video_id}"
        if seconds > 0:
            final_url += f"&t={seconds}s"

        # 4. Open in requested browser (or Safari on macOS by default)
        bname = browser_name or ("Safari" if sys.platform == "darwin" else None)
        open_res = await self.open_url(final_url, browser_name=bname)
        if not open_res.success:
            return open_res

        # Activate browser window on macOS so the video is frontmost
        if sys.platform == "darwin" and bname:
            try:
                subprocess.run(
                    ["osascript", "-e", f'tell application "{bname}" to activate'],
                    capture_output=True,
                    timeout=3,
                )
            except Exception:
                pass

        time_str = f" at {timestamp} ({seconds}s)" if seconds > 0 else ""
        return BrowserResult(
            success=True,
            output=f"Successfully opened and playing '{target_title}' on YouTube{time_str}.\nURL: {final_url}",
            data={"url": final_url, "video_id": target_video_id, "title": target_title, "timestamp_seconds": seconds},
        )

    async def close(self) -> None:
        """Tear down browser session."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
            self._active_page = None
        if self._pw_instance:
            try:
                await self._pw_instance.stop()
            except Exception:
                pass
            self._pw_instance = None


_browser_service: BrowserAutomationService | None = None


def get_browser_automation() -> BrowserAutomationService:
    global _browser_service
    if _browser_service is None:
        _browser_service = BrowserAutomationService()
    return _browser_service
