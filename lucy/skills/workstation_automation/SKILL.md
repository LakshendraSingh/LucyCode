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

LucyCode incorporates an autonomous workstation engine (analogous to OpenClaw and OpenInterpreter) allowing end-to-end control of macOS apps, browser navigation, display OCR, native notifications, and persistent multi-step automation scripts.

## 1. Tool Selection Hierarchy

- **Application Lifecycle**:
  - Use `launch_app` to start applications (e.g., Slack, Chrome, VS Code, Notes).
  - Use `focus_app` to bring an existing window to front before sending shortcuts or keystrokes.
  - Use `list_apps` to verify process state before attempting interaction.
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

## 2. Multi-Step Automation Workflows

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

