# Lucy Code — The Autonomous AI Coding Companion & Agentic Engine

<p align="center">
  <b>Reimagined in Python + C for the Next-Generation Agentic Era</b><br>
  <i>Lightning fast. Deeply integrated. Truly autonomous. Safer with Sandbox Isolation.</i>
</p>

---

Lucy Code is an autonomous, goal-driven AI coding assistant built from the ground up for speed, reliability, security, and universal model connectivity. Whether you are connected to Google Gemini, OpenAI, DeepSeek, Groq, Anthropic, or running completely offline with Ollama or local GGUF weights, Lucy provides an uncompromising agentic experience that plans, writes, verifies, self-corrects, and executes inside a protected sandbox.

---

## Key Highlights

*   **Native Performance**: Core orchestration in **Python 3.10+** with native **C extensions** for blazingly fast regex search, AST diffing, and file traversal.
*   **Universal LLM Engine (15+ Providers)**:
    *   Native streaming integration with **Gemini (2.5/3.x with thought signature support)**, **OpenAI (GPT-4o, o1, o3-mini)**, **DeepSeek (V3, R1)**, **Groq**, **Mistral**, **Anthropic Claude**, **OpenRouter**, **Together AI**, **Fireworks**, **Ollama**, and **llama.cpp**.
    *   Zero-dependency streaming fallback using Python's standard library `urllib` when third-party libraries aren't installed.
*   **Goal-Driven Autonomous Engine**:
    *   High-level goal decomposition and dynamic replanning.
    *   Multi-language automated self-verification (`pytest`, `jest`, `cargo test`, `go test`, `mypy`, `tsc`, `ruff`).
    *   Iterative self-correction with error-directed prompt feedback (up to 3 retries).
    *   Crash-resilient checkpoints saved in `~/.lucycode/goals/` for pause, resume, and audit.
*   **Sandbox Mode & Workspace Protection**:
    *   **Filesystem Confinement**: Strict boundary checks restricting file writes to your workspace root and `/tmp/`.
    *   **Credential Protection**: Guardrails blocking unauthorized read/write access to sensitive files (`~/.ssh`, `~/.aws`, `~/.gnupg`, keychains, `.env`, `*.pem`, `*.key`).
    *   **Command Safety Checks**: Proactive interception of destructive shell operations (`rm -rf /`, `mkfs`, fork bombs, `sudo`).
*   **Declarative Skills System**:
    *   Open `SKILL.md` format compatible with modern agent standards.
    *   **10 Built-in Production Skills**: `debugging`, `security-audit`, `code-review`, `performance`, `testing`, `refactoring`, `python`, `typescript`, `git-workflow`, and `api-design`.
    *   Context-aware auto-activation based on file extensions, project root indicators, and prompt keywords.
*   **Enhanced MCP (Client + Server + SSE)**:
    *   Model Context Protocol client supporting `stdio`, `sse`, and `streamable-http` transports with OAuth2 auth.
    *   **Lucy as an MCP Server** (`--serve-mcp`): Expose Lucy's tools and intelligence to Claude Desktop, Cursor, Zed, and any MCP-compliant client.
*   **Intelligence Amplifiers**:
    *   **Parallel Tool Execution**: Concurrently execute non-conflicting read tools (`read`, `grep`, `glob`, `tree`) to drastically cut round-trip latency.
    *   **Learning from Corrections**: Automatically captures user feedback and correction patterns in a persistent SQLite knowledge store.
    *   **Speculative Pre-fetching**: Analyzes imports in touched files to warm context before you even ask.
    *   **Diff-Aware Context Compaction**: Preserves vital conversation history while compressing long token streams.

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

| Mode | Writes Permitted | Sensitive Paths | Command Safety |
| :--- | :--- | :--- | :--- |
| **`workspace`** *(Default)* | Workspace root & `/tmp/` | Protected (Blocked) | Block dangerous commands |
| **`strict`** | Workspace root only | Protected (Blocked) | Strict allowlist execution |
| **`read_only`** | No writes anywhere | Protected (Blocked) | Read-only commands only |

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
*   **Python**: `pytest`, `unittest`, `mypy`, `ruff`, `flake8`
*   **JavaScript / TypeScript**: `jest`, `vitest`, `npm test`, `tsc --noEmit`
*   **Rust**: `cargo test`, `cargo check`
*   **Go**: `go test ./...`
*   **C / C++**: `cmake --build`, `ctest`, `make test`

---

## Declarative Skills System

Lucy supports modular skills following the `SKILL.md` specification. Skills enrich the system prompt with domain-specific best practices, rules, and workflows.

### Built-in Skills (10 Production Packs)

| Skill | Description | Triggers |
| :--- | :--- | :--- |
| `debugging` | Systematic root-cause analysis and reproduction | `bug`, `error`, `traceback`, `fail` |
| `security-audit` | OWASP Top 10, sanitization, secrets scanning | `security`, `audit`, `vuln`, `cve` |
| `code-review` | Thorough peer review for style and edge cases | `review`, `diff`, `pr` |
| `performance` | Profiling, asymptotic optimization, memory leaks | `slow`, `optimize`, `benchmark` |
| `testing` | Unit, integration, property testing & mock design | `test`, `coverage`, `mock` |
| `refactoring` | Martin Fowler design patterns & smell eradication | `refactor`, `clean`, `modularize` |
| `python` | Idiomatic Python 3.10+, typing, asyncio, PEP 8 | `*.py`, `pyproject.toml`, `requirements.txt` |
| `typescript` | Strict typing, TSConfig best practices, ESM | `*.ts`, `*.tsx`, `tsconfig.json` |
| `git-workflow` | Atomic commits, rebase strategies, PR descriptions | `git`, `commit`, `branch`, `merge` |
| `api-design` | RESTful & gRPC schema contracts, idempotency | `api`, `endpoint`, `schema`, `rest` |

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

