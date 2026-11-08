# Lucy Code — The Autonomous AI Coding Companion & Agentic Engine

<p align="center">
  <b>Reimagined in Python + C for the Next-Generation Agentic Era</b><br>
  <i>Lightning fast. Deeply integrated. Truly autonomous. Safer with Sandbox Isolation.</i>
</p>

---

Lucy Code is an autonomous, goal-driven AI coding assistant built from the ground up for speed, reliability, security, and universal model connectivity. Whether you are connected to Google Gemini, OpenAI, DeepSeek, Groq, Anthropic, or running completely offline with Ollama or local GGUF weights, Lucy provides an uncompromising agentic experience that plans, writes, verifies, self-corrects, and executes inside a protected sandbox.

> [!IMPORTANT]
> **Disclaimer**: Lucy Code is an AI assistant powered by Large Language Models and can make mistakes. Always review generated code, file modifications, and shell commands before execution, particularly when using autonomous modes or granting unrestricted permissions.

---

## Key Highlights

- **Native Performance**: Core orchestration in **Python 3.10+** with native **C extensions** for blazingly fast regex search, AST diffing, and file traversal.
- **Universal LLM Engine (15+ Providers)**:
  - Native streaming integration with **Gemini (2.5/3.x with thought signature support)**, **OpenAI (GPT-4o, o1, o3-mini)**, **DeepSeek (V3, R1)**, **Groq**, **Mistral**, **Anthropic Claude**, **OpenRouter**, **Together AI**, **Fireworks**, **Ollama**, and **llama.cpp**.
  - Zero-dependency streaming fallback using Python's standard library `urllib` when third-party libraries aren't installed.
- **Goal-Driven Autonomous Engine**:
  - High-level goal decomposition and dynamic replanning.
  - Multi-language automated self-verification (`pytest`, `jest`, `cargo test`, `go test`, `mypy`, `tsc`, `ruff`).
  - Iterative self-correction with error-directed prompt feedback (up to 3 retries).
  - Crash-resilient checkpoints saved in `~/.lucycode/goals/` for pause, resume, and audit.
- **Sandbox Mode & Workspace Protection**:
  - **Filesystem Confinement**: Strict boundary checks restricting file writes to your workspace root and `/tmp/`.
  - **Credential Protection**: Guardrails blocking unauthorized read/write access to sensitive files (`~/.ssh`, `~/.aws`, `~/.gnupg`, keychains, `.env`, `*.pem`, `*.key`).
  - **Command Safety Checks**: Proactive interception of destructive shell operations (`rm -rf /`, `mkfs`, fork bombs, `sudo`).
- **Declarative Skills System**:
  - Open `SKILL.md` format compatible with modern agent standards.
  - **11 Built-in Production Skills**: `presentation-design`, `debugging`, `security-audit`, `code-review`, `performance`, `testing`, `refactoring`, `python`, `typescript`, `git-workflow`, and `api-design`.
  - Context-aware auto-activation based on file extensions, project root indicators, and prompt keywords.
- **Enhanced MCP (Client + Server + SSE)**:
  - Model Context Protocol client supporting `stdio`, `sse`, and `streamable-http` transports with OAuth2 auth.
  - **Lucy as an MCP Server** (`--serve-mcp`): Expose Lucy's tools and intelligence to Claude Desktop, Cursor, Zed, and any MCP-compliant client.
- **Intelligence Amplifiers**:
  - **Parallel Tool Execution**: Concurrently execute non-conflicting read tools (`read`, `grep`, `glob`, `tree`) to drastically cut round-trip latency.
  - **Learning from Corrections**: Automatically captures user feedback and correction patterns in a persistent SQLite knowledge store.
  - **Speculative Pre-fetching**: Analyzes imports in touched files to warm context before you even ask.
  - **Diff-Aware Context Compaction**: Preserves vital conversation history while compressing long token streams.

---

## Quick Start

### 1. Installation

Clone and install Lucy Code in editable mode:

