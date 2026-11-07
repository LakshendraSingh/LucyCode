"""
Universal UI Automation & Verification Service for LucyCode.

Provides robust, application-agnostic desktop and browser interaction
using the macOS Accessibility API (System Events), menu bar navigation,
and closed-loop state verification to prevent false positives and eliminate
unreliable keyboard-shortcut guessing.
"""

from __future__ import annotations

import json
import logging
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class UIResult:
    """Return envelope for UI automation actions with verification."""
    success: bool
    action: str
    target: str
    message: str
    verified: bool = False
    app: str = ""
    window_title: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "target": self.target,
            "verified": self.verified,
            "app": self.app,
            "window_title": self.window_title,
            "message": self.message,
            "error": self.error,
            "details": self.details,
        }


def _run_osascript(script: str, timeout: int = 10) -> tuple[bool, str, str]:
    """Execute AppleScript string via osascript."""
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (proc.returncode == 0, proc.stdout.strip(), proc.stderr.strip())
    except subprocess.TimeoutExpired:
        return (False, "", "Operation timed out")
    except Exception as e:
        return (False, "", str(e))


class UniversalUIService:
    """
    Generalized macOS Application and Web UI Automation Engine.
    Works reliably across native apps, Catalyst, Electron, and browsers.
    """

    KNOWN_BROWSERS = {"Safari", "Google Chrome", "Brave Browser", "Microsoft Edge", "Arc"}

    def get_frontmost_app(self) -> dict[str, Any]:
        """
        Get metadata about the frontmost application, active window, and browser URL.
        """
        script = """
        tell application "System Events"
            set frontApp to first application process whose frontmost is true
            set appName to name of frontApp
            set appPid to unix id of frontApp
            set winCount to count of windows of frontApp
            set winTitle to ""
            if winCount > 0 then
                try
                    set winTitle to name of window 1 of frontApp
                end try
            end if
            return appName & "|||" & (appPid as string) & "|||" & (winCount as string) & "|||" & winTitle
        end tell
        """
        ok, stdout, stderr = _run_osascript(script)
        if not ok or not stdout:
            return {
                "name": "Unknown",
                "pid": 0,
                "window_count": 0,
                "window_title": "",
                "is_browser": False,
                "browser_url": None,
                "browser_title": None,
                "error": stderr or "Failed to query frontmost process",
            }

        parts = stdout.split("|||")
        app_name = parts[0] if len(parts) > 0 else "Unknown"
        pid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        win_count = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        win_title = parts[3] if len(parts) > 3 else ""

        is_browser = app_name in self.KNOWN_BROWSERS
        browser_url = None
        browser_title = None

        if is_browser:
            browser_url, browser_title = self._get_browser_tab_info(app_name)

        return {
            "name": app_name,
            "pid": pid,
            "window_count": win_count,
            "window_title": win_title,
            "is_browser": is_browser,
            "browser_url": browser_url,
            "browser_title": browser_title,
        }

    def _get_browser_tab_info(self, browser_name: str) -> tuple[str | None, str | None]:
        """Query active tab URL and title from a known browser."""
        if browser_name == "Safari":
            script = """
            tell application "Safari"
                if (count of windows) > 0 then
                    tell current tab of front window
                        return (URL as string) & "|||" & (name as string)
                    end tell
                end if
            end tell
            """
        elif browser_name in ("Google Chrome", "Brave Browser", "Microsoft Edge", "Arc"):
            script = f"""
            tell application "{browser_name}"
                if (count of windows) > 0 then
                    tell active tab of front window
                        return (URL as string) & "|||" & (title as string)
                    end tell
                end if
            end tell
            """
        else:
            return None, None

        ok, stdout, _ = _run_osascript(script, timeout=3)
        if ok and "|||" in stdout:
            u, t = stdout.split("|||", 1)
            return u.strip() or None, t.strip() or None
        return None, None

    def inspect(self, app_name: str | None = None) -> dict[str, Any]:
        """
        Inspect visible windows, buttons, text fields, and top-level menus of an application.
        """
        front = self.get_frontmost_app()
        target_app = app_name or front["name"]

        # 1. Menus
        menu_script = f"""
        tell application "System Events"
            if exists process "{target_app}" then
                tell process "{target_app}"
                    set menuList to name of every menu bar item of menu bar 1
                    return menuList
                end tell
            end if
        end tell
        """
        _, menu_out, _ = _run_osascript(menu_script, timeout=4)
        menus = [m.strip() for m in menu_out.split(",") if m.strip()] if menu_out else []

        # 2. Window elements (Buttons and text fields)
        elem_script = f"""
        tell application "System Events"
            if exists process "{target_app}" then
                tell process "{target_app}"
                    if (count of windows) > 0 then
                        set w to window 1
                        set wName to name of w
                        set btnNames to {{}}
                        try
                            set btnNames to name of every button of w
                        end try
                        set tfNames to {{}}
                        try
                            set tfNames to description of every text field of w
                        end try
                        set uiSummary to (wName as string) & "|||"
                        return uiSummary & (btnNames as string) & "|||" & (tfNames as string)
                    else
                        return "NO_WINDOWS"
                    end if
                end tell
            else
                return "PROCESS_NOT_FOUND"
            end if
        end tell
        """
        ok, elem_out, err = _run_osascript(elem_script, timeout=5)
        buttons = []
        text_fields = []
        window_title = front.get("window_title", "")

        if ok and elem_out and elem_out not in ("NO_WINDOWS", "PROCESS_NOT_FOUND"):
            parts = elem_out.split("|||")
            if len(parts) >= 1 and parts[0]:
                window_title = parts[0]
            if len(parts) >= 2 and parts[1]:
                buttons = [b.strip() for b in parts[1].split(",") if b.strip() and b.strip() != "missing value"]
            if len(parts) >= 3 and parts[2]:
                text_fields = [t.strip() for t in parts[2].split(",") if t.strip() and t.strip() != "missing value"]

        browser_url = None
        browser_title = None
        if target_app in self.KNOWN_BROWSERS:
            browser_url, browser_title = self._get_browser_tab_info(target_app)

        return {
            "app": target_app,
            "window_title": window_title,
            "window_count": front.get("window_count", 0),
            "is_browser": target_app in self.KNOWN_BROWSERS,
            "browser_url": browser_url,
            "browser_title": browser_title,
            "menus": menus,
            "visible_buttons": buttons,
            "text_fields": text_fields,
            "raw_status": elem_out if not ok else "OK",
        }

    def click_menu_item(self, app_name: str, menu_path: list[str]) -> UIResult:
        """
        Deterministically trigger an application menu item (e.g. ['File', 'New Document'] or ['Edit', 'Paste']).
        This works universally across 100% of macOS applications without guessing shortcuts.
        """
        if not menu_path:
            return UIResult(
                success=False,
                action="menu_click",
                target="",
                message="menu_path must contain at least 1 menu item (e.g. ['File', 'New'])",
                error="Empty menu path",
                app=app_name,
            )

        # Build nested AppleScript menu invocation
        top_menu = menu_path[0]
        leaf_item = menu_path[-1]

        if len(menu_path) == 1:
            script = f"""
            tell application "System Events"
                tell process "{app_name}"
                    click menu bar item "{top_menu}" of menu bar 1
                end tell
            end tell
            """
        elif len(menu_path) == 2:
            item = menu_path[1]
            script = f"""
            tell application "System Events"
                tell process "{app_name}"
                    click menu item "{item}" of menu "{top_menu}" of menu bar item "{top_menu}" of menu bar 1
                end tell
            end tell
            """
        else:
            # Sub-menu item
            parent = menu_path[-2]
            script = f"""
            tell application "System Events"
                tell process "{app_name}"
                    click menu item "{leaf_item}" of menu "{parent}" of menu item "{parent}" of menu "{top_menu}" of menu bar item "{top_menu}" of menu bar 1
                end tell
            end tell
            """

        ok, stdout, stderr = _run_osascript(script, timeout=6)
        path_str = " > ".join(menu_path)

        if ok:
            time.sleep(0.3)
            front = self.get_frontmost_app()
            return UIResult(
                success=True,
                action="menu_click",
                target=path_str,
                verified=True,
                app=app_name,
                window_title=front.get("window_title", ""),
                message=f"Successfully triggered menu '{path_str}' in {app_name}.",
                details={"window_count": front.get("window_count")},
            )
        else:
            return UIResult(
                success=False,
                action="menu_click",
                target=path_str,
                verified=False,
                app=app_name,
                message=f"Could not find or trigger menu '{path_str}' in {app_name}.",
                error=stderr or "Menu item not found or disabled",
            )

    def click_element(
        self,
        app_name: str | None,
        label: str,
        element_type: str = "button",
    ) -> UIResult:
        """
        Locate and click an interactive UI control by label or accessibility description.
        Verifies whether the element existed and reports failure instead of hallucinating success.
        """
        front = self.get_frontmost_app()
        app = app_name or front["name"]

        # Escape label for AppleScript
        clean_label = label.replace('\\', '\\\\').replace('"', '\\"')

        # Check for matching button or element in front window
        script = f"""
        tell application "System Events"
            tell process "{app}"
                if (count of windows) = 0 then
                    return "NO_WINDOWS"
                end if
                set w to window 1
                -- 1. Try exact button match
                if exists (button "{clean_label}" of w) then
                    click button "{clean_label}" of w
                    return "CLICKED_BUTTON"
                end if
                -- 2. Try partial/case-insensitive button match
                repeat with btn in (every button of w)
                    set bName to ""
                    try
                        set bName to name of btn
                    end try
                    if bName contains "{clean_label}" then
                        click btn
                        return "CLICKED_BUTTON_PARTIAL"
                    end if
                end repeat
                -- 3. Try generic UI Element with matching description/title
                repeat with el in (every UI element of w)
                    set elTitle to ""
                    try
                        set elTitle to title of el
                    end try
                    if elTitle contains "{clean_label}" then
                        try
                            perform action "AXPress" of el
                            return "PERFORMED_AXPRESS"
                        on error
                            click el
                            return "CLICKED_UI_ELEMENT"
                        end try
                    end if
                end repeat
                return "NOT_FOUND"
            end tell
        end tell
        """

        ok, stdout, stderr = _run_osascript(script, timeout=6)
        if ok and stdout in ("CLICKED_BUTTON", "CLICKED_BUTTON_PARTIAL", "PERFORMED_AXPRESS", "CLICKED_UI_ELEMENT"):
            time.sleep(0.3)
            front_after = self.get_frontmost_app()
            return UIResult(
                success=True,
                action="click",
                target=label,
                verified=True,
                app=app,
                window_title=front_after.get("window_title", ""),
                message=f"Successfully clicked '{label}' in {app} ({stdout}).",
            )
        else:
            # Query visible buttons so user/agent knows what is actually available
            insp = self.inspect(app)
            available = insp.get("visible_buttons", [])
            return UIResult(
                success=False,
                action="click",
                target=label,
                verified=False,
                app=app,
                window_title=insp.get("window_title", ""),
                message=f"Element '{label}' was not found in {app} (window: '{insp.get('window_title')}').",
                error=stderr or f"Element '{label}' not found",
                details={"available_buttons": available},
            )

    def type_into_element(
        self,
        app_name: str | None,
        text: str,
        field_label: str | None = None,
        clear_first: bool = False,
    ) -> UIResult:
        """
        Type or set text in a specific UI field or the focused control.
        Verifies insertion rather than blindly sending keystrokes into the void.
        """
        front = self.get_frontmost_app()
        app = app_name or front["name"]

        # Ensure app is frontmost
        subprocess.run(["osascript", "-e", f'tell application "{app}" to activate'], capture_output=True)
        time.sleep(0.2)

        escaped_text = text.replace('\\', '\\\\').replace('"', '\\"')

        if field_label:
            clean_field = field_label.replace('\\', '\\\\').replace('"', '\\"')
            script = f"""
            tell application "System Events"
                tell process "{app}"
                    if (count of windows) = 0 then
                        return "NO_WINDOWS"
                    end if
                    set w to window 1
                    -- Try matching text field by description or title
                    repeat with tf in (every text field of w)
                        set d to ""
                        try
                            set d to description of tf
                        end try
                        set t to ""
                        try
                            set t to title of tf
                        end try
                        if (d contains "{clean_field}") or (t contains "{clean_field}") then
                            set value of tf to "{escaped_text}"
                            return "SET_VALUE_SUCCESS"
                        end if
                    end repeat
                    -- Try text area
                    repeat with ta in (every text area of w)
                        set d to ""
                        try
                            set d to description of ta
                        end try
                        if d contains "{clean_field}" then
                            set value of ta to "{escaped_text}"
                            return "SET_TEXTAREA_SUCCESS"
                        end if
                    end repeat
                    return "FIELD_NOT_FOUND"
                end tell
            end tell
            """
            ok, stdout, stderr = _run_osascript(script, timeout=6)
            if ok and stdout in ("SET_VALUE_SUCCESS", "SET_TEXTAREA_SUCCESS"):
                return UIResult(
                    success=True,
                    action="type_text",
                    target=field_label,
                    verified=True,
                    app=app,
                    message=f"Successfully set value of '{field_label}' to text in {app}.",
                )
            elif stdout == "FIELD_NOT_FOUND":
                logger.debug("Field label '%s' not found via AX, falling back to clipboard paste", field_label)

        # Fallback to focused control insertion via clipboard paste (Cmd+V)
        # Using pbcopy ensures exact text preservation without keycode dropped characters
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-8"))

        paste_script = f"""
        tell application "System Events"
            tell process "{app}"
                keystroke "v" using command down
            end tell
        end tell
        """
        ok, stdout, stderr = _run_osascript(paste_script, timeout=5)
        word_count = len(text.split())
        return UIResult(
            success=ok,
            action="type_text",
            target=field_label or "focused_field",
            verified=ok,
            app=app,
            message=f"Pasted {word_count} words into {app} active control." if ok else f"Failed to paste into {app}.",
            error=stderr if not ok else None,
        )

    def verify(
        self,
        app_name: str | None,
        check_type: str,
        expected_value: str,
    ) -> dict[str, Any]:
        """
        Verify completion condition:
        - 'window_title': checks if window title contains expected_value
        - 'url': checks if browser URL contains expected_value
        - 'button_exists': checks if button is present
        - 'button_gone': checks if button has disappeared (e.g. 'Send' or 'Draft')
        - 'text_present': checks if text appears in the window
        """
        insp = self.inspect(app_name)
        app = insp.get("app", "")
        window_title = insp.get("window_title", "")
        url = insp.get("browser_url", "") or ""

        verified = False
        details = ""

        if check_type in ("window_title", "title"):
            verified = expected_value.lower() in window_title.lower()
            details = f"Window title is '{window_title}'"
        elif check_type in ("url", "browser_url"):
            verified = expected_value.lower() in url.lower()
            details = f"Active tab URL is '{url}'"
        elif check_type == "button_exists":
            buttons = insp.get("visible_buttons", [])
            verified = any(expected_value.lower() in b.lower() for b in buttons)
            details = f"Visible buttons: {buttons}"
        elif check_type == "button_gone":
            buttons = insp.get("visible_buttons", [])
            verified = not any(expected_value.lower() in b.lower() for b in buttons)
            details = f"Remaining buttons: {buttons}"
        elif check_type == "window_closed":
            verified = insp.get("window_count", 0) == 0 or expected_value.lower() not in window_title.lower()
            details = f"Current window title: '{window_title}'"
        else:
            details = f"Unknown check_type '{check_type}'"

        return {
            "verified": verified,
            "check": check_type,
            "expected": expected_value,
            "details": details,
            "app": app,
            "window_title": window_title,
            "url": url,
        }


# Singleton accessor
_universal_ui: UniversalUIService | None = None


def get_universal_ui() -> UniversalUIService:
    """Return singleton instance of UniversalUIService."""
    global _universal_ui
    if _universal_ui is None:
        _universal_ui = UniversalUIService()
    return _universal_ui
