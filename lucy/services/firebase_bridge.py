"""
Firebase Remote Bridge for LucyCode.

Provides bidirectional mobile workstation control and live alerting via Firebase Realtime Database REST API.
Enables receiving build/goal alerts on your phone and dispatching terminal & automation commands remotely.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import socket
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class FirebaseConfig:
    """Firebase Realtime Database connection settings."""
    database_url: str  # e.g. "https://my-app-default-rtdb.firebaseio.com"
    auth_token: str = ""  # Firebase database secret or ID token (optional for open rules)
    workstation_id: str = field(default_factory=lambda: socket.gethostname().replace(".", "_"))
    poll_interval: float = 2.0
    enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FirebaseConfig:
        return cls(
            database_url=data.get("database_url", ""),
            auth_token=data.get("auth_token", ""),
            workstation_id=data.get("workstation_id", socket.gethostname().replace(".", "_")),
            poll_interval=float(data.get("poll_interval", 2.0)),
            enabled=bool(data.get("enabled", False)),
        )


@dataclass
class RemoteAlert:
    """Alert message pushed to mobile phone."""
    id: str
    title: str
    message: str
    alert_type: str = "info"  # info, success, warning, error, goal
    timestamp: float = field(default_factory=time.time)
    screenshot_b64: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RemoteCommand:
    """Command received from mobile device."""
    id: str
    command: str
    source: str = "phone"
    timestamp: float = field(default_factory=time.time)
    status: str = "pending"  # pending, running, completed, failed
    result_output: str | None = None
    exit_code: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FirebaseBridgeService:
    """Manages Firebase REST communication for mobile push alerts and inbound command execution."""

    def __init__(self, config_file: Path | None = None) -> None:
        self.config_file = config_file or (Path.home() / ".lucycode" / "firebase.json")
        self.config = self._load_config()
        self._running = False
        self._listener_task: asyncio.Task | None = None
        self._processed_command_ids: set[str] = set()

    def _load_config(self) -> FirebaseConfig:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return FirebaseConfig.from_dict(json.load(f))
            except Exception as e:
                logger.error("Failed loading Firebase config: %s", e)
        return FirebaseConfig(database_url="")

    def save_config(self, config: FirebaseConfig) -> None:
        self.config = config
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config.to_dict(), f, indent=2)
        except (PermissionError, OSError):
            tmp_cfg = Path("/tmp/lucy_firebase.json")
            with open(tmp_cfg, "w", encoding="utf-8") as f:
                json.dump(config.to_dict(), f, indent=2)
            self.config_file = tmp_cfg

    def configure(self, database_url: str, auth_token: str = "", workstation_id: str | None = None) -> None:
        """Update and enable Firebase connection parameters."""
        clean_url = database_url.rstrip("/")
        if not clean_url.startswith("https://"):
            clean_url = f"https://{clean_url}"
        cfg = FirebaseConfig(
            database_url=clean_url,
            auth_token=auth_token,
            workstation_id=workstation_id or self.config.workstation_id,
            enabled=True,
        )
        self.save_config(cfg)

    # ------------------------------------------------------------------
    # REST API Helpers
    # ------------------------------------------------------------------

    def _build_url(self, path: str) -> str:
        clean_path = path.lstrip("/")
        base = f"{self.config.database_url}/{clean_path}"
        if not base.endswith(".json"):
            base += ".json"
        if self.config.auth_token:
            base += f"?auth={urllib.parse.quote(self.config.auth_token)}"
        return base

    def _http_request(self, method: str, path: str, data: Any = None) -> tuple[bool, Any]:
        if not self.config.database_url:
            return False, "Firebase database URL is not configured."
        url = self._build_url(path)
        payload = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "LucyCode-Workstation/1.0"},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                return True, json.loads(body) if body.strip() else {}
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------
    # Outbound Alerts (Workstation -> Phone)
    # ------------------------------------------------------------------

    def send_alert(
        self,
        title: str,
        message: str,
        alert_type: str = "info",
        include_screenshot: bool = False,
    ) -> bool:
        """Post a notification alert to Firebase for the mobile phone to display."""
        if not self.config.database_url:
            return False

        scr = None
        if include_screenshot:
            try:
                from lucy.services.screen_automation import get_screen_automation
                scr = get_screen_automation().screenshot()
            except Exception:
                pass

        alert_id = f"alert_{int(time.time()*1000)}"
        alert = RemoteAlert(
            id=alert_id,
            title=title,
            message=message,
            alert_type=alert_type,
            screenshot_b64=scr,
        )
        path = f"workstations/{self.config.workstation_id}/alerts/{alert_id}"
        ok, _ = self._http_request("PUT", path, alert.to_dict())
        return ok

    def update_status(self, active_task: str = "Idle", active_model: str = "gemini") -> bool:
        """Publish workstation heartbeat and state to Firebase."""
        if not self.config.database_url:
            return False

        status_payload = {
            "online": True,
            "last_seen": time.time(),
            "hostname": socket.gethostname(),
            "os": f"{platform.system()} {platform.release()}",
            "active_model": active_model,
            "active_task": active_task,
        }
        path = f"workstations/{self.config.workstation_id}/status"
        ok, _ = self._http_request("PUT", path, status_payload)
        return ok

    # ------------------------------------------------------------------
    # Inbound Command Processing (Phone -> Workstation)
    # ------------------------------------------------------------------

    def poll_commands(self) -> list[RemoteCommand]:
        """Fetch pending commands queued by the mobile phone."""
        if not self.config.database_url:
            return []

        path = f"workstations/{self.config.workstation_id}/commands"
        ok, data = self._http_request("GET", path)
        if not ok or not isinstance(data, dict):
            return []

        pending: list[RemoteCommand] = []
        for cid, payload in data.items():
            if not isinstance(payload, dict):
                continue
            if payload.get("status") == "pending" and cid not in self._processed_command_ids:
                cmd = RemoteCommand(
                    id=cid,
                    command=payload.get("command", ""),
                    source=payload.get("source", "phone"),
                    timestamp=payload.get("timestamp", time.time()),
                    status="pending",
                )
                pending.append(cmd)

        return pending

    async def execute_command(self, cmd: RemoteCommand) -> str:
        """Execute a phone-dispatched command securely on the workstation."""
        raw = cmd.command.strip()
        cmd.status = "running"
        path = f"workstations/{self.config.workstation_id}/commands/{cmd.id}"
        self._http_request("PATCH", path, {"status": "running"})
        self._processed_command_ids.add(cmd.id)

        output = ""
        exit_code = 0

        try:
            # 1. Check for slash commands
            if raw.startswith("/"):
                from lucy.core.commands import find_command
                parts = raw[1:].split(maxsplit=1)
                cmd_name = parts[0]
                args = parts[1] if len(parts) > 1 else ""
                handler = find_command(cmd_name)
                if handler:
                    res = await handler.execute(args, None)
                    output = res.output or res.error or "Command executed."
                    exit_code = 1 if res.error else 0
                else:
                    output = f"Unknown command: /{cmd_name}"
                    exit_code = 1

            # 2. Check for automation subcommands directly
            elif raw.startswith("workflow "):
                from lucy.services.workflow_engine import get_workflow_engine
                engine = get_workflow_engine()
                wf_id = raw.split()[-1]
                runs = []
                async for update in engine.execute(wf_id):
                    if update.results:
                        runs.append(f"[{update.results[-1].step_id}] {update.results[-1].output}")
                output = "\n".join(runs) if runs else "Workflow finished."

            # 3. Direct Shell Command (with Sandbox guardrails)
            else:
                from lucy.core.sandbox import get_sandbox_manager, DANGEROUS_COMMANDS, SENSITIVE_PATTERNS
                import re

                is_dangerous = False
                reason = ""
                for pat in DANGEROUS_COMMANDS:
                    if re.search(pat, raw, re.IGNORECASE):
                        is_dangerous = True
                        reason = f"Execution of dangerous command matching '{pat}' is blocked."
                        break

                if not is_dangerous:
                    sb = get_sandbox_manager()
                    allowed, reason = sb.validate_command(raw)
                    if not allowed:
                        is_dangerous = True

                if is_dangerous:
                    output = f"Blocked by Sandbox: {reason}"
                    exit_code = 126
                else:
                    proc = await asyncio.create_subprocess_shell(
                        raw,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await proc.communicate()
                    exit_code = proc.returncode or 0
                    output = (stdout.decode(errors="ignore") + stderr.decode(errors="ignore")).strip()

        except Exception as e:
            output = f"Execution error: {e}"
            exit_code = 1

        cmd.status = "completed" if exit_code == 0 else "failed"
        cmd.result_output = output
        cmd.exit_code = exit_code

        # Post result to /results/{id} and update command
        res_payload = {
            "status": cmd.status,
            "exit_code": exit_code,
            "output": output[:4000],
            "finished_at": time.time(),
        }
        self._http_request("PATCH", path, res_payload)
        self._http_request("PUT", f"workstations/{self.config.workstation_id}/results/{cmd.id}", res_payload)

        # Notify mobile with result alert
        self.send_alert(
            title=f"Command {'Completed' if exit_code == 0 else 'Failed'}: {raw[:30]}",
            message=output[:200] or "No output",
            alert_type="success" if exit_code == 0 else "error",
        )
        return output

    # ------------------------------------------------------------------
    # Background Listener Loop
    # ------------------------------------------------------------------

    async def start_listener(self) -> None:
        """Start background polling loop for phone commands and heartbeat."""
        if self._running:
            return
        self._running = True
        self._listener_task = asyncio.create_task(self._loop())
        logger.info("Firebase remote mobile bridge started.")

    async def stop_listener(self) -> None:
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        # Mark offline
        if self.config.database_url:
            self._http_request("PATCH", f"workstations/{self.config.workstation_id}/status", {"online": False})

    async def _loop(self) -> None:
        last_heartbeat = 0.0
        while self._running:
            now = time.time()
            if now - last_heartbeat >= 30.0:
                self.update_status()
                last_heartbeat = now

            try:
                pending = self.poll_commands()
                for cmd in pending:
                    await self.execute_command(cmd)
            except Exception as e:
                logger.debug("Firebase poll error: %s", e)

            await asyncio.sleep(self.config.poll_interval)


_firebase_bridge: FirebaseBridgeService | None = None


def get_firebase_bridge() -> FirebaseBridgeService:
    global _firebase_bridge
    if _firebase_bridge is None:
        _firebase_bridge = FirebaseBridgeService()
    return _firebase_bridge