```bash
git clone https://github.com/lucycode/lucycode.git
cd lucycode
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Launch with Your Preferred LLM

#### Google Gemini (Recommended)

Lucy natively handles Google Gemini 3.x models, streaming, tool calling, and Gemini `thought_signature` requirements:

```bash
export GEMINI_API_KEY="your-gemini-api-key"
lucy --model gemini
```

Or run single-turn prompts directly from your shell:

```bash
lucy --model gemini -p "Write an async HTTP client in Python using httpx with retry logic"
```

#### Groq (Ultra-Fast Inference)

```bash
export GROQ_API_KEY="your-groq-api-key"
lucy --model groq:llama-3.3-70b-versatile
```

#### DeepSeek (V3 / R1 Reasoning)

```bash
export DEEPSEEK_API_KEY="your-deepseek-api-key"
lucy --model deepseek:deepseek-reasoner
```

#### OpenAI (GPT-4o, o3-mini)

```bash
export OPENAI_API_KEY="your-openai-api-key"
lucy --model openai:gpt-4o
```

#### Local & Offline (Ollama or Direct GGUF)

No API keys or cloud access required:

```bash
# With Ollama running locally:
lucy --model ollama:llama3.1

# Or point directly to local GGUF weights:
lucy --model weights:/path/to/llama-3-8b.gguf
```

---

## Sandbox Mode

Lucy Code features an integrated **Sandbox Engine** designed to keep your machine safe while granting the AI autonomy to create and edit project files.

### Sandbox Modes

| Mode                        | Writes Permitted         | Sensitive Paths     | Command Safety             |
| :-------------------------- | :----------------------- | :------------------ | :------------------------- |
| **`workspace`** _(Default)_ | Workspace root & `/tmp/` | Protected (Blocked) | Block dangerous commands   |
| **`strict`**                | Workspace root only      | Protected (Blocked) | Strict allowlist execution |
| **`read_only`**             | No writes anywhere       | Protected (Blocked) | Read-only commands only    |

### CLI Options

```bash
# Enable workspace sandbox mode (default)
lucy --sandbox

