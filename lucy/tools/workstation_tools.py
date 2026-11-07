"""
Workstation automation tool suite for LucyCode.

Provides full desktop environment control: window management, application control,
AppleScript automation, clipboard sync, notifications, text-to-speech, screen OCR,
browser navigation, and persistent multi-step workflow execution.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


class ScreenshotTool(Tool):
    """Capture full desktop or cropped region screenshot."""

    @property
    def name(self) -> str:
        return "screenshot"

    @property
    def description(self) -> str:
        return "Capture a desktop screenshot and return base64 encoded PNG."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "monitor": {"type": "integer", "description": "0 for primary/all, 1 for monitor 1", "default": 0},
                "region": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                    },
                    "description": "Optional bounding box crop",
                },
            },
        }

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    def get_prompt(self) -> str:
        return "Capture desktop screenshot to visually inspect the user's workstation state."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.screen_automation import ScreenRegion, get_screen_automation
        reg_data = tool_input.get("region")
        reg = ScreenRegion.from_dict(reg_data) if reg_data else None
        mon = tool_input.get("monitor", 0)
        try:
            b64 = get_screen_automation().screenshot(monitor=mon, region=reg)
            return ToolResult(data=f"Screenshot taken ({len(b64)} chars base64). First 80 chars: {b64[:80]}...")
        except Exception as e:
            return ToolResult(error=f"Screenshot capture failed: {e}")


class FindTextOnScreenTool(Tool):
    """Locate textual elements on screen via OCR."""

    @property
    def name(self) -> str:
        return "find_on_screen"

    @property
    def description(self) -> str:
        return "Find coordinates of a specific word or phrase currently rendered on the user's screen."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The exact text or label to find"},
                "case_sensitive": {"type": "boolean", "default": False},
            },
            "required": ["text"],
        }

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    def get_prompt(self) -> str:
        return "Find UI elements or buttons on screen by label before clicking them."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.screen_automation import get_screen_automation
        text = tool_input.get("text", "")
        case_sensitive = tool_input.get("case_sensitive", False)
        res = get_screen_automation().find_text_on_screen(text, case_sensitive=case_sensitive)
        return ToolResult(data=json.dumps(res.to_dict(), indent=2))


class LaunchAppTool(Tool):
    """Launch or activate an application on the user's workstation."""

    @property
    def name(self) -> str:
        return "launch_app"

    @property
    def description(self) -> str:
        return "Launch an application by name or bundle path."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "app": {"type": "string", "description": "Application name, e.g. 'Slack', 'Google Chrome', 'Notes'"},
                "args": {"type": "array", "items": {"type": "string"}, "description": "Optional CLI arguments to pass"},
            },
            "required": ["app"],
        }

    def is_destructive(self, tool_input: dict[str, Any]) -> bool:
        return True

    def get_prompt(self) -> str:
        return "Launch an application on the workstation."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.app_automation import get_app_automation
        app = tool_input.get("app", "")
        args = tool_input.get("args", [])
        ok = get_app_automation().launch_app(app, args=args)
        if ok:
            return ToolResult(data=f"Successfully launched {app}")
        return ToolResult(error=f"Failed to launch application '{app}'")


class FocusAppTool(Tool):
    """Bring an application to the foreground."""

    @property
    def name(self) -> str:
        return "focus_app"

    @property
    def description(self) -> str:
        return "Bring a running application to the front window."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "app": {"type": "string", "description": "Application name to bring to foreground"},
            },
            "required": ["app"],
        }

    def get_prompt(self) -> str:
        return "Focus an application window."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.app_automation import get_app_automation
        app = tool_input.get("app", "")
        ok = get_app_automation().focus_app(app)
        if ok:
            return ToolResult(data=f"Focused application '{app}'")
        return ToolResult(error=f"Could not focus '{app}'. Make sure it is running.")


class ListAppsTool(Tool):
    """List running desktop applications and window titles."""

    @property
    def name(self) -> str:
        return "list_apps"

    @property
    def description(self) -> str:
        return "List all currently running applications and open windows on the workstation."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    def get_prompt(self) -> str:
        return "Inspect active workstation processes and visible windows."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.app_automation import get_app_automation
        apps = get_app_automation().list_running_apps()
        out = [f"- {a.name} (PID: {a.pid}, Windows: {len(a.windows)})" for a in apps]
        return ToolResult(data=f"Running Applications ({len(apps)} total):\n" + "\n".join(out))


