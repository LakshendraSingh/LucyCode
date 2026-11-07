"""
Unit tests for the Firebase Remote Bridge and Mobile Gateway (/firebase).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lucy.commands.firebase_commands import FirebaseCommand
from lucy.services.firebase_bridge import FirebaseBridgeService, FirebaseConfig, RemoteAlert, RemoteCommand, get_firebase_bridge


class TestFirebaseBridge(unittest.TestCase):
    """Test suite for Firebase Mobile Remote Bridge."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp()
        self.cfg_file = Path(self.tmp_dir) / "firebase.json"
        self.bridge = FirebaseBridgeService(config_file=self.cfg_file)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_configure_and_save(self) -> None:
        """Test configuring database URL and workstation id."""
        self.bridge.configure(
            database_url="https://test-lucy-rtdb.firebaseio.com",
            auth_token="secret_token_123",
            workstation_id="test_workstation",
        )
        self.assertEqual(self.bridge.config.database_url, "https://test-lucy-rtdb.firebaseio.com")
        self.assertEqual(self.bridge.config.auth_token, "secret_token_123")
        self.assertEqual(self.bridge.config.workstation_id, "test_workstation")

        # Reload from disk
        reloaded = FirebaseBridgeService(config_file=self.cfg_file)
        self.assertEqual(reloaded.config.database_url, "https://test-lucy-rtdb.firebaseio.com")
        self.assertEqual(reloaded.config.workstation_id, "test_workstation")

    def test_send_alert_mock(self) -> None:
        """Test sending alerts to Firebase endpoint."""
        self.bridge.configure("https://test-lucy-rtdb.firebaseio.com")

        mock_requests = []

        def mock_http(method: str, path: str, data: any = None):
            mock_requests.append((method, path, data))
            return True, {"name": "alert_ok"}

        self.bridge._http_request = mock_http

        ok = self.bridge.send_alert(
            title="Build Passed",
            message="All 108 tests passing.",
            alert_type="success",
        )
        self.assertTrue(ok)
        self.assertEqual(len(mock_requests), 1)
        method, path, payload = mock_requests[0]
        self.assertEqual(method, "PUT")
        self.assertIn("alerts", path)
        self.assertEqual(payload["title"], "Build Passed")
        self.assertEqual(payload["alert_type"], "success")

    def test_poll_and_execute_remote_command(self) -> None:
        """Test polling inbound commands and executing them securely."""
        self.bridge.configure("https://test-lucy-rtdb.firebaseio.com", workstation_id="ws1")

        cmd = RemoteCommand(
            id="cmd_999",
            command="echo 'remote execution works'",
            source="phone",
        )

        mock_updates = []

        def mock_http(method: str, path: str, data: any = None):
            mock_updates.append((method, path, data))
            return True, {}

        self.bridge._http_request = mock_http

        output = asyncio.run(self.bridge.execute_command(cmd))
        self.assertIn("remote execution works", output)
        self.assertEqual(cmd.status, "completed")
        self.assertEqual(cmd.exit_code, 0)

    def test_command_blocked_by_sandbox(self) -> None:
        """Test that unsafe commands from phone are intercepted by sandbox."""
        self.bridge.configure("https://test-lucy-rtdb.firebaseio.com")

        unsafe_cmd = RemoteCommand(
            id="cmd_bad",
            command="rm -rf /",
            source="phone",
        )

        self.bridge._http_request = lambda m, p, d=None: (True, {})

        output = asyncio.run(self.bridge.execute_command(unsafe_cmd))
        self.assertIn("Blocked by Sandbox", output)
        self.assertEqual(unsafe_cmd.status, "failed")
        self.assertEqual(unsafe_cmd.exit_code, 126)

    def test_firebase_slash_commands(self) -> None:
        """Test /firebase status, /firebase help, /firebase connect."""
        cmd = FirebaseCommand()
        self.assertEqual(cmd.name, "firebase")

        # /firebase help
        res_help = asyncio.run(cmd.execute("help", None))
        self.assertIn("Firebase Mobile Gateway Commands", res_help.output)

        # /firebase status
        res_status = asyncio.run(cmd.execute("status", None))
        self.assertIn("Firebase Gateway Status", res_status.output)

        # /firebase connect
        res_conn = asyncio.run(cmd.execute("connect", None))
        self.assertIn("Connect Your Phone to Workstation", res_conn.output)


if __name__ == "__main__":
    unittest.main()

