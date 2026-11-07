"""
Slash command suite for Firebase Mobile Remote Gateway (/firebase, /remote).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from lucy.core.commands import Command, CommandResult, register_command
from lucy.services.firebase_bridge import get_firebase_bridge


class FirebaseCommand(Command):
    """Command suite for managing mobile alerts and remote workstation command execution via Firebase."""

    name = "firebase"
    description = "Manage Firebase mobile bridge (receive phone alerts & dispatch remote commands)"
    aliases = ["mobile", "remote_phone"]

    async def execute(self, args_str: str, state: Any) -> CommandResult:
        parts = args_str.strip().split(maxsplit=1) if args_str else []
        sub = parts[0].lower() if parts else "status"
        arg = parts[1].strip() if len(parts) > 1 else ""

        bridge = get_firebase_bridge()

        if sub in ("help", "--help", "-h"):
            help_text = """
Firebase Mobile Gateway Commands (/firebase)
--------------------------------------------
  /firebase setup <db_url> [token]      Configure Firebase Realtime Database URL
  /firebase start                       Start background listener for phone commands
  /firebase stop                        Stop background command listener
  /firebase status                      Show current connection & workstation ID
  /firebase alert <title> | <message>   Send a push notification alert to phone
  /firebase poll                        Check and execute pending phone commands
  /firebase connect                     Print direct mobile web URL for your phone
"""
            return CommandResult(output=help_text.strip())

        elif sub == "setup":
            tokens = arg.split(maxsplit=1)
            if not tokens:
                return CommandResult(error="Usage: /firebase setup <database_url> [auth_token]")
            url = tokens[0]
            token = tokens[1] if len(tokens) > 1 else ""
            bridge.configure(database_url=url, auth_token=token)
            return CommandResult(
                output=f"Configured Firebase Database:\nURL: {bridge.config.database_url}\nWorkstation ID: {bridge.config.workstation_id}"
            )

        elif sub == "status":
            cfg = bridge.config
            st = "Configured & Active" if cfg.database_url else "Not configured (run /firebase setup <url>)"
            listener_st = "Running" if bridge._running else "Stopped (run /firebase start)"
            out = [
                f"Firebase Gateway Status: {st}",
                f"Workstation ID:          {cfg.workstation_id}",
                f"Database URL:            {cfg.database_url or '(none)'}",
                f"Background Listener:     {listener_st}",
            ]
            return CommandResult(output="\n".join(out))

        elif sub == "start":
            if not bridge.config.database_url:
                return CommandResult(error="Configure database first: /firebase setup <url>")
            await bridge.start_listener()
            bridge.send_alert(
                title="Workstation Online",
                message=f"LucyCode is connected and listening on {bridge.config.workstation_id}",
                alert_type="success",
            )
            return CommandResult(output=f"Firebase bridge listener started for workstation '{bridge.config.workstation_id}'.")

        elif sub == "stop":
            await bridge.stop_listener()
            return CommandResult(output="Firebase bridge listener stopped.")

        elif sub == "alert":
            if not bridge.config.database_url:
                return CommandResult(error="Configure database first: /firebase setup <url>")
            if "|" in arg:
                title, msg = arg.split("|", 1)
            else:
                title, msg = "Alert from LucyCode", arg
            ok = bridge.send_alert(title.strip(), msg.strip(), alert_type="info")
            return CommandResult(output=f"Alert dispatched to mobile: {title.strip()}") if ok else CommandResult(error="Failed to send alert to Firebase.")

        elif sub == "poll":
            pending = bridge.poll_commands()
            if not pending:
                return CommandResult(output="No pending commands from mobile device.")
            out = [f"Found {len(pending)} pending command(s):"]
            for cmd in pending:
                res = await bridge.execute_command(cmd)
                out.append(f"  [{cmd.id}] {cmd.command} -> {res[:100]}")
            return CommandResult(output="\n".join(out))

        elif sub == "connect":
            cfg = bridge.config
            db_enc = cfg.database_url
            ws_enc = cfg.workstation_id
            connect_url = f"https://lucycode.dev/remote?db={db_enc}&ws={ws_enc}"
            out = [
                "Connect Your Phone to Workstation:",
                "=" * 40,
                f"Workstation ID: {cfg.workstation_id}",
                f"Database URL:   {cfg.database_url}",
                "",
                "Open the mobile web dashboard on your phone browser:",
                f"  {connect_url}",
                "",
                "Or open local client:",
                f"  file://{os.path.abspath('lucy/services/mobile_web/firebase_app.html')}?db={db_enc}&ws={ws_enc}",
            ]
            return CommandResult(output="\n".join(out))

        return CommandResult(error=f"Unknown sub-command: '{sub}'. Run '/firebase help'.")


def get_commands() -> list[Command]:
    return [FirebaseCommand()]


def register():
    register_command(FirebaseCommand())