class TypeTextTool(Tool):
    """Type or paste text into an application or frontmost window."""

    @property
    def name(self) -> str:
        return "type_text"

    @property
    def description(self) -> str:
        return (
            "Type or paste text directly into a desktop application (e.g. 'Microsoft Word', 'TextEdit', 'Safari', 'Notes') "
            "or the frontmost window. When target is Microsoft Word, creates a new document and writes the content automatically."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text, essay, message, or paragraph to write into the application"},
                "app": {"type": "string", "description": "Target application name (e.g. 'Microsoft Word', 'TextEdit', 'Safari'). If omitted, writes to frontmost app."},
                "method": {"type": "string", "enum": ["paste", "type"], "default": "paste", "description": "'paste' uses clipboard (cmd+v) for instant reliable insertion; 'type' types character-by-character."},
            },
            "required": ["text"],
        }

    def get_prompt(self) -> str:
        return "Write essays, messages, or text into desktop application documents."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.app_automation import get_app_automation
        auto = get_app_automation()
        text = tool_input.get("text", "")
        app = tool_input.get("app")
        method = tool_input.get("method", "paste")

        # Focus app if specified
        if app:
            auto.launch_app(app)
            auto.focus_app(app)
            await asyncio.sleep(0.5)

        # 1. Specialized macOS Microsoft Word Automation
        if app and ("word" in app.lower() or "microsoft word" in app.lower()):
            escaped_text = text.replace('\\', '\\\\').replace('"', '\\"')
            word_script = f"""
            tell application "Microsoft Word"
                activate
                if (count of documents) = 0 then
                    make new document
                end if
                set content of text object of active document to "{escaped_text}"
            end tell
            """
            ok, out = auto.run_applescript(word_script)
            if ok:
                word_count = len(text.split())
                return ToolResult(data=f"Successfully created document and wrote {word_count} words in Microsoft Word.")

        # 2. Specialized TextEdit Automation
        if app and "textedit" in app.lower():
            escaped_text = text.replace('\\', '\\\\').replace('"', '\\"')
            te_script = f"""
            tell application "TextEdit"
                activate
                if (count of documents) = 0 then
                    make new document
                end if
                set text of front document to "{escaped_text}"
            end tell
            """
            ok, out = auto.run_applescript(te_script)
            if ok:
                return ToolResult(data=f"Successfully wrote {len(text.split())} words in TextEdit.")

        # 3. Standard paste method: copy to clipboard and simulate Cmd+V
        if method == "paste":
            auto.set_clipboard(text)
            target = app or (auto.get_frontmost_app().name if auto.get_frontmost_app() else "System Events")
            ok = auto.run_shortcut(target, "cmd+v")
            if ok:
                return ToolResult(data=f"Successfully pasted {len(text.split())} words into {target}.")

        # 4. Keystroke character by character fallback via System Events
        escaped = text.replace('\\', '\\\\').replace('"', '\\"')
        script = f"""
        tell application "System Events"
            keystroke "{escaped}"
        end tell
        """
        ok, out = auto.run_applescript(script)
        if ok:
            return ToolResult(data=f"Successfully typed {len(text)} characters.")
        return ToolResult(error=f"Failed to type text: {out}")


class KeyShortcutTool(Tool):
    """Send a keyboard shortcut or key press to an application."""

    @property
    def name(self) -> str:
        return "key_shortcut"

    @property
    def description(self) -> str:
        return (
            "Send keyboard shortcuts (e.g. 'cmd+n' for new document, 'cmd+s' to save, 'return', 'tab') "
            "to the active or target application."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "shortcut": {"type": "string", "description": "Key combination (e.g. 'cmd+n', 'cmd+s', 'return', 'tab', 'cmd+enter')"},
                "app": {"type": "string", "description": "Target application name. If omitted, targets frontmost app."},
            },
            "required": ["shortcut"],
        }

    def get_prompt(self) -> str:
        return "Dispatch keyboard shortcuts to active applications."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.app_automation import get_app_automation
        auto = get_app_automation()
        shortcut = tool_input.get("shortcut", "")
        app = tool_input.get("app")
        target = app or (auto.get_frontmost_app().name if auto.get_frontmost_app() else "System Events")
        ok = auto.run_shortcut(target, shortcut)
        if ok:
            return ToolResult(data=f"Sent key shortcut '{shortcut}' to {target}.")
        return ToolResult(error=f"Failed to send shortcut '{shortcut}' to {target}.")


