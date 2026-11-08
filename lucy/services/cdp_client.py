"""
Chrome DevTools Protocol (CDP) client for browser automation.

Provides direct, zero-dependency communication with Chromium-based browsers
(Google Chrome, Chromium, Brave, Microsoft Edge) via the Chrome DevTools
Protocol over WebSocket and HTTP.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class CDPElement:
    """Represents an interactive DOM element found via CDP."""
    tag: str
    id: str
    text: str
    role: str
    aria_label: str
    selector: str
    x: int
    y: int
    width: int
    height: int
    center_x: int
    center_y: int
    visible: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "id": self.id,
            "text": self.text,
            "role": self.role,
            "aria_label": self.aria_label,
            "selector": self.selector,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "center_x": self.center_x,
            "center_y": self.center_y,
            "visible": self.visible,
        }


@dataclass
class CDPClickResult:
    """Result of clicking an element via CDP."""
    success: bool
    element: CDPElement | None
    click_coordinates: tuple[int, int]
    navigation_occurred: bool
    initial_url: str
    final_url: str
    output: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "element": self.element.to_dict() if self.element else None,
            "click_coordinates": self.click_coordinates,
            "navigation_occurred": self.navigation_occurred,
            "initial_url": self.initial_url,
            "final_url": self.final_url,
            "output": self.output,
            "error": self.error,
        }


class _AsyncWebSocketClient:
    """Pure-Python RFC 6455 WebSocket client using asyncio streams."""

    def __init__(self, url: str) -> None:
        self.url = url
        parsed = urllib.parse.urlparse(url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 9222
        self.path = parsed.path or "/"
        if parsed.query:
            self.path += f"?{parsed.query}"
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._recv_task: asyncio.Task[None] | None = None
        self._on_message: Callable[[str], None] | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected and self.writer is not None and not self.writer.is_closing()

    async def connect(self, timeout: float = 5.0) -> None:
        """Perform HTTP Upgrade handshake to establish WebSocket connection."""
        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=timeout
        )

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.writer.write(handshake.encode("ascii"))
        await self.writer.drain()

        # Read response headers
        headers_data = await asyncio.wait_for(self.reader.readuntil(b"\r\n\r\n"), timeout=timeout)
        response_text = headers_data.decode("latin1", errors="replace")
        status_line = response_text.splitlines()[0] if response_text else ""
        if "101" not in status_line:
            raise ConnectionError(f"WebSocket upgrade rejected by server: {status_line}")

        self._connected = True

    def start_listening(self, on_message: Callable[[str], None]) -> None:
        """Start background receiver task."""
        self._on_message = on_message
        self._recv_task = asyncio.create_task(self._listen_loop())

    async def _listen_loop(self) -> None:
        """Read frames and dispatch incoming text payloads."""
        try:
            while self._connected and self.reader:
                text = await self._read_frame()
                if text is not None and self._on_message:
                    self._on_message(text)
        except (asyncio.CancelledError, ConnectionResetError, EOFError):
            pass
        except Exception as e:
            logger.debug("WebSocket listen loop stopped: %s", e)
        finally:
            self._connected = False

    async def _read_frame(self) -> str | None:
        """Read and decode a single RFC 6455 frame."""
        if not self.reader:
            return None

        # Read first 2 bytes
        head = await self.reader.readexactly(2)
        b1, b2 = head[0], head[1]
        fin = bool(b1 & 0x80)
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        payload_len = b2 & 0x7F

        # Close frame
        if opcode == 0x08:
            self._connected = False
            return None

        # Extended length
        if payload_len == 126:
            ext = await self.reader.readexactly(2)
            payload_len = struct.unpack("!H", ext)[0]
        elif payload_len == 127:
            ext = await self.reader.readexactly(8)
            payload_len = struct.unpack("!Q", ext)[0]

        # Mask key (from server, usually unmasked, but handle both)
        mask_key = None
        if masked:
            mask_key = await self.reader.readexactly(4)

        # Payload
        payload = await self.reader.readexactly(payload_len)
        if masked and mask_key:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

        # Ping frame -> reply with Pong
        if opcode == 0x09:
            await self._send_frame(payload, opcode=0x0A)
            return None

        if opcode == 0x01:  # Text frame
            return payload.decode("utf-8", errors="replace")

        return None

    async def send_text(self, text: str) -> None:
        """Send a masked text frame to the server."""
        payload = text.encode("utf-8")
        await self._send_frame(payload, opcode=0x01)

    async def _send_frame(self, payload: bytes, opcode: int = 0x01) -> None:
        """Construct and send an RFC 6455 frame."""
        if not self.writer or self.writer.is_closing():
            raise ConnectionError("WebSocket is not connected")

        header = bytearray([0x80 | opcode])
        length = len(payload)
        mask = os.urandom(4)

        if length <= 125:
            header.append(0x80 | length)
        elif length <= 65535:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))

        masked_payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        frame = bytes(header) + mask + masked_payload

        self.writer.write(frame)
        await self.writer.drain()

    async def close(self) -> None:
        """Close the WebSocket connection cleanly."""
        self._connected = False
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
        if self.writer and not self.writer.is_closing():
            try:
                # Send close frame
                await self._send_frame(b"", opcode=0x08)
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass


class CDPClient:
    """Chrome DevTools Protocol (CDP) client."""

    def __init__(self, port: int = 9222, host: str = "127.0.0.1") -> None:
        self.port = int(os.environ.get("LUCY_CDP_PORT", port))
        self.host = host
        self._ws: _AsyncWebSocketClient | None = None
        self._target_id: str | None = None
        self._msg_id = 0
        self._pending_responses: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._mock_mode = False
        self._mock_dom: list[dict[str, Any]] = []
        self._mock_url = "https://example.com"

    @property
    def is_connected(self) -> bool:
        return self._mock_mode or (self._ws is not None and self._ws.is_connected)

    def set_mock_mode(self, enabled: bool = True, mock_dom: list[dict[str, Any]] | None = None) -> None:
        """Enable simulated CDP execution for headless testing and environments without Chrome."""
        self._mock_mode = enabled
        if mock_dom:
            self._mock_dom = mock_dom

    async def is_cdp_available(self) -> bool:
        """Check if Chrome DevTools Protocol HTTP endpoint is responding."""
        if self._mock_mode:
            return True
        url = f"http://{self.host}:{self.port}/json/version"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LucyCode-CDP"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def auto_launch_chrome(self, headless: bool = False, url: str | None = None) -> bool:
        """Launch Chrome with remote debugging if not already listening."""
        if await self.is_cdp_available():
            return True

        chrome_candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
        chosen_binary = None
        for p in chrome_candidates:
            if os.path.exists(p):
                chosen_binary = p
                break

        if not chosen_binary and sys.platform != "darwin":
            import shutil
            chosen_binary = (
                shutil.which("google-chrome")
                or shutil.which("chromium")
                or shutil.which("brave")
            )

        if not chosen_binary:
            logger.debug("No Chromium binary found for auto-launch")
            return False

        profile_dir = os.path.expanduser("~/.lucycode/cdp_chrome_profile")
        os.makedirs(profile_dir, exist_ok=True)

        args = [
            chosen_binary,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={profile_dir}",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if headless:
            args.append("--headless=new")
        if url:
            args.append(url)

        try:
            self._proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            # Wait up to 5s for the CDP port to open
            for _ in range(25):
                await asyncio.sleep(0.2)
                if await self.is_cdp_available():
                    return True
        except Exception as e:
            logger.debug("Failed to auto-launch Chrome: %s", e)

        return False

    async def connect(self, auto_launch: bool = True, url: str | None = None) -> bool:
        """Connect to active browser target via CDP WebSocket."""
        if self._mock_mode:
            return True

        if not await self.is_cdp_available():
            if auto_launch:
                launched = await self.auto_launch_chrome(url=url)
                if not launched:
                    return False
            else:
                return False

        # Query /json/list to find active page target
        targets_url = f"http://{self.host}:{self.port}/json/list"
        ws_url = None
        try:
            req = urllib.request.Request(targets_url, headers={"User-Agent": "LucyCode-CDP"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                targets = json.loads(resp.read().decode("utf-8"))
                for t in targets:
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        ws_url = t["webSocketDebuggerUrl"]
                        self._target_id = t.get("id")
                        break

            # If no existing page target, create one via /json/new
            if not ws_url:
                new_url = f"http://{self.host}:{self.port}/json/new"
                if url:
                    new_url += f"?{urllib.parse.quote(url)}"
                req_new = urllib.request.Request(new_url, method="PUT", headers={"User-Agent": "LucyCode-CDP"})
                with urllib.request.urlopen(req_new, timeout=2.0) as resp:
                    new_target = json.loads(resp.read().decode("utf-8"))
                    ws_url = new_target.get("webSocketDebuggerUrl")
                    self._target_id = new_target.get("id")

        except Exception as e:
            logger.debug("Error discovering CDP targets: %s", e)
            return False

        if not ws_url:
            return False

        # Connect WebSocket
        try:
            self._ws = _AsyncWebSocketClient(ws_url)
            await self._ws.connect()
            self._ws.start_listening(self._handle_ws_message)

            # Enable necessary domains
            await self.send("Page.enable")
            await self.send("DOM.enable")
            await self.send("Runtime.enable")
            return True
        except Exception as e:
            logger.debug("Failed connecting to CDP WebSocket %s: %s", ws_url, e)
            return False

    def _handle_ws_message(self, message: str) -> None:
        """Route incoming JSON-RPC response or event."""
        try:
            data = json.loads(message)
            msg_id = data.get("id")
            if msg_id is not None and msg_id in self._pending_responses:
                future = self._pending_responses.pop(msg_id)
                if not future.done():
                    future.set_result(data)
        except Exception as e:
            logger.debug("Error processing CDP response: %s", e)

    async def send(self, method: str, params: dict[str, Any] | None = None, timeout: float = 10.0) -> dict[str, Any]:
        """Send a JSON-RPC method call to CDP and await the result."""
        if self._mock_mode or not self._ws or not self._ws.is_connected:
            return self._handle_mock_call(method, params or {})

        self._msg_id += 1
        req_id = self._msg_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending_responses[req_id] = future

        request_payload = {
            "id": req_id,
            "method": method,
            "params": params or {},
        }
        await self._ws.send_text(json.dumps(request_payload))

        try:
            res = await asyncio.wait_for(future, timeout=timeout)
            if "error" in res:
                logger.debug("CDP Error (%s): %s", method, res["error"])
            return res
        except asyncio.TimeoutError:
            self._pending_responses.pop(req_id, None)
            raise TimeoutError(f"CDP call {method} timed out after {timeout}s")

    def _handle_mock_call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Simulate CDP responses when running in mock/offline mode."""
        if method == "Page.navigate":
            self._mock_url = params.get("url", self._mock_url)
            return {"result": {"frameId": "mock-frame-1", "loaderId": "mock-loader-1"}}
        if method == "Runtime.evaluate":
            expr = params.get("expression", "")
            if "querySelectorAll" in expr and "getBoundingClientRect" in expr:
                # Return mock button candidates if not populated
                if not self._mock_dom:
                    self._mock_dom = [
                        {
                            "tag": "button",
                            "id": "submit-btn",
                            "text": "Submit",
                            "role": "button",
                            "aria_label": "Submit form",
                            "selector": "#submit-btn",
                            "x": 200,
                            "y": 300,
                            "width": 120,
                            "height": 40,
                            "center_x": 260,
                            "center_y": 320,
                        },
                        {
                            "tag": "a",
                            "id": "login-link",
                            "text": "Sign In",
                            "role": "link",
                            "aria_label": "Sign in to account",
                            "selector": "#login-link",
                            "x": 800,
                            "y": 40,
                            "width": 80,
                            "height": 30,
                            "center_x": 840,
                            "center_y": 55,
                        },
                        {
                            "tag": "button",
                            "id": "play-btn",
                            "text": "Play Video",
                            "role": "button",
                            "aria_label": "Play",
                            "selector": "#play-btn",
                            "x": 400,
                            "y": 250,
                            "width": 90,
                            "height": 90,
                            "center_x": 445,
                            "center_y": 295,
                        },
                    ]
                return {"result": {"value": self._mock_dom}}
            if "window.location.href" in expr:
                return {"result": {"value": self._mock_url}}
            if "document.title" in expr:
                return {"result": {"value": "LucyCode Web Playground"}}
            return {"result": {"value": True}}

        if method == "Input.dispatchMouseEvent":
            return {"result": {}}

        if method == "Page.captureScreenshot":
            # Return 1x1 blank pixel base64 png
            blank_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
            return {"result": {"data": blank_png}}

        return {"result": {}}

    def _extract_eval_value(self, res: dict[str, Any]) -> Any:
        """Extract value from CDP Runtime.evaluate response."""
        if "result" in res:
            sub = res["result"]
            if isinstance(sub, dict) and "result" in sub and isinstance(sub["result"], dict) and "value" in sub["result"]:
                return sub["result"]["value"]
            if isinstance(sub, dict) and "value" in sub:
                return sub["value"]
        return None

    async def navigate(self, url: str) -> bool:
        """Navigate active page to URL."""
        if not self.is_connected:
            await self.connect(url=url)
        res = await self.send("Page.navigate", {"url": url})
        await asyncio.sleep(0.01 if self._mock_mode else 0.5)
        return "error" not in res

    async def get_current_url(self) -> str:
        """Query current browser URL."""
        res = await self.send("Runtime.evaluate", {"expression": "window.location.href"})
        return self._extract_eval_value(res) or ""

    async def get_page_title(self) -> str:
        """Query current page title."""
        res = await self.send("Runtime.evaluate", {"expression": "document.title"})
        return self._extract_eval_value(res) or ""

    async def find_clickable_elements(self, filter_text: str | None = None) -> list[CDPElement]:
        """Find all buttons, links, and interactive elements on the page via CDP DOM inspection."""
        if not self.is_connected:
            await self.connect()

        js_query = """
        (() => {
            const candidates = Array.from(document.querySelectorAll(
                'button, a, input[type="button"], input[type="submit"], input[type="reset"], [role="button"], [onclick], .btn'
            ));
            const results = [];
            for (let el of candidates) {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const isVisible = rect.width > 0 && rect.height > 0 &&
                                  style.visibility !== 'hidden' &&
                                  style.display !== 'none' &&
                                  style.opacity !== '0';
                if (!isVisible) continue;

                let text = (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || el.title || '').trim();
                text = text.replace(/\\s+/g, ' ').substring(0, 100);

                let selector = '';
                if (el.id) {
                    selector = '#' + el.id;
                } else if (el.name) {
                    selector = `${el.tagName.toLowerCase()}[name="${el.name}"]`;
                } else if (el.className && typeof el.className === 'string') {
                    const firstClass = el.className.trim().split(/\\s+/)[0];
                    if (firstClass && !firstClass.includes(':')) {
                        selector = `${el.tagName.toLowerCase()}.${firstClass}`;
                    }
                }
                if (!selector) {
                    selector = el.tagName.toLowerCase();
                }

                results.push({
                    tag: el.tagName.toLowerCase(),
                    id: el.id || '',
                    text: text,
                    role: el.getAttribute('role') || el.tagName.toLowerCase(),
                    aria_label: el.getAttribute('aria-label') || '',
                    selector: selector,
                    x: Math.round(rect.left),
                    y: Math.round(rect.top),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                    center_x: Math.round(rect.left + rect.width / 2),
                    center_y: Math.round(rect.top + rect.height / 2),
                    visible: true
                });
            }
            return results;
        })()
        """
        res = await self.send("Runtime.evaluate", {"expression": js_query, "returnByValue": True})
        raw_items = self._extract_eval_value(res) or []

        elements: list[CDPElement] = []
        filter_lower = filter_text.lower().strip() if filter_text else None

        for item in raw_items:
            elem = CDPElement(
                tag=item.get("tag", "button"),
                id=item.get("id", ""),
                text=item.get("text", ""),
                role=item.get("role", "button"),
                aria_label=item.get("aria_label", ""),
                selector=item.get("selector", ""),
                x=item.get("x", 0),
                y=item.get("y", 0),
                width=item.get("width", 0),
                height=item.get("height", 0),
                center_x=item.get("center_x", 0),
                center_y=item.get("center_y", 0),
                visible=item.get("visible", True),
            )
            if filter_lower:
                match = (
                    filter_lower in elem.text.lower()
                    or filter_lower in elem.aria_label.lower()
                    or filter_lower in elem.id.lower()
                    or filter_lower in elem.selector.lower()
                )
                if match:
                    elements.append(elem)
            else:
                elements.append(elem)

        return elements

    async def click_element(
        self,
        target: str | None = None,
        selector: str | None = None,
        coordinates: tuple[int, int] | None = None,
    ) -> CDPClickResult:
        """Find and click a button or element via Chrome DevTools Protocol."""
        if not self.is_connected:
            await self.connect()

        initial_url = await self.get_current_url()

        # Direct coordinate click if provided
        if coordinates:
            cx, cy = coordinates
            await self._dispatch_cdp_click(cx, cy)
            await asyncio.sleep(0.01 if self._mock_mode else 0.4)
            final_url = await self.get_current_url()
            return CDPClickResult(
                success=True,
                element=None,
                click_coordinates=(cx, cy),
                navigation_occurred=(initial_url != final_url),
                initial_url=initial_url,
                final_url=final_url,
                output=f"Dispatched CDP click at coordinates ({cx}, {cy}).",
            )

        # Find candidate elements
        elements = await self.find_clickable_elements(filter_text=target)

        # Match element by selector or text
        chosen: CDPElement | None = None
        if selector:
            for el in elements:
                if el.selector.lower() == selector.lower() or el.id.lower() == selector.lstrip("#").lower():
                    chosen = el
                    break

        if not chosen and target:
            t_lower = target.lower().strip()
            # 1. Exact text match
            for el in elements:
                if el.text.lower() == t_lower:
                    chosen = el
                    break
            # 2. Substring text match
            if not chosen:
                for el in elements:
                    if t_lower in el.text.lower() or t_lower in el.aria_label.lower():
                        chosen = el
                        break
            # 3. ID match
            if not chosen:
                for el in elements:
                    if t_lower in el.id.lower() or t_lower in el.selector.lower():
                        chosen = el
                        break

        if not chosen:
            all_elements = await self.find_clickable_elements()
            if all_elements:
                candidates_str = ", ".join(f"'{e.text or e.id or e.selector}'" for e in all_elements[:6])
                return CDPClickResult(
                    success=False,
                    element=None,
                    click_coordinates=(0, 0),
                    navigation_occurred=False,
                    initial_url=initial_url,
                    final_url=initial_url,
                    output=f"Target '{target}' not found. Available buttons: {candidates_str}",
                    error=f"No matching button found for '{target}'",
                )
            return CDPClickResult(
                success=False,
                element=None,
                click_coordinates=(0, 0),
                navigation_occurred=False,
                initial_url=initial_url,
                final_url=initial_url,
                output="No interactive buttons or clickable elements found on current page.",
                error="No elements found",
            )

        # Scroll into view and click
        cx, cy = chosen.center_x, chosen.center_y

        # Dispatch CDP Input mouse events
        await self._dispatch_cdp_click(cx, cy)

        # Secondary JS click guarantee
        if chosen.id:
            js_click = f"document.getElementById({json.dumps(chosen.id)})?.click();"
            await self.send("Runtime.evaluate", {"expression": js_click})
        elif chosen.selector:
            js_click = f"document.querySelector({json.dumps(chosen.selector)})?.click();"
            await self.send("Runtime.evaluate", {"expression": js_click})

        # Wait for potential DOM reaction or navigation
        await asyncio.sleep(0.01 if self._mock_mode else 0.5)
        final_url = await self.get_current_url()
        nav_occurred = bool(initial_url and final_url and initial_url != final_url)

        label = chosen.text or chosen.aria_label or chosen.id or chosen.selector
        return CDPClickResult(
            success=True,
            element=chosen,
            click_coordinates=(cx, cy),
            navigation_occurred=nav_occurred,
            initial_url=initial_url,
            final_url=final_url,
            output=(
                f"Successfully clicked button '{label}' [tag: {chosen.tag}, selector: {chosen.selector}] "
                f"at coordinates ({cx}, {cy}) via CDP."
                + (f" Navigated to: {final_url}" if nav_occurred else "")
            ),
        )

    async def _dispatch_cdp_click(self, x: int, y: int) -> None:
        """Send Input.dispatchMouseEvent mousePressed and mouseReleased to CDP."""
        await self.send(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
        )
        await asyncio.sleep(0.001 if self._mock_mode else 0.05)
        await self.send(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
        )

    async def capture_screenshot(self) -> str:
        """Capture page screenshot and return base64 encoded PNG."""
        if not self.is_connected:
            await self.connect()
        res = await self.send("Page.captureScreenshot", {"format": "png"})
        return res.get("result", {}).get("data", "")

    async def close(self) -> None:
        """Close WebSocket session."""
        if self._ws:
            await self._ws.close()
            self._ws = None


_global_cdp_client: CDPClient | None = None


def get_cdp_client(port: int = 9222) -> CDPClient:
    """Retrieve or initialize singleton CDPClient instance."""
    global _global_cdp_client
    if _global_cdp_client is None:
        _global_cdp_client = CDPClient(port=port)
    return _global_cdp_client
