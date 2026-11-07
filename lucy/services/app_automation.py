"""
lucy/services/app_automation.py

macOS application automation service for LucyCode.

Provides programmatic control over macOS applications, windows, clipboard,
notifications, keyboard shortcuts, text-to-speech, and arbitrary AppleScript
execution — all using only the Python standard library (subprocess, shlex, etc.).
"""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data-classes
# ---------------------------------------------------------------------------


@dataclass
class AppInfo:
    """Metadata about a running macOS application."""

    name: str
    bundle_id: str
    pid: int
    is_running: bool
    windows: list[str] = field(default_factory=list)


@dataclass
class WindowInfo:
    """Metadata about a single application window."""

    title: str
    app: str
    x: int
    y: int
    width: int
    height: int
    is_focused: bool


@dataclass
class ClipboardContent:
    """Contents of the system clipboard."""

    text: Optional[str]
    files: list[str] = field(default_factory=list)
    html: Optional[str] = None


@dataclass
class NotificationResult:
    """Result of a macOS notification request."""

    sent: bool
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper: run a subprocess
# ---------------------------------------------------------------------------


def _run(
    args: list[str],
    input_text: Optional[str] = None,
    timeout: int = 15,
) -> tuple[int, str, str]:
    """
    Execute *args* as a subprocess.

    Parameters
    ----------
    args:
        Command and its arguments.
    input_text:
        Optional text piped to the process's stdin.
    timeout:
        Seconds to wait before raising ``subprocess.TimeoutExpired``.

    Returns
    -------
    tuple[int, str, str]
        ``(returncode, stdout, stderr)``
    """
    try:
        result = subprocess.run(
            args,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out"
    except FileNotFoundError as exc:
        return 1, "", str(exc)


def _osascript(script: str, timeout: int = 15) -> tuple[bool, str]:
    """
    Execute *script* as AppleScript via ``osascript``.

    Parameters
    ----------
    script:
        Multi-line AppleScript source.
    timeout:
        Maximum execution time in seconds.

    Returns
    -------
    tuple[bool, str]
        ``(success, output_or_error)``
    """
    rc, out, err = _run(["osascript", "-e", script], timeout=timeout)
    if rc == 0:
        return True, out
    return False, err or out


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AppAutomationService:
    """
    macOS application automation service.

    All public methods are safe to call repeatedly; they never raise
    exceptions — errors are captured and returned as ``False`` / ``None``
    / empty collections so callers can react without try/except boilerplate.
    """

    # ------------------------------------------------------------------
    # App lifecycle
    # ------------------------------------------------------------------

    def list_running_apps(self) -> list[AppInfo]:
        """
        Return every foreground (UI) application that is currently running.

        Uses AppleScript ``System Events`` to enumerate processes whose
        ``background only`` flag is ``false``, then cross-references ``ps``
        for PIDs.

        Returns
        -------
        list[AppInfo]
            One entry per visible application, sorted by name.
        """
        script = (
            'tell application "System Events"\n'
            "    set appList to every process whose background only is false\n"
            "    set output to {}\n"
            "    repeat with p in appList\n"
            "        set pName to name of p\n"
            "        set pPID  to unix id of p\n"
            "        set pBID  to bundle identifier of p\n"
            '        set end of output to pName & "|" & pPID & "|" & pBID\n'
            "    end repeat\n"
            '    return output as string\n'
            "end tell"
        )
        # AppleScript list → string returns items separated by ", "
        script_joined = (
            'tell application "System Events"\n'
            "    set appList to every process whose background only is false\n"
            "    set rows to {}\n"
            "    repeat with p in appList\n"
            "        set pName to name of p\n"
            "        set pPID  to (unix id of p) as string\n"
            "        try\n"
            "            set pBID to bundle identifier of p\n"
            "            if pBID is missing value then set pBID to \"\"\n"
            "        on error\n"
            '            set pBID to ""\n'
            "        end try\n"
            '        set end of rows to pName & "|" & pPID & "|" & pBID\n'
            "    end repeat\n"
            '    set AppleScript\'s text item delimiters to "\\n"\n'
            "    set result_str to rows as string\n"
            '    set AppleScript\'s text item delimiters to ""\n'
            "    return result_str\n"
            "end tell"
        )
        ok, output = _osascript(script_joined)
        apps: list[AppInfo] = []
        if not ok or not output:
            return apps

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 2:
                continue
            name = parts[0].strip()
            try:
                pid = int(parts[1].strip())
            except ValueError:
                pid = -1
            bundle_id = parts[2].strip() if len(parts) > 2 else ""
            apps.append(
                AppInfo(
                    name=name,
                    bundle_id=bundle_id,
                    pid=pid,
                    is_running=True,
                    windows=[],
                )
            )

        apps.sort(key=lambda a: a.name.lower())
        return apps

    def launch_app(self, name_or_path: str, args: list[str] | None = None) -> bool:
        """
        Launch an application by name or absolute path.

        Uses ``open -a <name>`` for named apps and direct execution for
        absolute paths. Any additional *args* are forwarded with ``--args``.

        Parameters
        ----------
        name_or_path:
            Application name (e.g. ``"Safari"``) or absolute ``/path/to/App.app``.
        args:
            Optional arguments forwarded to the application.

        Returns
        -------
        bool
            ``True`` if the application was launched successfully.
        """
        if args is None:
            args = []

        if name_or_path.startswith("/"):
            # Absolute path — open directly or via `open`
            cmd = ["open", name_or_path]
        else:
            cmd = ["open", "-a", name_or_path]

        if args:
            cmd += ["--args"] + args

        rc, _, _ = _run(cmd)
        return rc == 0

    def quit_app(self, name: str, force: bool = False) -> bool:
        """
        Quit an application gracefully or forcefully.

        Graceful quit uses ``osascript`` ``tell application … to quit``.
        Forced quit uses ``pkill -9``.

        Parameters
        ----------
        name:
            Application name as it appears in the menu bar / System Events.
        force:
            When ``True``, send SIGKILL via ``pkill`` instead of asking politely.

        Returns
        -------
        bool
            ``True`` if the quit command was accepted without error.
        """
        if force:
            rc, _, _ = _run(["pkill", "-9", "-x", name])
            return rc == 0

        script = f'tell application "{name}" to quit'
        ok, _ = _osascript(script)
        return ok

    def focus_app(self, name: str) -> bool:
        """
        Bring an application's windows to the foreground.

        Parameters
        ----------
        name:
            Application name (e.g. ``"Finder"``).

        Returns
        -------
        bool
            ``True`` if the activate command succeeded.
        """
        script = f'tell application "{name}" to activate'
        ok, _ = _osascript(script)
        return ok

    def get_frontmost_app(self) -> Optional[AppInfo]:
        """
        Return metadata about the application that currently has focus.

        Returns
        -------
        AppInfo | None
            The frontmost application, or ``None`` on failure.
        """
        script = (
            'tell application "System Events"\n'
            "    set fp to first process whose frontmost is true\n"
            "    set pName to name of fp\n"
            "    set pPID  to (unix id of fp) as string\n"
            "    try\n"
            "        set pBID to bundle identifier of fp\n"
            "        if pBID is missing value then set pBID to \"\"\n"
            "    on error\n"
            '        set pBID to ""\n'
            "    end try\n"
            '    return pName & "|" & pPID & "|" & pBID\n'
            "end tell"
        )
        ok, output = _osascript(script)
        if not ok or not output:
            return None

        parts = output.split("|")
        if len(parts) < 2:
            return None

        name = parts[0].strip()
        try:
            pid = int(parts[1].strip())
        except ValueError:
            pid = -1
        bundle_id = parts[2].strip() if len(parts) > 2 else ""

        return AppInfo(name=name, bundle_id=bundle_id, pid=pid, is_running=True)

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------

    def get_windows(self) -> list[WindowInfo]:
        """
        Return information about every visible window on screen.

        Uses AppleScript ``System Events`` to enumerate windows and their
        bounds (position + size).  The frontmost process's first window is
        flagged as focused.

        Returns
        -------
        list[WindowInfo]
            All windows across all foreground applications, in the order
            returned by System Events.
        """
        script = (
            'tell application "System Events"\n'
            "    set frontApp to name of first process whose frontmost is true\n"
            "    set rows to {}\n"
            "    set allProcesses to every process whose background only is false\n"
            "    repeat with proc in allProcesses\n"
            "        set procName to name of proc\n"
            "        set procWins to windows of proc\n"
            "        repeat with w in procWins\n"
            "            set wTitle to name of w\n"
            "            set wPos   to position of w\n"
            "            set wSize  to size of w\n"
            "            set wx to item 1 of wPos\n"
            "            set wy to item 2 of wPos\n"
            "            set ww to item 1 of wSize\n"
            "            set wh to item 2 of wSize\n"
            "            if procName is frontApp then\n"
            '                set focused to "1"\n'
            "            else\n"
            '                set focused to "0"\n'
            "            end if\n"
            "            set end of rows to "
            'wTitle & "|" & procName & "|" & (wx as string) & "|" & (wy as string)'
            ' & "|" & (ww as string) & "|" & (wh as string) & "|" & focused\n'
            "        end repeat\n"
            "    end repeat\n"
            '    set AppleScript\'s text item delimiters to "\\n"\n'
            "    set result_str to rows as string\n"
            '    set AppleScript\'s text item delimiters to ""\n'
            "    return result_str\n"
            "end tell"
        )
        ok, output = _osascript(script, timeout=30)
        windows: list[WindowInfo] = []
        if not ok or not output:
            return windows

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 7:
                continue
            try:
                windows.append(
                    WindowInfo(
                        title=parts[0],
                        app=parts[1],
                        x=int(parts[2]),
                        y=int(parts[3]),
                        width=int(parts[4]),
                        height=int(parts[5]),
                        is_focused=parts[6] == "1",
                    )
                )
            except (ValueError, IndexError):
                continue

        return windows

    def focus_window(self, title: str) -> bool:
        """
        Bring a window to the foreground by partial title match.

        Iterates all foreground processes and their windows; activates the
        first process that owns a window whose title contains *title*
        (case-insensitive).

        Parameters
        ----------
        title:
            Substring of the window title to search for.

        Returns
        -------
        bool
            ``True`` if a matching window was found and its app activated.
        """
        title_lower = title.lower()
        windows = self.get_windows()
        for win in windows:
            if title_lower in win.title.lower():
                return self.focus_app(win.app)
        return False

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def get_clipboard(self) -> ClipboardContent:
        """
        Read the current macOS clipboard contents.

        Uses ``pbpaste`` to retrieve plain text.  File URLs on the clipboard
        (``file://`` scheme) are parsed into the ``files`` list.

        Returns
        -------
        ClipboardContent
            Clipboard state.  ``text`` is ``None`` when nothing is on the
            clipboard or ``pbpaste`` fails.
        """
        rc, out, _ = _run(["pbpaste"])
        if rc != 0:
            return ClipboardContent(text=None)

        text: Optional[str] = out if out else None
        files: list[str] = []

        if text:
            # Extract file:// URIs if present (e.g. from Finder copy)
            file_uris = re.findall(r"file://[^\s\r\n]+", text)
            for uri in file_uris:
                # Decode percent-encoded path
                from urllib.parse import unquote, urlparse  # stdlib only

                parsed = urlparse(uri)
                files.append(unquote(parsed.path))

        return ClipboardContent(text=text, files=files)

    def set_clipboard(self, text: str) -> bool:
        """
        Place *text* onto the macOS clipboard.

        Uses ``pbcopy`` to write plain-text content.

        Parameters
        ----------
        text:
            String to place on the clipboard.

        Returns
        -------
        bool
            ``True`` if the write succeeded.
        """
        rc, _, _ = _run(["pbcopy"], input_text=text)
        return rc == 0

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def send_notification(
        self,
        title: str,
        message: str,
        subtitle: str = "",
    ) -> NotificationResult:
        """
        Display a macOS user notification via AppleScript.

        Parameters
        ----------
        title:
            Bold heading of the notification.
        message:
            Body text shown below the title.
        subtitle:
            Optional secondary heading shown between title and body.

        Returns
        -------
        NotificationResult
            ``sent=True`` on success, otherwise ``sent=False`` with an
            ``error`` description.
        """
        # Escape double-quotes for embedding in AppleScript string literals
        def _esc(s: str) -> str:
            return s.replace("\\", "\\\\").replace('"', '\\"')

        subtitle_clause = ""
        if subtitle:
            subtitle_clause = f' subtitle "{_esc(subtitle)}"'

        script = (
            f'display notification "{_esc(message)}"'
            f" with title \"{_esc(title)}\""
            f"{subtitle_clause}"
        )
        ok, err = _osascript(script)
        if ok:
            return NotificationResult(sent=True)
        return NotificationResult(sent=False, error=err)

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    # Map of human-friendly modifier names → AppleScript modifier constants
    _MODIFIER_MAP: dict[str, str] = {
        "cmd":     "command down",
        "command": "command down",
        "ctrl":    "control down",
        "control": "control down",
        "opt":     "option down",
        "option":  "option down",
        "alt":     "option down",
        "shift":   "shift down",
        "fn":      "function down",
    }

    # Special key names → AppleScript key code numbers
    _SPECIAL_KEYS: dict[str, str] = {
        "return":    "key code 36",
        "enter":     "key code 36",
        "tab":       "key code 48",
        "space":     "key code 49",
        "delete":    "key code 51",
        "backspace":  "key code 51",
        "escape":    "key code 53",
        "esc":       "key code 53",
        "left":      "key code 123",
        "right":     "key code 124",
        "down":      "key code 125",
        "up":        "key code 126",
        "f1":        "key code 122",
        "f2":        "key code 120",
        "f3":        "key code 99",
        "f4":        "key code 118",
        "f5":        "key code 96",
        "f6":        "key code 97",
        "f7":        "key code 98",
        "f8":        "key code 100",
        "f9":        "key code 101",
        "f10":       "key code 109",
        "f11":       "key code 103",
        "f12":       "key code 111",
        "home":      "key code 115",
        "end":       "key code 119",
        "pageup":    "key code 116",
        "pagedown":  "key code 121",
        "forwarddelete": "key code 117",
    }

    def run_shortcut(self, app: str, shortcut: str) -> bool:
        """
        Send a keyboard shortcut to an application.

        The *shortcut* string uses ``+``-separated tokens such as
        ``"cmd+s"``, ``"cmd+shift+t"``, ``"ctrl+alt+delete"``, etc.
        Modifier tokens are matched case-insensitively.  The final token is
        treated as the key to press; if it matches a known special key name
        the corresponding key code is used, otherwise it is sent as a
        literal keystroke character.

        Parameters
        ----------
        app:
            Target application name (the app will be activated first).
        shortcut:
            Key combination string, e.g. ``"cmd+shift+n"``.

        Returns
        -------
        bool
            ``True`` if the AppleScript command was dispatched without error.
        """
        tokens = [t.strip().lower() for t in shortcut.split("+")]
        if not tokens:
            return False

        key_token = tokens[-1]
        modifier_tokens = tokens[:-1]

        modifiers: list[str] = []
        for mod in modifier_tokens:
            mapped = self._MODIFIER_MAP.get(mod)
            if mapped:
                modifiers.append(mapped)

        using_clause = ""
        if modifiers:
            using_clause = " using {" + ", ".join(modifiers) + "}"

        # Build the keystroke/key code instruction
        if key_token in self._SPECIAL_KEYS:
            key_instruction = self._SPECIAL_KEYS[key_token] + using_clause
        else:
            # Escape the key character for AppleScript
            escaped_key = key_token.replace("\\", "\\\\").replace('"', '\\"')
            key_instruction = f'keystroke "{escaped_key}"{using_clause}'

        script = (
            f'tell application "{app}" to activate\n'
            f"tell application \"System Events\"\n"
            f"    tell process \"{app}\"\n"
            f"        {key_instruction}\n"
            f"    end tell\n"
            f"end tell"
        )
        ok, _ = _osascript(script)
        return ok

    # ------------------------------------------------------------------
    # Text-to-speech
    # ------------------------------------------------------------------

    def speak(self, text: str, voice: str = "Samantha") -> None:
        """
        Speak *text* aloud using macOS text-to-speech.

        The call blocks until speech is complete.

        Parameters
        ----------
        text:
            Text to speak.
        voice:
            macOS voice name (default ``"Samantha"``).  Run
            ``say -v ?`` in Terminal to list available voices.
        """
        _run(["say", "-v", voice, text], timeout=120)

    # ------------------------------------------------------------------
    # Raw AppleScript execution
    # ------------------------------------------------------------------

    def run_applescript(self, script: str) -> tuple[bool, str]:
        """
        Execute arbitrary AppleScript source code.

        Parameters
        ----------
        script:
            Complete AppleScript program to run.

        Returns
        -------
        tuple[bool, str]
            ``(True, stdout)`` on success; ``(False, error_message)`` on
            failure.
        """
        return _osascript(script)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_service: Optional[AppAutomationService] = None


def get_app_automation() -> AppAutomationService:
    """
    Return the module-level singleton ``AppAutomationService``.

    The instance is created lazily on first access and reused for all
    subsequent calls.

    Returns
    -------
    AppAutomationService
        Shared service instance.
    """
    global _service
    if _service is None:
        _service = AppAutomationService()
    return _service