class SendNotificationTool(Tool):
    """Deliver a native desktop system notification."""

    @property
    def name(self) -> str:
        return "notify"

    @property
    def description(self) -> str:
        return "Display a native desktop banner notification to inform the user."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Notification title"},
                "message": {"type": "string", "description": "Notification body text"},
                "subtitle": {"type": "string", "description": "Optional subtitle", "default": ""},
            },
            "required": ["title", "message"],
        }

    def get_prompt(self) -> str:
        return "Alert the user when an automation step or build finishes."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.app_automation import get_app_automation
        title = tool_input.get("title", "LucyCode")
        message = tool_input.get("message", "")
        subtitle = tool_input.get("subtitle", "")
        res = get_app_automation().send_notification(title, message, subtitle)
        if res.sent:
            return ToolResult(data=f"Notification delivered: '{title}: {message}'")
        return ToolResult(error=f"Notification error: {res.error}")


class ClipboardTool(Tool):
    """Read or modify the system clipboard."""

    @property
    def name(self) -> str:
        return "clipboard"

    @property
    def description(self) -> str:
        return "Get or set the workstation system clipboard contents."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["get", "set"], "description": "Action to perform"},
                "text": {"type": "string", "description": "Text to write when action is 'set'"},
            },
            "required": ["action"],
        }

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return tool_input.get("action") == "get"

    def get_prompt(self) -> str:
        return "Read from or write to the system clipboard."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.app_automation import get_app_automation
        action = tool_input.get("action", "get")
        if action == "get":
            content = get_app_automation().get_clipboard()
            return ToolResult(data=f"Clipboard Content: {content.text or '(empty)'}")
        elif action == "set":
            text = tool_input.get("text", "")
            ok = get_app_automation().set_clipboard(text)
            if ok:
                return ToolResult(data=f"Copied {len(text)} characters to clipboard.")
            return ToolResult(error="Failed to set clipboard contents.")
        return ToolResult(error=f"Unknown clipboard action '{action}'")


class RunAppleScriptTool(Tool):
    """Execute custom AppleScript for deep macOS application automation."""

    @property
    def name(self) -> str:
        return "applescript"

    @property
    def description(self) -> str:
        return "Execute an AppleScript command or script on macOS."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "AppleScript source code to execute"},
            },
            "required": ["script"],
        }

    def is_destructive(self, tool_input: dict[str, Any]) -> bool:
        return True

    def get_prompt(self) -> str:
        return "Control macOS system and native apps via AppleScript."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.app_automation import get_app_automation
        script = tool_input.get("script", "")
        ok, out = get_app_automation().run_applescript(script)
        if ok:
            return ToolResult(data=out or "AppleScript executed successfully.")
        return ToolResult(error=f"AppleScript error: {out}")


class BrowserTool(Tool):
    """Control web browser: open URLs, navigate tabs, read DOM, evaluate JS."""

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return "Automate browser navigation, search, screenshot capture, DOM inspection, and click actions."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["open", "screenshot", "get_text", "get_html", "click", "type", "scroll", "js", "search"],
                    "description": "Browser action to execute",
                },
                "url": {"type": "string", "description": "URL to navigate when action is 'open'"},
                "browser": {"type": "string", "description": "Specific browser application to target (e.g. 'Safari', 'Google Chrome')"},
                "selector": {"type": "string", "description": "CSS selector for click/type"},
                "text": {"type": "string", "description": "Text to type"},
                "script": {"type": "string", "description": "JavaScript code when action is 'js'"},
                "query": {"type": "string", "description": "Search query when action is 'search'"},
            },
            "required": ["action"],
        }

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return tool_input.get("action") in ("screenshot", "get_text", "get_html", "search")

    def get_prompt(self) -> str:
        return "Interact with web pages and browsers."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.browser_automation import get_browser_automation
        b = get_browser_automation()
        action = tool_input.get("action")

        if action == "open":
            res = await b.open_url(tool_input.get("url", ""), browser_name=tool_input.get("browser"))
            return ToolResult(data=res.output) if res.success else ToolResult(error=res.error)
        elif action == "search":
            res = await b.search_web_and_read(tool_input.get("query", ""))
            return ToolResult(data=res)
        elif action == "get_text":
            text = await b.get_page_text()
            return ToolResult(data=text[:4000])
        elif action == "get_html":
            dom = await b.get_page_html()
            return ToolResult(data=dom[:5000])
        elif action == "click":
            res = await b.click(tool_input.get("selector", ""))
            return ToolResult(data=res.output) if res.success else ToolResult(error=res.error)
        elif action == "type":
            res = await b.type_text(tool_input.get("selector", ""), tool_input.get("text", ""))
            return ToolResult(data=res.output) if res.success else ToolResult(error=res.error)
        elif action == "scroll":
            res = await b.scroll()
            return ToolResult(data=res.output) if res.success else ToolResult(error=res.error)
        elif action == "screenshot":
            b64 = await b.take_screenshot()
            return ToolResult(data=f"Browser screenshot taken ({len(b64)} chars base64).")
        elif action == "js":
            out = await b.evaluate_js(tool_input.get("script", ""))
            return ToolResult(data=f"JavaScript evaluation result: {out}")
        return ToolResult(error=f"Unknown browser action '{action}'")


