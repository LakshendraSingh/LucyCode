"""
Slash command suite for workstation automation (/automate, /workflow).
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from typing import Any

from lucy.core.commands import Command, CommandResult, register_command
from lucy.services.app_automation import get_app_automation
from lucy.services.browser_automation import get_browser_automation
from lucy.services.screen_automation import get_screen_automation
from lucy.services.workflow_engine import get_workflow_engine


class AutomateCommand(Command):
    """Command suite for controlling applications, windows, browser, and automation workflows."""

    name = "automate"
    description = "Workstation automation controls (apps, browser, screen, workflows)"
    aliases = ["automation", "workstation"]

    async def execute(self, args_str: str, state: Any) -> CommandResult:
        parts = args_str.strip().split(maxsplit=1) if args_str else []
        sub = parts[0].lower() if parts else "help"
        rest = parts[1] if len(parts) > 1 else ""

        if sub in ("help", "--help", "-h"):
            return self._help()

        # ------------------------------------------------------------------
        # Workflows
        # ------------------------------------------------------------------
        if sub in ("workflow", "wf"):
            return await self._handle_workflow(rest)

        # ------------------------------------------------------------------
        # Apps
        # ------------------------------------------------------------------
        if sub in ("app", "apps"):
            return self._handle_apps(rest)

        # ------------------------------------------------------------------
        # Browser
        # ------------------------------------------------------------------
        if sub == "browser":
            return await self._handle_browser(rest)

        # ------------------------------------------------------------------
        # Screen & Vision
        # ------------------------------------------------------------------
        if sub in ("screen", "screenshot"):
            return self._handle_screen(sub, rest)

        # ------------------------------------------------------------------
        # Clipboard
        # ------------------------------------------------------------------
        if sub in ("clip", "clipboard"):
            return self._handle_clipboard(rest)

        # ------------------------------------------------------------------
        # Notification & Speech
        # ------------------------------------------------------------------
        if sub == "notify":
            return self._handle_notify(rest)

        if sub == "speak":
            return self._handle_speak(rest)

        # ------------------------------------------------------------------
        # AppleScript
        # ------------------------------------------------------------------
        if sub in ("applescript", "osascript"):
            return self._handle_applescript(rest)

        return CommandResult(
            error=f"Unknown automation sub-command: '{sub}'. Run '/automate help' for options."
        )

    def _help(self) -> CommandResult:
        help_text = """
Workstation Automation Commands (/automate)
--------------------------------------------
Workflow Management:
  /automate workflow list                     List saved workflows
  /automate workflow create <name> [desc]     Create a new workflow
  /automate workflow add-step <id> <type> <json_params> [desc]  Add step to workflow
  /automate workflow run <id>                 Execute workflow
  /automate workflow show <id>                Inspect workflow steps
  /automate workflow delete <id>              Delete workflow

Applications:
  /automate apps list                         List running applications & window counts
  /automate apps launch <name>                Launch an application
  /automate apps focus <name>                 Bring application to foreground
  /automate apps quit <name>                  Quit an application

Browser:
  /automate browser open <url>                Open URL in browser
  /automate browser search <query>            Perform Web search and extract snippets
  /automate browser text                      Extract visible text from current page

Desktop & Hardware:
  /automate screenshot [path]                 Capture desktop screenshot
  /automate screen info                       Display monitor resolution and scale
  /automate clipboard get                     Read system clipboard
  /automate clipboard set <text>              Write to system clipboard
  /automate notify <title> | <message>        Display desktop banner notification
  /automate speak <text>                      Speak message aloud via text-to-speech
  /automate applescript <script>              Execute inline AppleScript
