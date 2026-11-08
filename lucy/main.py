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
    from lucy.tools.revert_tool import RevertTool
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
    register_tool(RevertTool())
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

    # Workstation & Desktop Automation Tools
    try:
        from lucy.tools.workstation_tools import WORKSTATION_TOOLS
        for wt in WORKSTATION_TOOLS:
            register_tool(wt)
    except Exception as e:
        logger.debug("Workstation tools registration skipped: %s", e)


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
    parallel_tools: bool = True,
    sandbox: bool = False,
    sandbox_mode: str | None = None,
    autonomous: bool = False,
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
    is_auto = autonomous or config.autonomous or (permission_mode in ("auto_accept", "autonomous"))
    effective_permission_mode = "auto_accept" if is_auto else (permission_mode or config.permission_mode)
    session_id = resume_session or str(uuid.uuid4())
    state = AppState(
        model=resolved_model,
        conversation_id=session_id,
        permission_mode=effective_permission_mode,
        autonomous=is_auto,
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
        is_autonomous=is_auto,
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
        autonomous=is_auto,
        is_interactive=not is_auto,
        ask_permission=lambda name, desc: _ask_permission(console, name, desc, theme),
    )

    # Initialize sandbox if enabled
    from lucy.core.sandbox import get_sandbox_manager
    sandbox_mgr = get_sandbox_manager()
    if sandbox or config.sandbox:
        prof = sandbox_mode or config.sandbox_mode or "workspace"
        sandbox_mgr.enable(prof)
        tool_context.sandbox = sandbox_mgr

    # Welcome
    render_welcome(console, resolved_model, theme)
    if is_auto:
        render_info(console, "⚡ Autonomous Mode: ACTIVE (zero mid-task confirmations or prompts)")
    if sandbox_mgr.is_enabled:
        render_info(console, f"🔒 Sandbox Active: {sandbox_mgr.config.profile.value.upper()} profile (filesystem constrained to workspace)")

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

            # Check for corrections and record procedural learning
            try:
                from lucy.core.learning import get_learning_engine
                learning = get_learning_engine()
                prev_assistant = next((m for m in reversed(state.messages) if isinstance(m, AssistantMessage)), None)
                if prev_assistant and learning.detect_correction(user_input, prev_assistant.get_text()):
                    corr = learning.extract_rule(user_input, prev_assistant.get_text(), state.cwd)
                    learning.record_correction(corr)
                    if verbose:
                        render_info(console, f"🧠 Learned correction: {corr.learned_rule}")
            except Exception as e:
                logger.debug("Learning engine error: %s", e)

            # Add user message
            user_msg = create_user_message(user_input)
            state.messages.append(user_msg)

            # Save to session
            save_message(session_id, user_msg)

            # Reset abort
            abort_event.clear()

            # Synchronize autonomous mode
            current_auto = getattr(state, "autonomous", False) or getattr(tool_context, "autonomous", False) or state.permission_mode in ("auto_accept", "autonomous")
            state.autonomous = current_auto
            tool_context.autonomous = current_auto
            if current_auto:
                tool_context.permission_mode = "auto_accept"
                tool_context.is_interactive = False
            else:
                tool_context.permission_mode = state.permission_mode
                tool_context.is_interactive = True

            # Query
            system_prompt = build_system_prompt(
                cwd=state.cwd,
                git_status=git_status,
                lucymd=lucymd,
                is_coordinator=is_coordinator,
                is_assistant=is_assistant,
                user_prompt=user_input,
                is_autonomous=current_auto,
            )
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
                parallel_tools=parallel_tools,
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
    parallel_tools: bool = True,
    sandbox: bool = False,
    sandbox_mode: str | None = None,
    autonomous: bool = False,
    permission_mode: str | None = None,
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

    is_auto = autonomous or config.autonomous or (permission_mode in ("auto_accept", "autonomous"))
    effective_permission_mode = "auto_accept" if is_auto else (permission_mode or "auto_accept")
    state = AppState(
        model=resolved_model,
        is_non_interactive=True,
        autonomous=is_auto,
        permission_mode=effective_permission_mode,
    )

    git_status = await get_git_status(state.cwd)
    lucymd = get_lucymd_content(state.cwd)
    system_prompt = build_system_prompt(
        cwd=state.cwd,
        git_status=git_status,
        lucymd=lucymd,
        is_coordinator=is_coordinator,
        is_assistant=is_assistant,
        user_prompt=prompt,
        is_autonomous=is_auto,
    )

    tool_context = ToolContext(
        cwd=state.cwd,
        permission_mode=effective_permission_mode,
        autonomous=is_auto,
        is_interactive=False if is_auto else (sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False),
    )

    from lucy.core.sandbox import get_sandbox_manager
    sandbox_mgr = get_sandbox_manager()
    if sandbox or config.sandbox:
        prof = sandbox_mode or config.sandbox_mode or "workspace"
        sandbox_mgr.enable(prof)
        tool_context.sandbox = sandbox_mgr

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
        parallel_tools=parallel_tools,
    )

    if ndjson:
        from lucy.api.ndjson_emitter import NDJSONEmitter
        # Suppress arbitrary stdout print statements so json is clean
        
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
        text_printed = False
        async for event in query_loop(params):
            if isinstance(event, StreamEvent):
                if event.type == "text_delta":
                    print(event.data.get("text", ""), end="", flush=True)
                    text_printed = True
                elif event.type == "tool_use_start":
                    tname = event.data.get("name", "")
                    print(f"\n[Tool: {tname}]", flush=True)
            elif isinstance(event, AssistantMessage):
                state.messages.append(event)
                msg_text = event.get_text()
                if msg_text and not text_printed:
                    print(msg_text, flush=True)
                    text_printed = True
                elif event.api_error and not text_printed:
                    print(f"Error: {event.api_error}", flush=True)
                    text_printed = True
            elif isinstance(event, UserMessage):
                state.messages.append(event)
        print()  # Final newline