class EmailTool(Tool):
    """Draft, compose, and send emails via Gmail (in Safari/Chrome), Apple Mail, or default client."""

    @property
    def name(self) -> str:
        return "email"

    @property
    def description(self) -> str:
        return (
            "Compose, draft, and send emails directly. For Gmail, automatically generates and opens the pre-filled "
            "compose window in Safari or Chrome, and optionally dispatches the email automatically via Send shortcut."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address (e.g. 'laksh28kit@gmail.com')"},
                "subject": {"type": "string", "description": "Email subject line", "default": ""},
                "body": {"type": "string", "description": "Email message body", "default": ""},
                "browser": {"type": "string", "default": "Safari", "description": "Browser to open for Gmail (e.g. 'Safari', 'Google Chrome')"},
                "send": {"type": "boolean", "default": True, "description": "Whether to automatically send the email after opening the compose window"},
            },
            "required": ["to"],
        }

    def get_prompt(self) -> str:
        return "Compose and send emails to recipients."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        import urllib.parse
        from lucy.services.app_automation import get_app_automation
        from lucy.services.browser_automation import get_browser_automation

        to_addr = tool_input.get("to", "").strip()
        subject = tool_input.get("subject", "").strip()
        body = tool_input.get("body", "").strip()
        browser_name = tool_input.get("browser", "Safari")
        auto_send = tool_input.get("send", True)

        if not to_addr:
            return ToolResult(error="Recipient 'to' email address is required.")

        # Construct official direct Gmail compose URL with pre-filled fields
        enc_to = urllib.parse.quote(to_addr)
        enc_su = urllib.parse.quote(subject)
        enc_body = urllib.parse.quote(body)
        gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={enc_to}&su={enc_su}&body={enc_body}"

        # Open in requested browser
        target_browser = "Safari" if "safari" in browser_name.lower() else ("Google Chrome" if "chrome" in browser_name.lower() else browser_name)
        b = get_browser_automation()
        auto = get_app_automation()

        res = await b.open_url(gmail_url, browser_name=target_browser)
        if not res.success:
            return ToolResult(error=f"Could not open Gmail in {target_browser}: {res.error}")

        if auto_send:
            # Wait for Gmail webmail compose DOM to load and gain focus
            await asyncio.sleep(4.0)
            # Send Cmd+Enter (the universal Gmail send shortcut)
            send_script = f"""
            tell application "{target_browser}" to activate
            tell application "System Events"
                tell process "{target_browser}"
                    keystroke return using {{command down}}
                end tell
            end tell
            """
            auto.run_applescript(send_script)
            return ToolResult(data=f"Successfully opened pre-filled Gmail compose in {target_browser} and sent email to '{to_addr}' with subject '{subject}'.")

        return ToolResult(data=f"Opened pre-filled Gmail compose window in {target_browser} addressed to '{to_addr}'.")