*   **Application Lifecycle**: Launch (`launch_app`), focus (`focus_app`), inspect (`list_apps`), and quit applications on macOS.
*   **Deep macOS Control**: Run arbitrary automation scripts and UI scripting via `applescript`.
*   **Visual Vision & OCR**: Inspect display geometry (`screen_info`), capture screenshots (`screenshot`), and locate UI text or buttons via OCR (`find_on_screen`).
*   **Browser Automation**: Search the web, extract readable text summaries (`browser search`), navigate pages (`browser open`), and capture DOM content (`browser get_text`).
*   **Hardware & Audio**: Speak status aloud via text-to-speech (`speak`), read/write system clipboard (`clipboard`), and send native banner notifications (`notify`).
*   **Persistent Workflows**: Create, save, and execute sequential multi-step tasks across apps, bash commands, browser URLs, and delays with automated error recovery.

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

## The Developer Toolbelt (40+ Tools)

| Category | Tools |
| :--- | :--- |
| **Filesystem** | `read`, `write`, `edit`, `grep`, `glob`, `tree`, `binary_check`, `undo` |
| **System** | `bash`, `powershell`, `worktree`, `task_manager`, `cron`, `sandbox` |
| **Workstation** | `screenshot`, `find_on_screen`, `launch_app`, `focus_app`, `list_apps`, `notify`, `clipboard`, `applescript`, `browser`, `workflow`, `speak`, `screen_info` |
| **Intelligence** | `agent`, `team_create`, `plan`, `briefing`, `reflect`, `skill_eval` |
| **Environment** | `lsp`, `mcp`, `notebook`, `config`, `ask_user` |
| **Exploration** | `web_search`, `web_fetch`, `computer_use`, `sleep` |

---

## Slash Commands Reference

Type `/` in the interactive REPL to trigger system commands:

| Command | Description | Command | Description |
| :--- | :--- | :--- | :--- |
| `/goal` | Autonomous goal planning & execution | `/automate` | Workstation & workflow automation |
| `/skills` | Browse and toggle agent skills | `/sandbox` | Manage sandbox isolation levels |
| `/model` | Switch model/provider on the fly | `/plan` | Create or view execution plan |
| `/cost` | Token usage & cost analytics | `/status` | System health & usage stats |
| `/doctor` | Run comprehensive system diagnostics | `/memory` | Semantic memory inspection |
| `/mcp` | Inspect & manage MCP servers | `/undo` | Revert last file modification |
| `/dream` | Proactive background codebase indexing | `/tasks` | View running background tasks |
| `/sessions` | Save, list, or resume chat sessions | `/voice` | Toggle voice transcription |
| `/init` | Generate a `LUCY.md` prompt for repo | | |

---

## CLI Flags

| Flag | Short | Description |
| :--- | :--- | :--- |
| `--model <name>` | `-m` | Model specifier (`gemini`, `openai:gpt-4o`, `deepseek:r1`, `ollama:...`) |
| `--prompt <text>` | `-p` | Execute a single prompt non-interactively and exit |
| `--goal <text>` | `-g` | Run a goal with automated planning, verification, and correction |
| `--sandbox` | | Enable sandbox filesystem containment and safety checks |
| `--sandbox-mode <mode>` | | Isolation level: `workspace`, `strict`, or `read_only` |
| `--permission-mode <mode>`| | Tool permission policy: `prompt`, `auto_accept`, or `read_only` |
| `--serve-mcp` | | Run Lucy as an MCP server for external IDEs |
| `--verbose` | `-v` | Enable detailed debug logs |

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
pytest tests/test_enhanced_mcp_amplifiers.py
```

---

## Project Architecture

```
lucycode/
├── lucy/
│   ├── api/             # Universal LLM providers & streaming clients
│   │   ├── client.py
│   │   ├── models.py
│   │   └── providers/   # Gemini, OpenAI, DeepSeek, Groq, Mistral, Ollama, etc.
│   ├── commands/        # Slash command handlers (/goal, /sandbox, /skills, etc.)
│   ├── core/            # Agentic orchestration & intelligence
│   │   ├── goal_engine.py      # Goal decomposition & auto-correction
│   │   ├── sandbox.py          # Filesystem containment & credential guardrails
│   │   ├── skills_engine.py    # Declarative SKILL.md loader & context triggers
│   │   ├── verification.py     # Multi-language test/lint runners
│   │   ├── parallel_tools.py   # Concurrency engine for read tools
│   │   ├── learning.py         # SQLite memory from user corrections
│   │   └── context_engine.py   # Token compression & diff summarization
│   ├── services/        # MCP server/client implementations
│   ├── skills/          # Built-in SKILL.md definition packs
│   └── tools/           # Filesystem, bash, web, and AST inspection tools
├── native/              # C extensions for high-speed file search and diffing
└── tests/               # Pytest suite
```

---

<p align="center">
  <b>Lucy Code</b> — Built for the future of autonomous software engineering.
</p>
