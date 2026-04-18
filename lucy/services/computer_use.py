"""
Computer Use service (cross-platform desktop automation).
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

from pynput.keyboard import Controller as KeyboardController, Key
from pynput.mouse import Controller as MouseController, Button

logger = logging.getLogger(__name__)


class ComputerUseService:
    """Service to handle mouse, keyboard, and screen capture across platforms."""

    def __init__(self):
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        self._key_map = {
            "enter": Key.enter, "Return": Key.enter,
            "space": Key.space, "tab": Key.tab,
            "backspace": Key.backspace, "esc": Key.esc,
            "Escape": Key.esc,
            "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
            "shift": Key.shift, "ctrl": Key.ctrl, "alt": Key.alt, "cmd": Key.cmd,
            "page_up": Key.page_up, "page_down": Key.page_down,
        }

    def type_text(self, text: str) -> None:
        """Type a string of text."""
        self.keyboard.type(text)

    def press_key(self, key_name: str) -> None:
        """Press a specific key."""
        key = self._key_map.get(key_name)
        if key:
            self.keyboard.press(key)
            self.keyboard.release(key)
        else:
            # Assume it's a character
            self.keyboard.press(key_name)
            self.keyboard.release(key_name)

    def mouse_move(self, x: int, y: int) -> None:
        """Move mouse to absolute coordinates."""
        self.mouse.position = (x, y)

    def mouse_click(self, button: str = "left", clicks: int = 1) -> None:
        """Click the mouse."""
        btn = Button.right if button == "right" else Button.left
        self.mouse.click(btn, clicks)

    def mouse_drag(self, x: int, y: int) -> None:
        """Drag mouse to absolute coordinates."""
        self.mouse.press(Button.left)
        self.mouse.position = (x, y)
        self.mouse.release(Button.left)

    def take_screenshot(self) -> str:
        """Take a screenshot and return base64 encoded PNG."""
        import mss
        from PIL import Image
        
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # primary monitor
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode("utf-8")


_service: ComputerUseService | None = None

def get_computer_use_service() -> ComputerUseService:
    global _service
    if _service is None:
        _service = ComputerUseService()
    return _service