class WorkflowTool(Tool):
    """Execute, save, or list automated multi-step workflows."""

    @property
    def name(self) -> str:
        return "workflow"

    @property
    def description(self) -> str:
        return "Create, execute, list, or inspect persistent multi-step workstation automation workflows."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "run", "list", "add_step", "delete"]},
                "workflow_id": {"type": "string", "description": "Workflow identifier"},
                "name": {"type": "string", "description": "Name for new workflow"},
                "description": {"type": "string", "description": "Workflow description"},
                "step_type": {"type": "string", "description": "Step type: bash, open_app, open_url, notify, wait, screenshot, etc."},
                "step_params": {"type": "object", "description": "Step configuration parameters"},
                "step_description": {"type": "string", "description": "Human-readable label for step"},
            },
            "required": ["action"],
        }

    def get_prompt(self) -> str:
        return "Manage automated workflows."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.workflow_engine import get_workflow_engine
        engine = get_workflow_engine()
        action = tool_input.get("action")

        if action == "create":
            name = tool_input.get("name", "New Workflow")
            desc = tool_input.get("description", "")
            wf = engine.create_workflow(name, desc)
            return ToolResult(data=f"Created workflow '{wf.name}' (ID: {wf.id})")

        elif action == "list":
            wfs = engine.list_workflows()
            if not wfs:
                return ToolResult(data="No workflows found in storage.")
            lines = [f"- [{w.id}] {w.name} ({len(w.steps)} steps): {w.description}" for w in wfs]
            return ToolResult(data="Saved Workflows:\n" + "\n".join(lines))

        elif action == "add_step":
            wid = tool_input.get("workflow_id", "")
            stype = tool_input.get("step_type", "bash")
            sparams = tool_input.get("step_params", {})
            sdesc = tool_input.get("step_description", "")
            step = engine.add_step(wid, stype, sparams, sdesc)
            if step:
                return ToolResult(data=f"Added step {step.id} ({step.type}) to workflow {wid}")
            return ToolResult(error=f"Could not add step. Workflow '{wid}' not found.")

        elif action == "run":
            wid = tool_input.get("workflow_id", "")
            summary = []
            try:
                async for update in engine.execute(wid):
                    if update.results:
                        last = update.results[-1]
                        summary.append(f"[{'PASS' if last.success else 'FAIL'}] {last.step_id}: {last.output or last.error}")
                return ToolResult(data=f"Workflow {wid} execution completed.\n" + "\n".join(summary))
            except Exception as e:
                return ToolResult(error=f"Workflow run failed: {e}")

        elif action == "delete":
            wid = tool_input.get("workflow_id", "")
            ok = engine.delete_workflow(wid)
            return ToolResult(data=f"Deleted workflow {wid}") if ok else ToolResult(error=f"Workflow {wid} not found.")

        return ToolResult(error=f"Unknown action: {action}")


class SpeakTool(Tool):
    """Text-to-speech audio feedback."""

    @property
    def name(self) -> str:
        return "speak"

    @property
    def description(self) -> str:
        return "Speak a message aloud using native text-to-speech."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Sentence or message to speak aloud"},
                "voice": {"type": "string", "default": "Samantha", "description": "Voice identifier"},
            },
            "required": ["text"],
        }

    def get_prompt(self) -> str:
        return "Audibly notify user upon long automation completion."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.app_automation import get_app_automation
        text = tool_input.get("text", "")
        voice = tool_input.get("voice", "Samantha")
        get_app_automation().speak(text, voice=voice)
        return ToolResult(data=f"Spoke aloud: '{text}'")


class GetScreenInfoTool(Tool):
    """Inspect display geometry and monitors."""

    @property
    def name(self) -> str:
        return "screen_info"

    @property
    def description(self) -> str:
        return "Inspect primary display dimensions, scale factors, and attached monitors."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    def get_prompt(self) -> str:
        return "Query screen resolution before performing mouse or click operations."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.screen_automation import get_screen_automation
        info = get_screen_automation().get_screen_info()
        return ToolResult(data=json.dumps(info.to_dict(), indent=2))


from lucy.tools.presentation_tools import PresentationTool

WORKSTATION_TOOLS: list[Tool] = [
    ScreenshotTool(),
    FindTextOnScreenTool(),
    LaunchAppTool(),
    FocusAppTool(),
    ListAppsTool(),
    TypeTextTool(),
    KeyShortcutTool(),
    SendNotificationTool(),
    ClipboardTool(),
    RunAppleScriptTool(),
    BrowserTool(),
    EmailTool(),
    WorkflowTool(),
    SpeakTool(),
    GetScreenInfoTool(),
    PresentationTool(),
]