# Select a specific sandbox isolation level
lucy --sandbox --sandbox-mode strict
lucy --sandbox --sandbox-mode read_only
```

### Interactive Sandbox Control

Inside Lucy's REPL, check status or toggle modes on the fly:

```text
/sandbox status           # View current sandbox policy and stats
/sandbox strict           # Switch to strict workspace isolation
/sandbox workspace        # Switch to workspace + /tmp/
/sandbox read_only        # Block all filesystem writes
/sandbox allow /path/dir  # Temporarily allow an external directory
/sandbox off              # Disable sandbox (requires confirmation)
```

---

## Goal-Driven Autonomous Engine

Instead of issuing micro-instructions, give Lucy a high-level goal. Lucy decomposes the task, generates code, runs project tests/linters, and self-corrects until verification passes.

### Running a Goal from CLI

```bash
lucy --goal "Implement an LRU Cache in C++ with O(1) get and put, and write comprehensive doctests"
```

### Interactive `/goal` Commands

```text
/goal start "Refactor auth middleware to JWT with refresh tokens"
/goal status       # View goal progress, sub-tasks, and verification status
/goal resume       # Resume execution from the last saved checkpoint
/goal cancel       # Cancel the currently active goal
/goal list         # List all saved goal checkpoints
```

### Verification Pipeline

Lucy automatically detects and runs appropriate verification suites:

- **Python**: `pytest`, `unittest`, `mypy`, `ruff`, `flake8`
- **JavaScript / TypeScript**: `jest`, `vitest`, `npm test`, `tsc --noEmit`
- **Rust**: `cargo test`, `cargo check`
- **Go**: `go test ./...`
- **C / C++**: `cmake --build`, `ctest`, `make test`

---

## Declarative Skills System

Lucy supports modular skills following the `SKILL.md` specification. Skills enrich the system prompt with domain-specific best practices, rules, and workflows.

### Built-in Skills (11 Production Packs)

| Skill                 | Description                                          | Triggers                                     |
| :-------------------- | :--------------------------------------------------- | :------------------------------------------- |
| `presentation-design` | Executive 16:9 widescreen PowerPoint deck generation | `ppt`, `presentation`, `slides`, `deck`      |
| `debugging`           | Systematic root-cause analysis and reproduction      | `bug`, `error`, `traceback`, `fail`          |
| `security-audit`      | OWASP Top 10, sanitization, secrets scanning         | `security`, `audit`, `vuln`, `cve`           |
| `code-review`         | Thorough peer review for style and edge cases        | `review`, `diff`, `pr`                       |
| `performance`         | Profiling, asymptotic optimization, memory leaks     | `slow`, `optimize`, `benchmark`              |
| `testing`             | Unit, integration, property testing & mock design    | `test`, `coverage`, `mock`                   |
| `refactoring`         | Martin Fowler design patterns & smell eradication    | `refactor`, `clean`, `modularize`            |
| `python`              | Idiomatic Python 3.10+, typing, asyncio, PEP 8       | `*.py`, `pyproject.toml`, `requirements.txt` |
| `typescript`          | Strict typing, TSConfig best practices, ESM          | `*.ts`, `*.tsx`, `tsconfig.json`             |
| `git-workflow`        | Atomic commits, rebase strategies, PR descriptions   | `git`, `commit`, `branch`, `merge`           |
| `api-design`          | RESTful & gRPC schema contracts, idempotency         | `api`, `endpoint`, `schema`, `rest`          |

### Skill Management

```text
/skills              # List all available skills and their activation state
/skill python        # Manually activate a skill
/skill info security # View details and prompt injections of a skill
/skill learn         # Learn new workflows from current conversation
```

---

## Model Context Protocol (MCP)

Lucy Code is both an **MCP Client** and an **MCP Server**.

### 1. Using Lucy as an MCP Client

Configure external tool servers in `~/.lucycode/mcp_servers.json` or project-local `.lucy/mcp.json`:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_..." }
    },
    "remote-sse": {
      "url": "https://mcp.internal.company.com/events",
      "transport": "sse"
    }
  }
}
```

### 2. Exposing Lucy as an MCP Server (`--serve-mcp`)

Connect Claude Desktop, Cursor, or any other editor to Lucy:

```bash
lucy --serve-mcp --mcp-transport stdio
# Or over SSE:
lucy --serve-mcp --mcp-transport sse --mcp-port 8765
```

---

## Workstation & Desktop Automation (OpenClaw Mode)

LucyCode includes a native workstation automation engine inspired by OpenClaw and OpenInterpreter. It provides direct, autonomous control over applications, browser navigation, display OCR, clipboard synchronization, and persistent multi-step workflow pipelines.

### Capabilities

- **Application Lifecycle**: Launch (`launch_app`), focus (`focus_app`), inspect (`list_apps`), and quit applications on macOS.
- **Deep macOS Control**: Run arbitrary automation scripts and UI scripting via `applescript`.
- **Visual Vision & OCR**: Inspect display geometry (`screen_info`), capture screenshots (`screenshot`), and locate UI text or buttons via OCR (`find_on_screen`).
- **Browser Automation**: Search the web, extract readable text summaries (`browser search`), navigate pages (`browser open`), and capture DOM content (`browser get_text`).
- **Browser Subagent (CDP)**: Autonomous Chrome DevTools Protocol sub-agent (`browser_subagent`) that scans the live DOM, locates buttons/links/inputs by text or selector, and dispatches deterministic mouse click events.
- **Hardware & Audio**: Speak status aloud via text-to-speech (`speak`), read/write system clipboard (`clipboard`), and send native banner notifications (`notify`).
- **Persistent Workflows**: Create, save, and execute sequential multi-step tasks across apps, bash commands, browser URLs, and delays with automated error recovery.

### Interactive Automation Control