async def _run_goal(
    goal_text: str | None,
    resume_goal_id: str | None = None,
    model: str | None = None,
    verbose: bool = False,
    permission_mode: str | None = None,
    ndjson: bool = False,
    sandbox: bool = False,
    sandbox_mode: str | None = None,
) -> None:
    """Run in autonomous goal-driven mode."""
    from rich.panel import Panel

    from lucy.api.models import resolve_model
    from lucy.core.config import get_config
    from lucy.core.goal_engine import GoalConfig, GoalEngine, GoalStatus
    from lucy.core.sandbox import get_sandbox_manager
    from lucy.core.tool import ToolContext, get_tool_registry
    from lucy.tui.renderer import create_console, render_error
    from lucy.tui.theme import get_theme

    config = get_config()
    console = create_console()
    theme = get_theme()
    resolved_model = resolve_model(model or config.model)

    goal_config = GoalConfig(auto_verify=True)
    engine = GoalEngine(config=goal_config)
    tool_context = ToolContext(
        cwd=os.getcwd(),
        permission_mode=permission_mode or "auto_accept",
        autonomous=True,
        is_interactive=False,
    )

    sandbox_mgr = get_sandbox_manager()
    if sandbox or config.sandbox:
        prof = sandbox_mode or config.sandbox_mode or "workspace"
        sandbox_mgr.enable(prof)
        tool_context.sandbox = sandbox_mgr
    tools = get_tool_registry()

    if not ndjson:
        target_display = goal_text or f"Resume Goal: {resume_goal_id}"
        console.print(
            Panel(
                f"[bold cyan]🎯 Goal-Driven Autonomous Engine[/bold cyan]\n\n"
                f"[bold white]{target_display}[/bold white]\n\n"
                f"[{theme.dim}]Model: {resolved_model} | Auto-Verification: ON | Crash-Recovery: ON[/{theme.dim}]\n\n"
                f"[{theme.warning}]Notice:[/{theme.warning}] [{theme.dim}]Lucy is an AI and can make mistakes. Always review generated code and executions.[/{theme.dim}]",
                border_style="cyan",
            )
        )

    generator = None
    if resume_goal_id:
        generator = engine.resume(
            goal_id=resume_goal_id,
            context=tool_context,
            model=resolved_model,
            tools=tools,
        )
    elif goal_text:
        generator = engine.execute(
            goal_text=goal_text,
            context=tool_context,
            model=resolved_model,
            tools=tools,
        )
    else:
        render_error(console, "Error: No goal description or goal ID provided.")
        return

    try:
        async for event in generator:
            if ndjson:
                print(event.to_ndjson(), flush=True)
                continue

            etype = event.type
            data = event.data

            if etype == "planning":
                est = data.get("estimated_steps", 0)
                if est > 0:
                    console.print(f"[{theme.accent}]📋 Plan formulated:[/{theme.accent}] {est} steps required.")
                else:
                    console.print(f"[{theme.accent}]📋 Decomposing goal and analyzing project...[/{theme.accent}]")

            elif etype == "step_start":
                sid = data.get("step_id", 0)
                desc = data.get("description", "")
                done = data.get("steps_done", 0)
                total = data.get("steps_total", 0)
                console.print(f"\n[{theme.tool_name}]▶ Step {sid}/{total}:[/{theme.tool_name}] [bold]{desc}[/bold]")

            elif etype == "step_complete":
                sid = data.get("step_id", 0)
                console.print(f"[{theme.success}]✓ Step {sid} finished.[/{theme.success}]")

            elif etype == "step_failed":
                sid = data.get("step_id", 0)
                err = data.get("error", "")
                console.print(f"[{theme.error}]✗ Step {sid} failed:[/{theme.error}] {err}")

            elif etype == "verifying":
                strat = data.get("strategy", "all")
                console.print(f"[{theme.dim}]🔍 Running self-verification ({strat})...[/{theme.dim}]")

            elif etype == "verification_result":
                passed = data.get("passed", False)
                results_list = data.get("results", [])
                if passed:
                    console.print(f"[{theme.success}]✓ Self-verification passed ({len(results_list)} checks ok)[/{theme.success}]")
                else:
                    console.print(f"[{theme.warning}]⚠ Self-verification flagged issues:[/{theme.warning}]")
                    for r in results_list:
                        if not r.get("passed", False):
                            strat = r.get("strategy", "")
                            cmd = r.get("command", "")
                            errs = r.get("errors", [])
                            first_err = errs[0] if errs else "check failed"
                            console.print(f"  • [{theme.error}]{strat.upper()}[/{theme.error}] `{cmd}`: {first_err[:100]}")

            elif etype == "correcting":
                sid = data.get("step_id", 0)
                att = data.get("attempt", 1)
                max_att = data.get("max_attempts", 3)
                console.print(f"[{theme.warning}]🛠️ Self-correcting step {sid} (attempt {att}/{max_att})...[/{theme.warning}]")

            elif etype == "replanning":
                reason = data.get("reason", "")
                console.print(f"[{theme.accent}]🔄 Dynamic replanning:[/{theme.accent}] {reason}")

            elif etype == "progress":
                done = data.get("steps_done", 0)
                total = data.get("steps_total", 0)
                pct = data.get("percent", 0.0)
                tokens = data.get("tokens_used", 0)
                eta = data.get("eta_seconds", 0.0)
                console.print(
                    f"[{theme.dim}]Progress: {done}/{total} ({pct:.0f}%) | "
                    f"Tokens: {tokens:,} | ETA: {int(eta)}s[/{theme.dim}]"
                )

            elif etype == "checkpoint":
                path = data.get("checkpoint_path", "")
                console.print(f"[{theme.dim}]💾 Checkpoint saved: {path}[/{theme.dim}]")

            elif etype == "completed":
                summary = data.get("summary", "")
                files = data.get("files_modified", [])
                panel_content = f"[bold green]Goal Succeeded![/bold green]\n\n{summary}"
                if files:
                    panel_content += f"\n\n[bold]Files Modified/Created ({len(files)}):[/bold]\n"
                    panel_content += "\n".join(f"  • {f}" for f in files)
                console.print(Panel(panel_content, border_style="green", title="Execution Summary"))

            elif etype == "failed":
                err = data.get("error", "")
                progress_info = data.get("partial_progress", "")
                console.print(
                    Panel(
                        f"[bold red]Goal Execution Failed[/bold red]\n\n"
                        f"[bold]Error:[/bold] {err}\n"
                        f"[bold]Progress:[/bold] {progress_info}\n\n"
                        f"[dim]Checkpoint saved. You can inspect or resume later with /goal resume.[/dim]",
                        border_style="red",
                        title="Goal Failed",
                    )
                )

            elif etype == "paused":
                gid = data.get("goal_id", "")
                cp_path = data.get("checkpoint_path", "")
                console.print(
                    Panel(
                        f"[bold yellow]Goal Paused[/bold yellow]\n\n"
                        f"Goal ID: {gid}\n"
                        f"Checkpoint saved: {cp_path}\n\n"
                        f"Resume with: [bold]lucy --resume-goal {gid}[/bold] or [bold]/goal resume {gid}[/bold]",
                        border_style="yellow",
                        title="Paused",
                    )
                )

    except (KeyboardInterrupt, asyncio.CancelledError):
        cp = await engine.pause()
        if not ndjson:
            console.print(
                f"\n[{theme.warning}]⚠ Goal execution paused by user.[/{theme.warning}]"
            )
            if cp:
                console.print(
                    f"[{theme.dim}]Checkpoint saved to ~/.lucycode/goals/{cp.goal_id}.json\n"
                    f"Resume anytime with: lucy --resume-goal {cp.goal_id}[/{theme.dim}]"
                )


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
@click.option("-y", "--yes", "--auto", "--autonomous", "autonomous", is_flag=True, default=False, help="Run in autonomous mode (never ask user questions or confirmations mid-task)")
@click.option("--permission-mode", default=None, type=click.Choice(["default", "auto_accept", "plan", "autonomous"]))
@click.option("--resume", default=None, help="Resume a previous session by ID")
@click.option("--list-sessions", "list_sessions_flag", is_flag=True, help="List recent sessions")
@click.option("--ndjson", is_flag=True, help="Emit output as NDJSON lines (IPC only)")
@click.option("--coordinator", is_flag=True, help="Launch in generic Coordinator Metaprompt mode")
@click.option("--assistant", is_flag=True, help="Launch in Kairos Assistant Metaprompt mode")
@click.option("--worker-spec", default=None, help="Headless worker spec (JSON path)")
@click.option("--worker-out", default=None, help="Headless worker output (JSON path)")
@click.option("--goal", default=None, help="Run in autonomous goal execution mode")
@click.option("--resume-goal", default=None, help="Resume an autonomous goal execution by ID")
@click.option("--serve-mcp", is_flag=True, help="Start Lucy as an MCP server")
@click.option("--parallel-tools/--no-parallel-tools", default=True, help="Enable parallel tool execution (default: on)")
@click.option("--sandbox", is_flag=True, default=False, help="Enable filesystem & command sandbox mode")
@click.option("--sandbox-mode", default=None, type=click.Choice(["workspace", "strict", "read_only"]), help="Sandbox isolation profile (workspace, strict, read_only)")
@click.option("--harness", default=None, help="Run LLM evaluation benchmark suite (all, coding, debugging, security, workstation)")
@click.option("--harness2", default=None, help="Run Harness² recursive self-improvement cycle on target domain (e.g. coding, debugging)")
@click.option("--firebase", is_flag=True, default=False, help="Enable background Firebase mobile bridge for phone alerts & remote commands")
@click.option("--companion", is_flag=True, default=False, help="Launch interactive pixel art dog companion in the terminal")
@click.option("--web", "--remote", "web_server", is_flag=True, default=False, help="Start Lucy mobile web & WebSocket server on http://127.0.0.1:9847")
@click.argument("initial_prompt", nargs=-1, required=False)
def cli(
    prompt: str | None,
    model: str | None,
    verbose: bool,
    version: bool,
    autonomous: bool,
    permission_mode: str | None,
    resume: str | None,
    list_sessions_flag: bool,
    ndjson: bool,
    coordinator: bool,
    assistant: bool,
    worker_spec: str | None,
    worker_out: str | None,
    goal: str | None,
    resume_goal: str | None,
    serve_mcp: bool,
    parallel_tools: bool,
    sandbox: bool,
    sandbox_mode: str | None,
    harness: str | None,
    harness2: str | None,
    firebase: bool,
    companion: bool,
    web_server: bool,
    initial_prompt: tuple[str, ...],
):
    """Lucy Code — AI-powered coding assistant in your terminal."""
    if version:
        click.echo(f"Lucy Code v{__version__}")
        return

    # Normalize autonomous mode
    if autonomous or permission_mode == "autonomous":
        autonomous = True
        permission_mode = "auto_accept"

    # Pixel Art Dog Companion mode
    if companion or (initial_prompt and len(initial_prompt) == 1 and initial_prompt[0] in ("companion", "pet", "dog")):
        from lucy.tui.companion import DogCompanion
        comp = DogCompanion(name="Pixel")
        comp.run_interactive()
        return

    # Mobile Web & WebSocket Server mode
    if web_server or (initial_prompt and len(initial_prompt) == 1 and initial_prompt[0] in ("web", "serve-web")):
        import webbrowser
        from lucy.services.remote_server import run_remote_server
        click.echo("⚡ Starting Lucy Mobile Web & WebSocket Server...")
        click.echo("   • Web App:   http://127.0.0.1:9847")
        click.echo("   • WebSocket: ws://127.0.0.1:9847")
        try:
            webbrowser.open("http://127.0.0.1:9847")
        except Exception:
            pass
        try:
            asyncio.run(run_remote_server(host="127.0.0.1", port=9847))
        except KeyboardInterrupt:
            click.echo("\nServer stopped.")
        return

    if serve_mcp:
        from lucy.services.mcp import MCPServerHost
        host = MCPServerHost()
        asyncio.run(host.start(transport="stdio"))
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

    # Optional Firebase Mobile Bridge startup
    if firebase:
        from lucy.services.firebase_bridge import get_firebase_bridge
        fb = get_firebase_bridge()
        if fb.config.database_url:
            asyncio.run(fb.start_listener())
            click.echo(f"Firebase mobile bridge active on workstation: {fb.config.workstation_id}")
        else:
            click.echo("Firebase not configured. Run '/firebase setup <url>' first.")

    # LLM Evaluation Harness mode
    if harness:
        from lucy.core.harness import get_harness
        h = get_harness()
        click.echo(f"Starting LLM Evaluation Harness (suite: {harness})...")
        report = asyncio.run(h.run_suite(suite_name=harness, model=model))
        click.echo(report.summary_table())
        return

    # Harness²: Recursive Agent Self-Improvement mode
    if harness2:
        from lucy.core.recursive_harness import get_harness2
        h2 = get_harness2()
        click.echo(f"Starting Harness² Recursive Self-Improvement cycle (domain: {harness2})...")
        mut, rep, ok = asyncio.run(h2.run_recursive_cycle(target_name=harness2))
        res_str = "SUCCESS (Composed & Distilled)" if ok else "REJECTED (No improvement)"
        click.echo(f"Outcome: {res_str} | Score Delta: {rep.score_delta:+.2f}")
        click.echo(f"Behavioral Contrast: {rep.behavioral_contrast}")
        return

    # Determine mode
    if worker_spec and worker_out:
        asyncio.run(_run_worker(worker_spec, worker_out))
    elif goal or resume_goal:
        asyncio.run(_run_goal(
            goal_text=goal,
            resume_goal_id=resume_goal,
            model=model,
            verbose=verbose,
            permission_mode=permission_mode or "auto_accept",
            ndjson=ndjson,
            sandbox=sandbox,
            sandbox_mode=sandbox_mode,
        ))
    elif prompt is not None:
        asyncio.run(_run_print(
            prompt=prompt,
            model=model,
            verbose=verbose,
            ndjson=ndjson,
            is_coordinator=coordinator,
            is_assistant=assistant,
            parallel_tools=parallel_tools,
            sandbox=sandbox,
            sandbox_mode=sandbox_mode,
            autonomous=autonomous,
            permission_mode=permission_mode,
        ))
    elif initial_prompt:
        # Joined positional args as prompt for print mode
        asyncio.run(_run_print(
            prompt=" ".join(initial_prompt),
            model=model,
            verbose=verbose,
            ndjson=ndjson,
            is_coordinator=coordinator,
            is_assistant=assistant,
            parallel_tools=parallel_tools,
            sandbox=sandbox,
            sandbox_mode=sandbox_mode,
            autonomous=autonomous,
            permission_mode=permission_mode,
        ))
    else:
        asyncio.run(_run_repl(
            model=model,
            verbose=verbose,
            permission_mode=permission_mode or "default",
            resume_session=resume,
            is_coordinator=coordinator,
            is_assistant=assistant,
            parallel_tools=parallel_tools,
            sandbox=sandbox,
            sandbox_mode=sandbox_mode,
            autonomous=autonomous,
        ))


if __name__ == "__main__":
    cli()
