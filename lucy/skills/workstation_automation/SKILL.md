---
name: workstation-automation
description: Autonomous desktop and workstation automation guidelines for macOS app control, browser manipulation, OCR vision, and multi-step workflows.
version: "1.0.0"
priority: 8
tags: ["automation", "workstation", "macos", "computer-use", "workflow", "browser"]
activates_on:
  keywords: ["automate", "open app", "click", "screenshot", "workflow", "notify", "clipboard", "browser", "applescript", "schedule", "workstation", "computer use", "control"]
  file_patterns: []
  project_files: []
  always: false
---

# Workstation & Desktop Automation Guidelines

LucyCode incorporates an autonomous workstation engine allowing end-to-end control of macOS apps, browser navigation, display OCR, native notifications, and persistent multi-step automation scripts.

## 1. Universal UI Automation & Closed-Loop Verification

To generalize across ANY macOS application (native, Electron, web browser, or Catalyst) without brittle shortcut guessing or false positives:

1. **Inspect Before Acting (`ui_inspect`)**:
   - Query the active application, window title, and browser URL before taking action.
   - If automating a browser (Safari/Chrome), verify that the active tab matches the target web application (e.g. `mail.google.com`) before trying to interact.
2. **Deterministic Targeting (`ui_menu` and `ui_click`)**:
   - **Menu Bar Navigation (`ui_menu`)**: Every macOS application exposes standard menus (`File > New`, `Edit > Paste`, `Window > ...`). Use `ui_menu` to open documents or trigger actions universally across 100% of apps without guessing keyboard shortcuts.
   - **Interactive Elements (`ui_click`)**: Click buttons or controls by their accessibility label (`'Compose'`, `'Send'`, `'Save'`). If the element does not exist, `ui_click` reports an error with visible controls rather than falsely claiming success.
3. **Reliable Text Entry (`ui_type`)**:
   - Uses clipboard-backed injection (`pbcopy` + command-v) to prevent dropped characters or missed key events.
4. **Closed-Loop Verification (`ui_verify`)**:
   - Before telling the user a task is complete, run `ui_verify` to confirm that the expected state change occurred (e.g. window title updated, browser URL changed, or modal closed).
   - **Zero False Positives**: If an element is missing or verification fails, report the actual screen state to the user instead of falsely claiming completion.

## 2. Tool Selection Hierarchy

- **Application Lifecycle**:
  - Use `launch_app` to start applications (e.g., Slack, Chrome, VS Code, Notes).
  - Use `focus_app` to bring an existing window to front before sending shortcuts or keystrokes.
  - Use `list_apps` to verify process state before attempting interaction.
- **Universal UI & Menu Control**:
  - Use `ui_inspect` to view active controls, window title, and browser URL.
  - Use `ui_menu` for deterministic action triggering across any app.
  - Use `ui_click` to click labeled controls with existence checks.
  - Use `ui_type` to fill text into fields reliably.
  - Use `ui_verify` to audit outcome before declaring success.
- **Deep macOS App Control**:
  - Prefer `applescript` for robust, deterministic application automation (e.g. querying tabs in Chrome, triggering menu items, interacting with Mail or Calendar).
- **Vision & Display**:
  - Use `screen_info` to query resolution and scale factors.
  - Use `screenshot` to verify layout or visual output.
  - Use `find_on_screen` to locate buttons, icons, or text coordinates prior to clicking.
- **Web Navigation**:
  - Use `browser(action="search", query="...")` to research documentation or solutions without spawning a heavyweight headless browser.
  - Use `browser(action="open", url="...")` to open sites or portals.
  - Use `browser(action="get_text")` to consume page contents.
- **Audible and Visual Feedback**:
  - Use `notify` to alert the user when builds, exports, or long workflows finish.
  - Use `speak` sparingly for hands-free audio announcements when the user is away from the screen.
- **Clipboard**:
  - Use `clipboard(action="get")` or `clipboard(action="set", text="...")` to bridge data between apps.

## 3. Multi-Step Automation Workflows

When the user asks for a reusable or recurring sequence of tasks (e.g. "Every morning open Jira, Slack, and my terminal" or "Take a screenshot of the site, run tests, and notify me"):

1. Create a named workflow via `workflow(action="create", name="...", description="...")`.
2. Add sequential atomic steps:
   - `bash`: Build commands, git commands, script runs.
   - `open_app`: Opening editor, terminal, or communication apps.
   - `open_url`: Opening web dashboards.
   - `wait`: Giving apps time to initialize (e.g. 2-5 seconds).
   - `screenshot`: Auditing final state.
   - `notify`: Informing the user of completion.
3. Run the workflow with `workflow(action="run", workflow_id="...")`.

## 3. Safety Guardrails & Best Practices

- **Never Automate Password Fields**: Never read, copy, or type into password fields, Master Password prompts, or keychain access dialogs.
- **Confirm Destructive Operations**: Explicitly prompt or ask before quitting apps with unsaved work or terminating processes.
- **Visual Verification Loop**: Always take a screenshot or read page text *after* navigation or button clicks to verify the UI updated as expected.
- **Graceful Error Recovery**: In workflows, set `on_error="skip"` for non-critical steps (like playing audio or notifications) and `on_error="stop"` for core data steps.

