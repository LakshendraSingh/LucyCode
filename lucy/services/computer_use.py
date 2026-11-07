"""
Enhanced Computer Use service — zero-dependency workstation automation core.

Provides low-level mouse, keyboard, and screenshot control.
Requires pynput for input control and mss/PIL for screen capture.
Gracefully degrades when dependencies are not installed.
"""

from __future__ import annotations

import base64
import io
import logging
import subprocess
import tempfile
import os
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency resolution
# ---------------------------------------------------------------------------

try:
    from pynput.keyboard import Controller as KeyboardController, Key
    from pynput.mouse import Controller as MouseController, Button as MouseButton
    _HAS_PYNPUT = True
except ImportError:
    _HAS_PYNPUT = False
    logger.debug("pynput not installed — keyboard/mouse control unavailable. Install with: pip install pynput")

try:
    import mss
    import mss.tools
    _HAS_MSS = True
except ImportError:
    _HAS_MSS = False
    logger.debug("mss not installed — using subprocess screenshot fallback. Install with: pip install mss")

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


class ComputerUseService:
    """
    Low-level desktop automation: mouse, keyboard, screenshots.
    Integrates with the higher-level screen_automation and app_automation services.
    """

    # Modifier key ordering for shortcut parsing
    _MODIFIER_ORDER = ["ctrl", "alt", "shift", "cmd", "command", "super", "fn"]

    def __init__(self) -> None:
        if _HAS_PYNPUT:
            self._mouse = MouseController()
            self._keyboard = KeyboardController()
        else:
            self._mouse = None
            self._keyboard = None

        self._key_map: dict[str, Any] = {}
        if _HAS_PYNPUT:
            self._key_map = {
                "enter": Key.enter, "return": Key.enter,
                "space": Key.space, "tab": Key.tab,
                "backspace": Key.backspace, "delete": Key.delete,
                "esc": Key.esc, "escape": Key.esc,
                "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
                "home": Key.home, "end": Key.end,
                "page_up": Key.page_up, "page_down": Key.page_down,
                "shift": Key.shift, "ctrl": Key.ctrl, "control": Key.ctrl,
                "alt": Key.alt, "option": Key.alt,
                "cmd": Key.cmd, "command": Key.cmd, "super": Key.cmd,
                "f1": Key.f1, "f2": Key.f2, "f3": Key.f3, "f4": Key.f4,
                "f5": Key.f5, "f6": Key.f6, "f7": Key.f7, "f8": Key.f8,
                "f9": Key.f9, "f10": Key.f10, "f11": Key.f11, "f12": Key.f12,
            }

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def type_text(self, text: str) -> None:
        """Type a string of text character by character."""
        if not _HAS_PYNPUT or self._keyboard is None:
            raise RuntimeError("pynput not installed. Run: pip install pynput")
        self._keyboard.type(text)

    def press_key(self, key_name: str) -> None:
        """Press and release a single key by name."""
        if not _HAS_PYNPUT or self._keyboard is None:
            raise RuntimeError("pynput not installed. Run: pip install pynput")
        key = self._key_map.get(key_name.lower())
        if key is not None:
            self._keyboard.press(key)
            self._keyboard.release(key)
        elif len(key_name) == 1:
            self._keyboard.press(key_name)
            self._keyboard.release(key_name)
        else:
            raise ValueError(f"Unknown key: {key_name!r}")

    def hotkey(self, *keys: str) -> None:
        """Press a combination of keys simultaneously. E.g. hotkey('cmd', 's')."""
        if not _HAS_PYNPUT or self._keyboard is None:
            raise RuntimeError("pynput not installed. Run: pip install pynput")
        resolved = [self._key_map.get(k.lower(), k) for k in keys]
        for key in resolved:
            self._keyboard.press(key)
        for key in reversed(resolved):
            self._keyboard.release(key)

    def shortcut(self, shortcut_str: str) -> None:
        """
        Parse and press a shortcut string like 'cmd+s', 'cmd+shift+t', 'ctrl+c'.
        """
        parts = [p.strip().lower() for p in shortcut_str.replace("-", "+").split("+")]
        self.hotkey(*parts)

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------

    def get_mouse_position(self) -> tuple[int, int]:
        """Return the current mouse position as (x, y)."""
        if not _HAS_PYNPUT or self._mouse is None:
            raise RuntimeError("pynput not installed. Run: pip install pynput")
        pos = self._mouse.position
        return (int(pos[0]), int(pos[1]))

    def mouse_move(self, x: int, y: int) -> None:
        """Move mouse to absolute screen coordinates."""
        if not _HAS_PYNPUT or self._mouse is None:
            raise RuntimeError("pynput not installed. Run: pip install pynput")
        self._mouse.position = (x, y)

    def mouse_move_relative(self, dx: int, dy: int) -> None:
        """Move mouse relative to current position."""
        if not _HAS_PYNPUT or self._mouse is None:
            raise RuntimeError("pynput not installed. Run: pip install pynput")
        x, y = self.get_mouse_position()
        self._mouse.position = (x + dx, y + dy)

    def mouse_click(self, button: str = "left", clicks: int = 1) -> None:
        """Click the mouse at current position."""
        if not _HAS_PYNPUT or self._mouse is None:
            raise RuntimeError("pynput not installed. Run: pip install pynput")
        btn_map = {
            "left": MouseButton.left,
            "right": MouseButton.right,
            "middle": MouseButton.middle,
        }
        btn = btn_map.get(button, MouseButton.left)
        self._mouse.click(btn, clicks)

    def mouse_click_at(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        """Move to coordinates then click."""
        self.mouse_move(x, y)
        self.mouse_click(button, clicks)

    def mouse_drag(self, x: int, y: int) -> None:
        """Hold left button and drag to absolute coordinates."""
        if not _HAS_PYNPUT or self._mouse is None:
            raise RuntimeError("pynput not installed. Run: pip install pynput")
        self._mouse.press(MouseButton.left)
        self._mouse.position = (x, y)
        self._mouse.release(MouseButton.left)

    def mouse_drag_from_to(
        self, x1: int, y1: int, x2: int, y2: int
    ) -> None:
        """Move to (x1,y1) and drag to (x2,y2)."""
        self.mouse_move(x1, y1)
        self.mouse_drag(x2, y2)

    def mouse_scroll(self, dx: int = 0, dy: int = -3) -> None:
        """Scroll the mouse wheel. dy < 0 scrolls down."""
        if not _HAS_PYNPUT or self._mouse is None:
            raise RuntimeError("pynput not installed. Run: pip install pynput")
        self._mouse.scroll(dx, dy)

    # ------------------------------------------------------------------
    # Screen capture
    # ------------------------------------------------------------------

    def take_screenshot(
        self,
        monitor: int = 0,
        region: dict[str, int] | None = None,
    ) -> str:
        """
        Take a screenshot and return base64-encoded PNG string.

        Args:
            monitor: Monitor index. 0 = all monitors combined, 1 = primary.
            region: Optional dict with keys x, y, width, height for a crop.

        Returns:
            Base64-encoded PNG string.
        """
        if _HAS_MSS:
            return self._screenshot_mss(monitor, region)
        else:
            return self._screenshot_subprocess(region)

    def _screenshot_mss(self, monitor: int, region: dict[str, int] | None) -> str:
        with mss.mss() as sct:
            if region:
                grab_region = {
                    "top": region["y"],
                    "left": region["x"],
                    "width": region["width"],
                    "height": region["height"],
                }
            else:
                grab_region = sct.monitors[monitor] if monitor < len(sct.monitors) else sct.monitors[0]

            sct_img = sct.grab(grab_region)
            buf = io.BytesIO()
            if _HAS_PIL:
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                if region:
                    img = img.crop((0, 0, region["width"], region["height"]))
                img.save(buf, format="PNG")
            else:
                # Save raw mss screenshot
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=buf)
            return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _screenshot_subprocess(self, region: dict[str, int] | None) -> str:
        """Fallback screenshot using macOS screencapture."""
        path = "/tmp/lucy_screenshot_fallback.png"
        cmd = ["screencapture", "-x", path]
        if region:
            cmd = [
                "screencapture", "-x",
                "-R",
                f"{region['x']},{region['y']},{region['width']},{region['height']}",
                path,
            ]
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        if result.returncode != 0:
            raise RuntimeError(f"screencapture failed: {result.stderr.decode()}")
        with open(path, "rb") as f:
            data = f.read()
        try:
            os.unlink(path)
        except OSError:
            pass
        return base64.b64encode(data).decode("utf-8")

    def save_screenshot(
        self,
        path: str,
        monitor: int = 0,
        region: dict[str, int] | None = None,
    ) -> str:
        """Take screenshot and save to a file. Returns the saved path."""
        b64 = self.take_screenshot(monitor=monitor, region=region)
        data = base64.b64decode(b64)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def get_screen_dimensions(self) -> tuple[int, int]:
        """Return (width, height) of the primary display."""
        if _HAS_MSS:
            with mss.mss() as sct:
                m = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                return m["width"], m["height"]
        # Fallback: parse system_profiler
        try:
            out = subprocess.check_output(
                ["system_profiler", "SPDisplaysDataType"], text=True, timeout=10
            )
            for line in out.splitlines():
                if "Resolution" in line and "x" in line:
                    parts = line.split(":")[-1].strip().split("x")
                    if len(parts) >= 2:
                        w = int(parts[0].strip().split()[0])
                        h = int(parts[1].strip().split()[0])
                        return w, h
        except Exception:
            pass
        return 1920, 1080  # Safe default

    def get_pixel_color(self, x: int, y: int) -> tuple[int, int, int]:
        """Return the RGB color of a pixel at (x, y)."""
        if _HAS_MSS and _HAS_PIL:
            with mss.mss() as sct:
                region = {"top": y, "left": x, "width": 1, "height": 1}
                sct_img = sct.grab(region)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                return img.getpixel((0, 0))[:3]
        # Fallback: screenshot + crop
        b64 = self._screenshot_subprocess(region={"x": x, "y": y, "width": 1, "height": 1})
        if _HAS_PIL:
            data = base64.b64decode(b64)
            img = Image.open(io.BytesIO(data))
            px = img.getpixel((0, 0))
            return px[0], px[1], px[2]
        return (0, 0, 0)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: ComputerUseService | None = None


def get_computer_use_service() -> ComputerUseService:
    """Return the global ComputerUseService singleton."""
    global _service
    if _service is None:
        _service = ComputerUseService()
    return _service