```text
/automate workflow list                     # View saved multi-step workflows
/automate workflow create daily-dev         # Create a reusable workflow
/automate workflow add-step daily-dev open_app '{"app":"Slack"}' "Launch Slack"
/automate workflow run daily-dev            # Run the workflow
/automate apps list                         # List running applications and window counts
/automate browser search "fastapi docs"     # Web research with clean text output
/automate notify "Build Succeeded"          # Display desktop banner notification
/automate speak "All tests passing"         # Speak aloud via text-to-speech
```

---

## Executive Presentation & Slide Deck Design Engine

LucyCode incorporates an executive presentation generation engine that creates modern, high-impact, 16:9 widescreen PowerPoint (`.pptx`) decks. It avoids the boring, cluttered, wall-of-bullet-points look of legacy slide tools and instead produces modern, card-based digital product aesthetics.

### Key Capabilities

- **16:9 Widescreen Canvas**: Generates standard widescreen presentations (13.333" x 7.5" / 1280x720 pt) with generous margins and breathing room.
- **Curated Design Themes**:
  - `modern_dark`: Deep obsidian/slate background (#0F172A) with electric indigo and cyan accents. Perfect for developer tools and AI tech.
  - `clean_light`: Pure crisp white background (#FFFFFF) with subtle gray card containers and royal blue accents. Perfect for business and enterprise.
  - `executive_navy`: Deep royal navy background (#0A192F) with champagne gold and amber accents. Perfect for investor pitch decks and board reviews.
  - `warm_editorial`: Warm alabaster sand (#FDFBF7) with terracotta accents. Perfect for research briefs and narrative presentations.
  - `vibrant_tech`: High-contrast dark cyber theme (#090D16) with vivid violet and teal accents.
- **Slide Archetypes**:
  - **Hero / Title**: High-impact cover with category pill, title, subtitle, and metadata footer.
  - **Feature Cards**: 2, 3, or 4 column rounded cards with accent borders, category badges, and concise bullets.
  - **Key Metrics**: Giant 44pt+ bold numbers in accent colors with uppercase KPI labels and context.
  - **Process Pipeline**: Horizontal sequential workflow stages (01 Ingest -> 02 Execute -> 03 Verify -> 04 Deploy).
  - **Side-by-Side Comparison**: Dual-column contrast layout (e.g. Before vs After, Problem vs Solution).
  - **Editorial Quote**: Large stylized quotation marks with high-conviction quotes and speaker attribution.
  - **Summary & Roadmap**: Two-column split with checkmark takeaways on the left and action items on the right.

### Interactive Slash Commands

```text
/presentation create "AI Agent Architecture"          # Generate complete 5-slide presentation
/presentation create "Q4 Strategy" --theme clean_light # Build deck with light theme
/presentation themes                                  # List color palettes and typography
/presentation templates                               # View available slide layouts and schemas
```

### Tool Use

The LLM can invoke the `presentation` tool directly:

```json
{
  "action": "create",
  "theme": "modern_dark",
  "title": "Autonomous Workstations",
  "output_path": "workstation_overview.pptx",
  "slides": [...]
}
```

---

## LLM Evaluation & Benchmarking Harness

Lucy Code includes an autonomous agent benchmark harness (`AgentHarness`) designed to evaluate model capability, multi-turn reasoning, tool execution, and code generation reliability across real-world developer tasks.

### Features

- **Isolated Workspace Sandboxes**: Each test task executes inside a clean, isolated temporary workspace.
- **Automated Assertion Grading**: Tasks define programmatic verification functions (syntax validation, unit test execution, security regex checks) to score success objectively without human intervention.
- **Performance Metrics**: Collects step counts, token usage, execution time, and error traces.
- **Built-in Benchmark Tasks**:
  - `code_fibonacci`: Python implementation with edge cases, docstrings, and typing.
  - `bugfix_json_parser`: Debugging and fixing broken JSON parsing logic.
  - `workstation_script`: Generating multi-step desktop automation workflows.
  - `security_sanitizer`: Implementing sanitization logic against shell injection.
- **JSON Persistence & Reports**: Stores detailed benchmark records under `~/.lucycode/harness/reports/`.

### Usage

```bash
# Run all benchmark suites
lucy --harness all

# Run specific suite or task
lucy --harness coding
lucy --harness workstation_script
```

Or from inside Lucy's interactive REPL:

```text
/harness list               # List available evaluation suites and tasks
/harness run coding         # Run coding benchmark suite
/harness report             # View summary of the latest benchmark run
```

---

## Harness²: Recursive Agent Harnessing (Google Research Inspired)

Inspired by Google Research's **Harness²** framework (_Recursive Agent Harnessing for an Open World_, arXiv:2610.14224), Lucy Code implements recursive self-improvement around fixed LLM weights. Rather than fine-tuning model weights, Harness² continuously optimizes the surrounding execution harness: system prompts, domain skill heuristics, tool constraints, and error-recovery policies.

### Architecture: Two Levels of Recursion

1. **Task-Level Recursion: Propose — Probe — Compose**:
   - **Propose**: Suggests targeted modifications to harness components (e.g. prompt rules, defensive import fallbacks, error-recovery policies).
   - **Probe**: Runs candidate mutations against benchmark tasks in isolated sandboxes to measure behavioral contrasts and metrics.
   - **Compose**: Merges winning modifications that improve execution scores and reduce failure modes without requiring rigid ground-truth answer keys.
2. **Harness-Level Recursion: Continual Experience Library**:
   - Distills generalized lessons learned from successful mutations into a persistent Experience Library (`~/.lucycode/harness2/experience_library.json`).
   - Automatically injects accumulated domain experience into future prompts across coding, debugging, workstation, and security tasks.

### Usage

```bash
# Run automated recursive self-improvement cycle on coding domain
lucy --harness2 coding

# Target debugging or security
lucy --harness2 debugging
```

Or from inside Lucy's interactive REPL:

```text
/harness2 status                     # View active harness mutations and experience library
/harness2 optimize coding            # Run automated Propose-Probe-Compose cycle
/harness2 propose coding "Defensive validation" # Propose targeted rule
/harness2 probe                      # Probe latest mutation on benchmark task
/harness2 compose                    # Merge winning mutation into active harness
/harness2 library                    # View distilled lessons in Continual Experience Library
/harness2 reset                      # Revert mutations to clean baseline
```

---

## Firebase Mobile Remote Bridge & Phone Control

The Firebase Remote Bridge connects your workstation directly to your mobile phone (iOS / Android) through a lightweight, zero-dependency Firebase Realtime Database gateway. It allows you to receive instant notifications and execute workstation commands remotely from your phone.

### Architecture & Security

- **Zero External Dependencies**: Operates entirely over standard Python `urllib.request` REST calls. No heavy SDKs or Firebase admin packages needed.
- **Outbound Real-Time Alerts**: Pushes build status, test completions, goal checkpoints, and security warnings directly to your phone.
- **Inbound Command Execution**: Dispatches commands from your phone to Lucy's execution engine, capturing stdout, stderr, and execution duration.
- **Safety Sandboxing**: Remote commands are checked against strict safety filters. Dangerous commands (`rm -rf /`, `sudo`, destructive fork bombs, credential inspection) are unconditionally intercepted and rejected.
- **Standalone Mobile Web App**: Includes a ready-to-use mobile PWA interface (`lucy/services/mobile_web/firebase_app.html`) that can be opened on any mobile browser or pinned to your home screen.

### Setup & Usage

1. **Configure Firebase**:
   Set your Firebase Realtime Database URL in environment variables or via `/firebase setup`:

   ```bash
   export FIREBASE_DB_URL="https://your-project-default-rtdb.firebaseio.com"
   export FIREBASE_AUTH_SECRET="optional-database-secret"
   ```

2. **Launch Bridge**:

   ```bash
   # Start the bridge daemon from CLI
   lucy --firebase

   # Or start interactively inside Lucy
   /firebase start
   ```

3. **Interactive Commands**:

   ```text
   /firebase setup https://my-app.firebaseio.com secret123
   /firebase start                    # Start background polling and heartbeat
   /firebase status                   # Check connection and queue statistics
   /firebase alert "Build finished!"  # Push instant alert to mobile device
   /firebase poll                     # Process pending command queue once
   /firebase stop                     # Stop background listener
   ```

4. **Mobile Web Interface**:
   Open `lucy/services/mobile_web/firebase_app.html` in Chrome or Safari on your phone, enter your Database URL and workstation ID (`macbook-pro` by default), and you have a real-time terminal and alert feed on your mobile device.

---

## Mobile & Web Portal with File Upload (`--web`)

Lucy Code includes an integrated browser portal served locally over HTTP and RFC 6455 WebSockets, providing an agentic interface for mobile phones, tablets, or desktop browsers without needing an active terminal window.

### Features

- **Full Agentic Execution**: Directly prompts Lucy with access to all 40+ developer tools, slash commands, and multi-turn conversational memory.
- **Drag-and-Drop File Uploads**: Drag any source file, document, or archive directly into the browser chat window, or use the attachment button (`lucy/services/mobile_web/index.html`). Files are stored in your workspace `uploads/` directory and injected into Lucy's prompt context.
- **RFC 6455 WebSocket Bridge**: Pure-Python, zero-dependency streaming WebSocket protocol handling real-time tool execution notifications, text streaming, and automatic reconnects.
- **Interactive Companion Widget**: Features an authentic 24x24 pixel art dog companion ("Pixel") rendered directly on an HTML5 canvas with live pet, feed, bark, and sleep actions.

### Running the Web Server

```bash
# Start local web portal and WebSocket daemon on port 9847
lucy --web

# Or specify a custom port
python3 -m lucy.services.remote_server 9847
```

Navigate to `http://127.0.0.1:9847` in your browser.

---

## Pixel Art Dog Companion (`--companion`)

Lucy Code includes an authentic, retro 24-bit TrueColor pixel art companion named Pixel to keep you company while coding in the terminal or on the web.

### Features

- **Procedural Pixel Art**: 24x24 sprite engine rendered via Unicode half-blocks (`▀` / `▄`) with 24-bit TrueColor palette support.
- **Continuous Animation Loop**: Tail wagging, breathing idle cycles, blinking, and sleep animations.
- **Interactive Controls**:
  - `P` or Space: Pet Pixel (increases happiness, displays heart thought bubble).
  - `F` or `T`: Feed a bone treat.
  - `B`: Bark and deliver random developer advice and coding wisdom.
  - `S`: Toggle nap / sleep mode.
  - `Q` or Esc: Exit companion mode.

### Launching the Companion

```bash
# Standalone animated companion loop
lucy --companion

# Inside the Lucy REPL
/companion
/pet
/companion feed
/companion live
```

---

## Visual Studio Code Extension

Lucy Code includes an official VS Code extension located in `vscode_extension/` that integrates the agentic engine directly into your editor workflow.

### Features

- **Context Menu Actions**: Highlight code in any editor tab, right-click, and select:
  - **Ask Lucy Code**: Ask questions about the highlighted code.
  - **Fix with Lucy Code**: Diagnose and repair syntax, typing, or runtime errors.
  - **Refactor with Lucy Code**: Apply automated clean code transformations.
  - **Explain with Lucy Code**: Generate plain-English architectural breakdowns.
  - **Generate Tests**: Automatically scaffold unit tests for the active file.
- **Autonomous Goal Launcher**: Run `lucy.goal` from the command palette to execute multi-step goals with automated planning and test verification.
- **LSP Server Integration**: Connects via JSON-RPC over stdio to `python3 -m lucy --lsp`.

### Installing the Extension

```bash
cd vscode_extension
npm install
```

Open the directory in VS Code and press `F5` to launch an Extension Development Host.

---

## The Developer Toolbelt (40+ Tools)

| Category         | Tools                                                                                                                                                                                                             |
| :--------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Filesystem**   | `read`, `write`, `edit`, `revert_change`, `grep`, `glob`, `tree`, `binary_check`, `undo`                                                                                                                         |
| **System**       | `bash`, `powershell`, `worktree`, `task_manager`, `cron`, `sandbox`                                                                                                                                               |
| **Workstation**  | `ui_inspect`, `ui_click`, `ui_menu`, `ui_type`, `ui_verify`, `screenshot`, `find_on_screen`, `launch_app`, `focus_app`, `list_apps`, `type_text`, `key_shortcut`, `notify`, `clipboard`, `applescript`, `browser`, `browser_subagent`, `email`, `workflow`, `speak`, `screen_info`, `presentation` |
| **Intelligence** | `agent`, `team_create`, `plan`, `briefing`, `reflect`, `skill_eval`                                                                                                                                               |
| **Environment**  | `lsp`, `mcp`, `notebook`, `config`, `ask_user`                                                                                                                                                                    |
| **Exploration**  | `web_search`, `web_fetch`, `computer_use`, `sleep`                                                                                                                                                                |

---

## Slash Commands Reference

Type `/` in the interactive REPL to trigger system commands:

| Command     | Description                            | Command         | Description                              |
| :---------- | :------------------------------------- | :-------------- | :--------------------------------------- |
| `/goal`     | Autonomous goal planning & execution   | `/automate`     | Workstation & workflow automation        |
| `/skills`   | Browse and toggle agent skills         | `/sandbox`      | Manage sandbox isolation levels          |
| `/model`    | Switch model/provider on the fly       | `/plan`         | Create or view execution plan            |
| `/cost`     | Token usage & cost analytics           | `/status`       | System health & usage stats              |
| `/doctor`   | Run comprehensive system diagnostics   | `/memory`       | Semantic memory inspection               |
| `/mcp`      | Inspect & manage MCP servers           | `/revert`       | Revert / undo changes (`/revert all`)    |
| `/dream`    | Proactive background codebase indexing | `/tasks`        | View running background tasks            |
| `/sessions` | Save, list, or resume chat sessions    | `/voice`        | Toggle voice transcription               |
| `/harness`  | LLM evaluation & benchmark suite       | `/harness2`     | Harness² recursive self-improvement      |
| `/firebase` | Mobile phone remote bridge & alerts    | `/presentation` | Create executive 16:9 presentation decks |
| `/init`     | Generate a `LUCY.md` prompt for repo   | `/autonomous`   | Toggle autonomous mode (zero prompts)    |
| `/companion`| Pixel art dog companion in terminal    | `/browser`      | CDP Browser Subagent (find & click)      |

---

## CLI Flags

| Flag                       | Short | Description                                                              |
| :------------------------- | :---- | :----------------------------------------------------------------------- |
| `--model <name>`           | `-m`  | Model specifier (`gemini`, `openai:gpt-4o`, `deepseek:r1`, `ollama:...`) |
| `--prompt <text>`          | `-p`  | Execute a single prompt non-interactively and exit                       |
| `--goal <text>`            | `-g`  | Run a goal with automated planning, verification, and correction         |
| `--sandbox`                |       | Enable sandbox filesystem containment and safety checks                  |
| `--sandbox-mode <mode>`    |       | Isolation level: `workspace`, `strict`, or `read_only`                   |
| `--permission-mode <mode>` |       | Tool permission policy: `prompt`, `auto_accept`, or `read_only`          |
| `--autonomous`, `--auto`   | `-y`  | Run in autonomous mode (zero mid-task questions or human prompts)        |
| `--companion`              |       | Launch interactive pixel art dog companion in the terminal               |
| `--web`, `--remote`        |       | Start mobile web portal & WebSocket server on http://127.0.0.1:9847     |
| `--harness [suite]`        |       | Run LLM evaluation benchmarks (`all`, `coding`, `reasoning`)             |
| `--harness2 [domain]`      |       | Run Harness² recursive self-improvement cycle (`coding`, `debugging`)    |
| `--firebase`               |       | Start Firebase mobile remote bridge daemon                               |
| `--serve-mcp`              |       | Run Lucy as an MCP server for external IDEs                              |
| `--verbose`                | `-v`  | Enable detailed debug logs                                               |

---

## Running Tests

Lucy Code is covered by an extensive test suite:

```bash
# Run all core tests
pytest tests/

# Test specific modules
pytest tests/test_sandbox.py
pytest tests/test_goal_engine.py
pytest tests/test_providers.py
pytest tests/test_skills.py
pytest tests/test_browser_subagent.py
pytest tests/test_remote_server.py
pytest tests/test_companion.py
pytest tests/test_enhanced_mcp_amplifiers.py
```

---

## Project Architecture

```
lucycode/
├── frontend/            # React Ink terminal UI frontend (Node / TypeScript)
├── lucy/
│   ├── api/             # Universal LLM providers & streaming clients
│   │   ├── client.py
│   │   ├── models.py
│   │   └── providers/   # Gemini, OpenAI, DeepSeek, Groq, Mistral, Ollama, etc.
│   ├── commands/        # Slash command handlers (/goal, /skills, /companion, /harness)
│   ├── core/            # Agentic orchestration & intelligence
│   │   ├── goal_engine.py      # Goal decomposition & auto-correction
│   │   ├── sandbox.py          # Filesystem containment & credential guardrails
│   │   ├── skills_engine.py    # Declarative SKILL.md loader & context triggers
│   │   ├── verification.py     # Multi-language test/lint runners
│   │   ├── parallel_tools.py   # Concurrency engine for read tools
│   │   ├── learning.py         # SQLite memory from user corrections
│   │   ├── context_engine.py   # Token compression & diff summarization
│   │   ├── harness.py          # LLM evaluation & benchmarking engine
│   │   └── recursive_harness.py # Harness² recursive agent self-improvement
│   ├── services/        # MCP server/client, CDP browser agent, remote WebSocket server
│   │   ├── cdp_client.py       # Pure-Python RFC 6455 CDP browser automation
│   │   ├── browser_subagent.py # Autonomous DOM element locator and clicker
│   │   ├── remote_server.py    # RFC 6455 WebSocket & HTTP bridge daemon
│   │   ├── firebase_bridge.py  # Mobile remote phone bridge gateway
│   │   └── mobile_web/
│   │       ├── index.html      # Mobile web app with companion & file upload
│   │       └── firebase_app.html
│   ├── skills/          # Built-in SKILL.md definition packs
│   ├── tui/             # Terminal UI renderer & Pixel companion sprite engine
│   │   └── companion.py # 24-bit TrueColor pixel art companion
│   └── tools/           # Filesystem, bash, web, workstation, and AST tools
├── native/              # C extensions for high-speed file search and diffing
├── tests/               # Comprehensive test suites (111 passing tests)
└── vscode_extension/    # Official Visual Studio Code extension (LSP & actions)
```

---

## Disclaimer

Lucy Code is an AI-powered developer tool driven by Large Language Models. While Lucy includes automated verification suites, self-correction heuristics, and sandbox containment, **AI models can make mistakes, hallucinate APIs, misinterpret instructions, or generate unintended code and commands**.

- Always review generated code, file modifications, and terminal commands before running them.
- Exercise heightened vigilance when running in autonomous modes (`--autonomous`, `--auto`, `-y`, `/autonomous`) or with sandbox protections disabled.
- Do not execute unverified commands or allow destructive file operations in production or mission-critical environments without human oversight.
- The authors and contributors assume no liability for any data loss, service disruptions, or damages resulting from the use of this tool.

---

<p align="center">
  <b>Lucy Code</b> — Built with ❤️ for the future of autonomous software and engineering.
</p>