"""
        return CommandResult(output=help_text.strip())

    async def _handle_workflow(self, rest: str) -> CommandResult:
        engine = get_workflow_engine()
        parts = rest.split(maxsplit=1)
        sub = parts[0].lower() if parts else "list"
        arg = parts[1] if len(parts) > 1 else ""

        if sub == "list":
            wfs = engine.list_workflows()
            if not wfs:
                return CommandResult(output="No saved workflows. Create one with: /automate workflow create <name>")
            lines = [f"{w.id:<10} {w.name:<24} {len(w.steps):<6} steps  {w.description}" for w in wfs]
            header = f"{'ID':<10} {'NAME':<24} {'STEPS':<6}        DESCRIPTION\n" + "-" * 60
            return CommandResult(output=header + "\n" + "\n".join(lines))

        elif sub == "create":
            p = arg.split(maxsplit=1)
            name = p[0] if p else "New Workflow"
            desc = p[1] if len(p) > 1 else ""
            wf = engine.create_workflow(name, desc)
            return CommandResult(output=f"Created workflow '{wf.name}' (ID: {wf.id})")

        elif sub == "show":
            wf = engine.load_workflow(arg.strip())
            if not wf:
                return CommandResult(error=f"Workflow '{arg.strip()}' not found.")
            lines = [f"Workflow: {wf.name} (ID: {wf.id}) - {wf.description}"]
            lines.append("-" * 60)
            for i, s in enumerate(wf.steps, start=1):
                lines.append(f"{i}. [{s.type.upper()}] {s.description} (params: {s.params})")
            return CommandResult(output="\n".join(lines))

        elif sub == "add-step":
            try:
                tokens = shlex.split(arg)
                if len(tokens) < 3:
                    return CommandResult(error="Usage: /automate workflow add-step <id> <type> <json_params> [desc]")
                wid, stype, sparams_raw = tokens[0], tokens[1], tokens[2]
                sdesc = tokens[3] if len(tokens) > 3 else ""
                sparams = json.loads(sparams_raw)
                step = engine.add_step(wid, stype, sparams, sdesc)
                if step:
                    return CommandResult(output=f"Added step {step.id} ({step.type}) to workflow {wid}")
                return CommandResult(error=f"Workflow '{wid}' not found.")
            except Exception as e:
                return CommandResult(error=f"Failed to add step: {e}")

        elif sub == "run":
            wid = arg.strip()
            wf = engine.load_workflow(wid)
            if not wf:
                return CommandResult(error=f"Workflow '{wid}' not found.")
            summary = [f"Starting execution of '{wf.name}'..."]
            async for run in engine.execute(wid):
                if run.results:
                    last = run.results[-1]
                    status = "OK" if last.success else "FAIL"
                    summary.append(f"  [{status}] {last.step_id}: {last.output or last.error}")
            return CommandResult(output="\n".join(summary))

        elif sub == "delete":
            ok = engine.delete_workflow(arg.strip())
            return CommandResult(output=f"Deleted workflow {arg.strip()}") if ok else CommandResult(error=f"Workflow {arg.strip()} not found.")

        return CommandResult(error=f"Unknown workflow action: '{sub}'.")

    def _handle_apps(self, rest: str) -> CommandResult:
        auto = get_app_automation()
        parts = rest.split(maxsplit=1)
        sub = parts[0].lower() if parts else "list"
        arg = parts[1] if len(parts) > 1 else ""

        if sub == "list":
            apps = auto.list_running_apps()
            lines = [f"{a.name:<28} PID: {a.pid:<8} Windows: {len(a.windows)}" for a in apps[:40]]
            return CommandResult(output=f"Running Applications ({len(apps)} total):\n" + "\n".join(lines))
        elif sub == "launch":
            ok = auto.launch_app(arg.strip())
            return CommandResult(output=f"Launched '{arg.strip()}'") if ok else CommandResult(error=f"Failed to launch '{arg.strip()}'.")
        elif sub == "focus":
            ok = auto.focus_app(arg.strip())
            return CommandResult(output=f"Focused '{arg.strip()}'") if ok else CommandResult(error=f"Failed to focus '{arg.strip()}'.")
        elif sub == "quit":
            ok = auto.quit_app(arg.strip())
            return CommandResult(output=f"Quit '{arg.strip()}'") if ok else CommandResult(error=f"Failed to quit '{arg.strip()}'.")

        return CommandResult(error="Usage: /automate apps [list|launch|focus|quit] <name>")

    async def _handle_browser(self, rest: str) -> CommandResult:
        b = get_browser_automation()
        parts = rest.split(maxsplit=1)
        sub = parts[0].lower() if parts else "text"
        arg = parts[1] if len(parts) > 1 else ""

        if sub == "open":
            res = await b.open_url(arg.strip())
            return CommandResult(output=res.output) if res.success else CommandResult(error=res.error)
        elif sub == "search":
            text = await b.search_web_and_read(arg.strip())
            return CommandResult(output=text)
        elif sub == "text":
            text = await b.get_page_text()
            return CommandResult(output=text[:3000])

        return CommandResult(error="Usage: /automate browser [open <url>|search <query>|text]")

    def _handle_screen(self, sub: str, rest: str) -> CommandResult:
        screen = get_screen_automation()
        if sub == "screenshot" or rest.startswith("shot"):
            path = rest.split()[-1] if ("/" in rest or ".png" in rest) else "/tmp/lucy_screenshot.png"
            b64 = screen.screenshot()
            import base64
            with open(path, "wb") as f:
                f.write(base64.b64decode(b64))
            return CommandResult(output=f"Captured desktop screenshot: {path}")
        elif "info" in rest or sub == "screen":
            info = screen.get_screen_info()
            return CommandResult(output=f"Screen Geometry: {info.width}x{info.height} (Scale: {info.scale_factor}x, {len(info.monitors)} monitors)")
        return CommandResult(error="Usage: /automate screen [info|screenshot <path>]")

    def _handle_clipboard(self, rest: str) -> CommandResult:
        auto = get_app_automation()
        parts = rest.split(maxsplit=1)
        sub = parts[0].lower() if parts else "get"
        val = parts[1] if len(parts) > 1 else ""

        if sub == "get":
            content = auto.get_clipboard()
            return CommandResult(output=f"Clipboard: {content.text or '(empty)'}")
        elif sub == "set":
            ok = auto.set_clipboard(val)
            return CommandResult(output=f"Copied to clipboard ({len(val)} chars)") if ok else CommandResult(error="Failed to set clipboard")
        return CommandResult(error="Usage: /automate clipboard [get|set <text>]")

    def _handle_notify(self, rest: str) -> CommandResult:
        auto = get_app_automation()
        if "|" in rest:
            title, msg = rest.split("|", 1)
        else:
            title, msg = "LucyCode Workstation", rest
        res = auto.send_notification(title.strip(), msg.strip())
        return CommandResult(output=f"Notification delivered: {title.strip()}") if res.sent else CommandResult(error=res.error or "Failed")

    def _handle_speak(self, rest: str) -> CommandResult:
        auto = get_app_automation()
        auto.speak(rest.strip())
        return CommandResult(output=f"Spoke aloud: '{rest.strip()}'")

    def _handle_applescript(self, rest: str) -> CommandResult:
        auto = get_app_automation()
        ok, out = auto.run_applescript(rest.strip())
        return CommandResult(output=out or "Executed successfully.") if ok else CommandResult(error=f"AppleScript error: {out}")


def get_commands() -> list[Command]:
    return [AutomateCommand()]


def register():
    register_command(AutomateCommand())
