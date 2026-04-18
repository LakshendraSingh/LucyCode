# 🪐 Lucy Code — The High-Performance AI Coding Companion

<p align="center">
  <b>Reimagined in Python + C for the Next-Generation Agentic Era</b><br>
  <i>Lightning fast. Deeply integrated. Truly autonomous.</i>
</p>

---

Lucy Code is a full-featured AI-powered coding assistant, built from the ground up for speed, reliability, and local-first execution. Whether you're connected to the cloud or working entirely offline, Lucy provides a seamless, agentic experience that handles everything from trivial fixes to complex architectural refactors.

## 🚀 Key Highlights

*   **⚡ Native Performance**: Core logic implemented in **Python 3.12** with performance-critical extensions in **C** for search, diffing, and I/O.
*   **🤖 Multi-Agent Meta-Modes**: 
    *   **Coordinator Mode**: Orchestrates entire teams of workers for parallel research and implementation.
    *   **Kairos Mode**: A passive, high-speed desktop companion for rapid-fire questions and context exploration.
*   **🏠 Offline Excellence**: First-class support for **Ollama**, **vLLM**, **llama.cpp**, and direct **weights loading** (.gguf, .safetensors) with zero setup.
*   **🛠️ Expanded Toolset**: Over **26 built-in tools** covering Filesystem, Web, System, LSP, and Multi-Agent patterns.
*   **🖥️ Universal Access**: Native TUI, VS Code Extension, and a mobile-responsive web interface accessible via QR code.

---

## 🏗️ Intelligence & Orchestration

Lucy Code isn't just a chatbot; it's a reasoning engine designed for the agentic loop.

### 🧠 Agentic Loop
- **Reasoning Chains**: ReAct-style `thought` → `action` → `observation` loops ensure high-fidelity tool usage.
- **Self-Critique**: Automatic reflection agents score generated code and iterate until quality hits a defined threshold.
- **Decomposition**: Complex goals are automatically broken down into a hierarchical plan with sub-goal tracking.

### 👥 Orchestration Modes
- **Coordinator**: Launch multiple async "workers" to research disparate parts of a codebase simultaneously.
- **Tungsten Panels**: Native teammate spawning—Lucy can spawn new terminal tabs (or tmux panes) to run parallel sub-tasks while you keep working.
- **KAIROS Daemon**: Background indexing and file watching for instant search and proactive suggestions.

---

## 🛠️ The Ultimate Developer Toolbelt (26+ Tools)

Lucy has direct access to your machine (with your permission) via a rich library of tools:

| Category | Tools |
| :--- | :--- |
| **Filesystem** | `read`, `write`, `edit`, `grep`, `glob`, `tree`, `binary_check`, `undo` |
| **System** | `bash`, `powershell`, `worktree`, `task_manager`, `cron` |
| **Intelligence** | `agent`, `team_create`, `plan`, `briefing`, `reflect` |
| **Environment** | `lsp`, `mcp`, `notebook`, `config`, `ask_user` |
| **Explore** | `web_search`, `web_fetch`, `computer_use`, `sleep` |

---

## 🕹️ Slash Commands (24 Built-in)

Type `/` in the REPL to access powerful system controls:

| Command | Description | Command | Description |
| :--- | :--- | :--- | :--- |
| `/plan` | Create/view execution plan | `/doctor` | Run system diagnostics |
| `/status` | System health & usage | `/undo` | Revert last file change |
| `/cost` | Token usage & cost stats | `/memory` | Semantic memory search |
| `/model` | Switch model on the fly | `/tasks`| Manage background tasks |
| `/dream` | Autonomous code analysis | `/voice` | Toggle voice mode |
| `/mcp` | MCP server status | `/plugins`| Manage extensions |
| `/sessions`| Save/Load conversations | `/qr` | Mobile pairing |

---

## 📦 Quick Start

### ☁️ Cloud (Anthropic/OpenAI)
```bash
# Requires ANTHROPIC_API_KEY
pip install -e ".[cloud]"
lucy
```

### 🏠 Offline (Local & Free)
Lucy automatically detects running local servers.
```bash
# 1. Start Ollama (https://ollama.ai)
# 2. Install Lucy
pip install -e ".[offline]"
# 3. Run — no API key required!
lucy --model ollama:llama3.1
```

### 🗄️ Direct Weights (Zero Server Setup)
Run Lucy directly against GGUF or .safetensors files.
```bash
lucy --model weights:/path/to/llama-3-8b.gguf
```

---

## 📊 Repository Metrics

| Component | Files | Lines of Code | Description |
| :--- | :--: | :--: | :--- |
| **Python** | 148 | 22,281 | Core Orchestration, Tools, TUI |
| **C Extensions** | 4 | 500 | High-performance Search & Diff |
| **Frontend/Web** | 2 | 601 | Mobile Web Interface & JS Bindings |
| **Total** | **154** | **23,382** | |

---

## 📁 Project Structure

*   **/lucy**: Core Python logic divided into `core/`, `api/`, `tools/`, and `services/`.
*   **/native**: C sources for performance-critical logic.
*   **/vscode_extension**: Source for the VS Code marketplace integration.
*   **/tests**: Comprehensive 40+ case test suite.
*   **LUCY.md**: Your project's "System Prompt" extension (initialized via `/init`).

---

<p align="center">
  Built with ❤️ for the future of coding.
</p>
