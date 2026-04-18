"""
Main CLI entrypoint — the REPL loop and --print mode.

This ties everything together: config, tools, context, API, UI,
MCP servers, hooks, plugins, and session persistence.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import uuid
from typing import Any

import click

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML

from lucy import __version__


def _register_tools():
    """Register all built-in tools."""
    from lucy.core.tool import register_tool

    # Core tools
    from lucy.tools.bash_tool import BashTool
    from lucy.tools.file_read_tool import FileReadTool
    from lucy.tools.file_write_tool import FileWriteTool
    from lucy.tools.file_edit_tool import FileEditTool
    from lucy.tools.grep_tool import GrepTool
    from lucy.tools.glob_tool import GlobTool
    from lucy.tools.web_search_tool import WebSearchTool
    from lucy.tools.agent_tool import AgentTool

    # New Phase 1 tools
    from lucy.tools.ask_user_tool import AskUserQuestionTool
    from lucy.tools.brief_tool import BriefTool
    from lucy.tools.config_tool import ConfigTool
    from lucy.tools.plan_mode_tools import EnterPlanModeTool, ExitPlanModeTool
    from lucy.tools.worktree_tools import EnterWorktreeTool, ExitWorktreeTool
    from lucy.tools.lsp_tool import LSPTool
    from lucy.tools.mcp_tools import MCPTool, McpAuthTool, ListMcpResourcesTool, ReadMcpResourceTool
    from lucy.tools.notebook_edit_tool import NotebookEditTool
    from lucy.tools.powershell_tool import PowerShellTool
    from lucy.tools.sleep_tool import SleepTool
    from lucy.tools.task_tools import (
        TaskCreateTool, TaskGetTool, TaskListTool,
        TaskStopTool, TaskUpdateTool, TaskOutputTool,
    )
    from lucy.tools.todo_write_tool import TodoWriteTool
    from lucy.tools.tool_search_tool import ToolSearchTool
    from lucy.tools.web_fetch_tool import WebFetchTool
    from lucy.tools.team_tools import TeamCreateTool, TeamDeleteTool, SendMessageTool
    from lucy.tools.cron_tool import CronCreateTool, CronDeleteTool, CronListTool
    from lucy.tools.computer_use_tool import ComputerUseTool

    # Register core tools
    register_tool(BashTool())
    register_tool(FileReadTool())
    register_tool(FileWriteTool())
    register_tool(FileEditTool())
    register_tool(GrepTool())
    register_tool(GlobTool())
    register_tool(WebSearchTool())
    register_tool(AgentTool())
    register_tool(ComputerUseTool())

    # Register new tools
    register_tool(AskUserQuestionTool())
    register_tool(BriefTool())
    register_tool(ConfigTool())
    register_tool(EnterPlanModeTool())
    register_tool(ExitPlanModeTool())
    register_tool(EnterWorktreeTool())
    register_tool(ExitWorktreeTool())
    register_tool(LSPTool())
    register_tool(MCPTool())
    register_tool(McpAuthTool())
    register_tool(ListMcpResourcesTool())
    register_tool(ReadMcpResourceTool())
    register_tool(NotebookEditTool())
    register_tool(PowerShellTool())
    register_tool(SleepTool())
    register_tool(TaskCreateTool())
    register_tool(TaskGetTool())
    register_tool(TaskListTool())
    register_tool(TaskStopTool())
    register_tool(TaskUpdateTool())
    register_tool(TaskOutputTool())
    register_tool(TodoWriteTool())
    register_tool(ToolSearchTool())
    register_tool(WebFetchTool())
    register_tool(TeamCreateTool())
    register_tool(TeamDeleteTool())
    register_tool(SendMessageTool())
    register_tool(CronCreateTool())
    register_tool(CronDeleteTool())
    register_tool(CronListTool())


async def _initialize_mcp():
    """Initialize MCP server connections."""
    from lucy.services.mcp import get_mcp_manager
    from lucy.core.tool import register_tool

    manager = get_mcp_manager()
    await manager.connect_from_config()

    # Register MCP tools with the global tool registry
    for tool in manager.get_tools():
        register_tool(tool)


def _load_hooks():
    """Load hooks from config."""
    from lucy.core.hooks import load_hooks_from_config
    load_hooks_from_config()


def _initialize_plugins():
    """Initialize plugin system."""
    from lucy.core.plugins import get_plugin_manager
    manager = get_plugin_manager()
    manager.initialize()


async def _run_repl(
    model: str | None,
    verbose: bool,
    permission_mode: str | None,
    resume_session: str | None,
    is_coordinator: bool = False,
    is_assistant: bool = False,
) -> None:
    """Run the interactive REPL."""
    from rich.live import Live
    from rich.status import Status
    from rich.spinner import Spinner
    from rich.text import Text

    from lucy.api.client import stream_query
    from lucy.api.models import calculate_cost, resolve_model, is_offline_model
    from lucy.core.commands import find_command, parse_command_input
    from lucy.core.config import get_config
    from lucy.core.context import build_system_prompt, get_lucymd_content, get_git_status
    from lucy.core.message import (
        AssistantMessage,
        StreamEvent,
        UserMessage,
        create_user_message,
        messages_to_api_params,
    )
    from lucy.core.query import QueryParams, query_loop
    from lucy.core.state import AppState
    from lucy.core.tool import ToolContext, get_tool_registry
    from lucy.tui.renderer import (
        create_console,
        render_assistant_message,
        render_error,
        render_info,
        render_separator,
        render_streaming_text,
        render_success,
        render_tool_result,
        render_welcome,
    )
    from lucy.tui.theme import get_theme
    from lucy.utils.session import save_message, save_metadata, load_session, list_sessions
    from lucy.core.hooks import run_hooks_for_event, HookEvent, HookInput, get_hook_registry

    from lucy.shell.vim import get_vim_manager

    config = get_config()
    console = create_console()
    theme = get_theme(config.theme)
    resolved_model = resolve_model(model or config.model)

    # Initialize MCP servers
    await _initialize_mcp()

    # Initialize state
    session_id = resume_session or str(uuid.uuid4())
    state = AppState(
        model=resolved_model,
        conversation_id=session_id,
        permission_mode=permission_mode or config.permission_mode,
    )

    # Resume session if requested
    if resume_session:
        resumed_msgs, session_info = load_session(resume_session)
        if resumed_msgs:
            state.messages = resumed_msgs
            render_info(console, f"Resumed session: {session_info.title or resume_session}")
            render_info(console, f"  {len(resumed_msgs)} messages loaded")
        else:
            render_error(console, f"Session not found: {resume_session}")

    # Build context
    git_status = await get_git_status(state.cwd)
    lucymd = get_lucymd_content(state.cwd)
    system_prompt = build_system_prompt(
        cwd=state.cwd,
        git_status=git_status,
        lucymd=lucymd,
        is_coordinator=is_coordinator,
        is_assistant=is_assistant,
    )

    # Fire SessionStart hook
    hook_input = HookInput(
        session_id=session_id,
        cwd=state.cwd,
        hook_event=HookEvent.SESSION_START.value,
    )
    await run_hooks_for_event(HookEvent.SESSION_START, hook_input)

    # Tool context
    tool_context = ToolContext(
        cwd=state.cwd,
        permission_mode=state.permission_mode,
        is_interactive=True,
        ask_permission=lambda name, desc: _ask_permission(console, name, desc, theme),
    )

    # Welcome
    render_welcome(console, resolved_model, theme)

    # Abort event for cancellation
    abort_event = asyncio.Event()

    # Set up prompt session
    vim_manager = get_vim_manager(theme)
    session = PromptSession(
        key_bindings=vim_manager.get_key_bindings(),
        bottom_toolbar=lambda: vim_manager.get_bottom_toolbar(session.app.vi_state)
    )

    # REPL loop
    status = None
    status_active = False
    while True:
        try:
            # Update editing mode before each prompt
            session.app.editing_mode = vim_manager.get_editing_mode()
            
            # Use basic ansi prompt string
            prompt_str = HTML(f'<style fg="ansiblue">&gt;</style> ')
            
            try:
                # Need to use patch_stdout if we want to print while prompting, 
                # but for standard REPL we can just await
                user_input = await session.prompt_async(prompt_str)
            except EOFError:
                console.print()
                break
            except KeyboardInterrupt:
                console.print()
                continue

            user_input = user_input.strip()
            if not user_input:
                continue

            # Check for commands
            cmd_parsed = parse_command_input(user_input)
            if cmd_parsed:
                cmd_name, cmd_args = cmd_parsed
                cmd = find_command(cmd_name)
                if cmd:
                    result = await cmd.execute(cmd_args, state)
                    if result.clear_screen:
                        console.clear()
                    if result.output:
                        console.print(result.output)
                    if result.error:
                        render_error(console, result.error)
                    if result.should_exit:
                        break
                    continue
                else:
                    render_error(console, f"Unknown command: /{cmd_name}. Type /help for commands.")
                    continue

            # Fire UserPromptSubmit hook
            hook_input = HookInput(
                session_id=session_id,
                cwd=state.cwd,
                hook_event=HookEvent.USER_PROMPT_SUBMIT.value,
                user_prompt=user_input,
            )
            hook_results = await run_hooks_for_event(HookEvent.USER_PROMPT_SUBMIT, hook_input)
            if hook_results and not hook_results[0].continue_execution:
                render_info(console, f"Blocked by hook: {hook_results[0].reason or 'unknown'}")
                continue

            # Add user message
            user_msg = create_user_message(user_input)
            state.messages.append(user_msg)

            # Save to session
            save_message(session_id, user_msg)

            # Reset abort
            abort_event.clear()

            # Query
            registry = get_tool_registry()
            params = QueryParams(
                messages=list(state.messages),
                system_prompt=system_prompt,
                tools=registry,
                tool_context=tool_context,
                model=state.model,
                max_tokens=params.max_tokens if 'params' in locals() and params.max_tokens else None,
                max_turns=10 if is_offline_model(state.model) else 50,
                thinking_enabled=config.thinking_enabled,
                abort_event=abort_event,
            )

            console.print()
            streaming_text = ""

            status_msg = "[dim]Thinking...[/dim]"
            if is_offline_model(state.model):
                status_msg = "[dim]Thinking (Local model may take 5-10s to load)...[/dim]"
            
            status = Status(status_msg, console=console, spinner="dots")
            status_active = False
            try:
                async for event in query_loop(params):
                    from lucy.core.message import RequestStartEvent
                    if isinstance(event, RequestStartEvent):
                        status.start()
                        status_active = True
                        continue
                        
                    if isinstance(event, StreamEvent):
                        if event.type == "text_delta":
                            if status_active:
                                status.stop()
                                status_active = False
                            text = event.data.get("text", "")
                            streaming_text += text
                            render_streaming_text(console, text)
                        elif event.type == "thinking_delta":
                            pass  # Accumulating; rendered after
                        elif event.type == "tool_use_start":
                            if streaming_text:
                                console.print()  # End streaming line
                                streaming_text = ""
                            name = event.data.get("name", "")
                            console.print(
                                f"\n[{theme.tool_name}]⚡ {name}[/{theme.tool_name}]",
                                end="",
                            )
                        elif event.type == "tool_use_complete":
                            inp = event.data.get("input", {})
                            name = event.data.get("name", "")
                            summary = _tool_summary(name, inp)
                            console.print(f" [{theme.dim}]{summary}[/{theme.dim}]")

                    elif isinstance(event, AssistantMessage):
                        if status_active:
                            status.stop()
                            status_active = False
                        if streaming_text:
                            console.print()  # End streaming line
                            streaming_text = ""
                        else:
                            # If no text was streamed (e.g. error or empty response), render it now
                            render_assistant_message(console, event, theme=theme, verbose=verbose)

                        # Explicitly render error if it's an API error message
                        if event.api_error:
                            render_error(console, event.api_error, theme=theme)

                        # Record
                        state.messages.append(event)
                        save_message(session_id, event)
                        if event.usage:
                            cost = calculate_cost(
                                state.model,
                                event.usage.input_tokens,
                                event.usage.output_tokens,
                                event.usage.cache_creation_input_tokens,
                                event.usage.cache_read_input_tokens,
                            )
                            state.cost.add_usage(event.usage, cost)

                        # Show thinking if verbose
                        if verbose:
                            thinking = event.get_thinking_text()
                            if thinking:
                                from rich.panel import Panel
                                console.print(
                                    Panel(
                                        thinking,
                                        title="[dim]Thinking[/dim]",
                                        border_style=theme.dim,
                                    )
                                )

                    elif isinstance(event, UserMessage):
                        # Tool result
                        state.messages.append(event)
                        content = event.get_text()
                        if content and verbose:
                            is_err = False
                            if isinstance(event.content, list):
                                from lucy.core.message import ToolResultBlock
                                for b in event.content:
                                    if isinstance(b, ToolResultBlock) and b.is_error:
                                        is_err = True
                            render_tool_result(console, "Result", content, is_error=is_err, theme=theme)

            except KeyboardInterrupt:
                abort_event.set()
                console.print(f"\n[{theme.warning}]⚠ Interrupted[/{theme.warning}]")
                continue

            # Cost footer
            if config.show_cost:
                console.print(
                    f"\n[{theme.dim}]Cost: {state.cost.format_cost()} "
                    f"| {state.cost.format_tokens()}[/{theme.dim}]"
                )
            console.print()

            # Update session metadata
            first_prompt = ""
            for m in state.messages:
                if isinstance(m, UserMessage):
                    first_prompt = m.get_text()[:80]
                    break
            save_metadata(
                session_id=session_id,
                title=first_prompt or "Untitled session",
                model=state.model,
                cwd=state.cwd,
                total_cost=state.cost.total_cost,
            )

        except KeyboardInterrupt:
            console.print()
            continue
        except Exception as e:
            render_error(console, f"Unexpected error: {e}")
            if verbose:
                import traceback
                console.print_exception()

        finally:
            if status_active:
                status.stop()
                status_active = False

    # Print session exit cost track
    from lucy.utils.cost import get_session_tracker
    tracker = get_session_tracker()
    if tracker.total_cost > 0 or tracker.input_tokens > 0:
        console.print(f"\n[dim]{tracker.format_total()}[/dim]\n")


async def _run_worker(spec_path: str, out_path: str) -> None:
    """Run in headless worker mode (for teammate spawning)."""
    import json
    from lucy.core.orchestrator import _run_single_agent, AgentSpec
    
    try:
        with open(spec_path, 'r') as f:
            spec_data = json.load(f)
        
        # Deserialize spec
        spec = AgentSpec(**spec_data)
        
        # Register tools
        _register_tools()
        _initialize_plugins()
        
        # Execute agent
        result = await _run_single_agent(spec, os.getcwd(), permission_mode="auto_accept")
        
        # Serialize and write result
        result_data = {
            "agent_name": result.agent_name,
            "role": result.role.value if hasattr(result.role, 'value') else result.role,
            "task": result.task,
            "output": result.output,
            "turn_count": result.turn_count,
            "elapsed_seconds": result.elapsed_seconds,
            "success": result.success,
            "error": result.error,
        }
        
        with open(out_path, 'w') as f:
            json.dump(result_data, f, indent=2)
            
    except Exception as e:
        # Write error result if possible
        try:
            with open(out_path, 'w') as f:
                json.dump({"success": False, "error": str(e)}, f)
        except:
            pass
        print(f"Worker failed: {e}")
        sys.exit(1)


async def _run_print(
    prompt: str,
    model: str | None,
    verbose: bool,
    ndjson: bool = False,
    is_coordinator: bool = False,
    is_assistant: bool = False,
) -> None:
    """Run in non-interactive (--print) mode."""
    from lucy.api.models import resolve_model
    from lucy.core.config import get_config
    from lucy.core.context import build_system_prompt, get_lucymd_content, get_git_status
    from lucy.core.message import AssistantMessage, StreamEvent, UserMessage, create_user_message
    from lucy.core.query import QueryParams, query_loop
    from lucy.core.state import AppState
    from lucy.core.tool import ToolContext, get_tool_registry
    from lucy.tui.renderer import create_console

    config = get_config()
    console = create_console()
    resolved_model = resolve_model(model or config.model)

    state = AppState(model=resolved_model, is_non_interactive=True)

    git_status = await get_git_status(state.cwd)
    lucymd = get_lucymd_content(state.cwd)
    system_prompt = build_system_prompt(
        cwd=state.cwd,
        git_status=git_status,
        lucymd=lucymd,
        is_coordinator=is_coordinator,
        is_assistant=is_assistant,
    )

    tool_context = ToolContext(
        cwd=state.cwd,
        permission_mode="auto_accept",
        is_interactive=False,
    )

    user_msg = create_user_message(prompt)
    state.messages.append(user_msg)

    registry = get_tool_registry()
    params = QueryParams(
        messages=list(state.messages),
        system_prompt=system_prompt,
        tools=registry,
        tool_context=tool_context,
        model=resolved_model,
        thinking_enabled=config.thinking_enabled,
    )

    if ndjson:
        from lucy.api.ndjson_emitter import NDJSONEmitter
        # Suppress arbitrary stdout print statements so json is clean
        import sys
        
        async for event in query_loop(params):
            if isinstance(event, StreamEvent):
                if event.type == "text_delta":
                    NDJSONEmitter.emit_text_delta(event.data.get("text", ""))
                elif event.type == "tool_use_start":
                    NDJSONEmitter.emit_tool_start(event.data.get("name", ""))
            elif isinstance(event, AssistantMessage):
                state.messages.append(event)
                NDJSONEmitter.emit_message("assistant", event.get_text())
                if event.has_tools:
                    for b in event.content:
                        if hasattr(b, "type") and getattr(b, "type") == "tool_use":
                            NDJSONEmitter.emit_tool_complete(b.name, getattr(b, "input", {}))
            elif isinstance(event, UserMessage):
                state.messages.append(event)
                # This could be a tool result or normal user message
                NDJSONEmitter.emit_message("user", event.get_text())
    else:
        async for event in query_loop(params):
            if isinstance(event, StreamEvent):
                if event.type == "text_delta":
                    print(event.data.get("text", ""), end="", flush=True)
            elif isinstance(event, AssistantMessage):
                state.messages.append(event)
            elif isinstance(event, UserMessage):
                state.messages.append(event)
        print()  # Final newline


def _ask_permission(console, tool_name: str, description: str, theme) -> bool:
    """Ask the user for tool permission."""
    console.print(
        f"\n[{theme.warning}]⚠ Permission required[/{theme.warning}]: "
        f"[{theme.tool_name}]{tool_name}[/{theme.tool_name}] — {description}"
    )
    try:
        response = input("  Allow? [y/N] ").strip().lower()
        return response in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def _tool_summary(name: str, inp: dict) -> str:
    """One-line summary of tool input for the spinner."""
    if name in ("Bash",):
        cmd = inp.get("command", "")
        return cmd[:80] if cmd else ""
    if name in ("Read", "FileRead"):
        return inp.get("file_path", "")
    if name in ("Write", "FileWrite"):
        return inp.get("file_path", "")
    if name in ("Edit", "FileEdit"):
        return inp.get("file_path", "")
    if name in ("Grep", "GrepTool"):
        return f"'{inp.get('pattern', '')}'"
    if name in ("Glob", "GlobTool"):
        return inp.get("pattern", "")
    if name in ("WebSearch", "Search"):
        return inp.get("query", "")[:60]
    if name in ("Agent", "SubAgent"):
        return inp.get("task", "")[:60]
    return ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option("-p", "--prompt", "--print", "prompt", default=None, help="Run non-interactively with a prompt")
@click.option("-m", "--model", default=None, help="Model to use (e.g. sonnet, opus, haiku)")
@click.option("-v", "--verbose", is_flag=True, help="Show verbose output (thinking, tool results)")
@click.option("--version", is_flag=True, help="Show version")
@click.option("--permission-mode", default=None, type=click.Choice(["default", "auto_accept", "plan"]))
@click.option("--resume", default=None, help="Resume a previous session by ID")
@click.option("--list-sessions", "list_sessions_flag", is_flag=True, help="List recent sessions")
@click.option("--ndjson", is_flag=True, help="Emit output as NDJSON lines (IPC only)")
@click.option("--coordinator", is_flag=True, help="Launch in generic Coordinator Metaprompt mode")
@click.option("--assistant", is_flag=True, help="Launch in Kairos Assistant Metaprompt mode")
@click.option("--worker-spec", default=None, help="Headless worker spec (JSON path)")
@click.option("--worker-out", default=None, help="Headless worker output (JSON path)")
@click.argument("initial_prompt", nargs=-1, required=False)
def cli(
    prompt: str | None,
    model: str | None,
    verbose: bool,
    version: bool,
    permission_mode: str | None,
    resume: str | None,
    list_sessions_flag: bool,
    ndjson: bool,
    coordinator: bool,
    assistant: bool,
    worker_spec: str | None,
    worker_out: str | None,
    initial_prompt: tuple[str, ...],
):
    """Lucy Code — AI-powered coding assistant in your terminal."""
    if version:
        click.echo(f"Lucy Code v{__version__}")
        return

    if list_sessions_flag:
        from lucy.utils.session import list_sessions
        sessions = list_sessions(limit=20)
        if not sessions:
            click.echo("No sessions found.")
            return
        click.echo(f"\n{'ID':<38} {'Title':<40} {'Messages':>8}")
        click.echo("─" * 90)
        for s in sessions:
            title = (s.title or s.first_prompt or "Untitled")[:40]
            click.echo(f"{s.session_id:<38} {title:<40} {s.message_count:>8}")
        click.echo()
        return

    # Register tools and load Phase 2 systems
    _register_tools()
    _load_hooks()
    _initialize_plugins()

    # Determine mode
    if worker_spec and worker_out:
        asyncio.run(_run_worker(worker_spec, worker_out))
    elif prompt is not None:
        asyncio.run(_run_print(prompt=prompt, model=model, verbose=verbose, ndjson=ndjson, is_coordinator=coordinator, is_assistant=assistant))
    elif initial_prompt:
        # Joined positional args as prompt for print mode
        asyncio.run(_run_print(prompt=" ".join(initial_prompt), model=model, verbose=verbose, ndjson=ndjson, is_coordinator=coordinator, is_assistant=assistant))
    else:
        asyncio.run(_run_repl(
            model=model,
            verbose=verbose,
            permission_mode=permission_mode or "default",
            resume_session=resume,
            is_coordinator=coordinator,
            is_assistant=assistant,
        ))


if __name__ == "__main__":
    cli()
