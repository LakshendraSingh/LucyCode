"""
Mobile QR — generate QR codes for mobile access.

Generates QR codes in the terminal using Unicode block characters.
The QR contains:
  - WebSocket URL to the Lucy Code server
  - Authentication token (time-limited)
  - Session configuration
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QRPayload:
    """Data encoded in the QR code."""
    url: str
    token: str
    session_id: str = ""
    expires_at: float = 0.0


def generate_qr_text(data: str, border: int = 1) -> str:
    """Generate a QR code as a Unicode text string.

    Uses a simple implementation that creates a valid-looking QR pattern.
    For real QR generation, install `qrcode` library.
    """
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)

        matrix = qr.get_matrix()
        lines = []
        # Each line combines two rows into one using half-block characters
        for r in range(0, len(matrix), 2):
            line = ""
            for c in range(len(matrix[0])):
                top = matrix[r][c]
                bottom = matrix[r + 1][c] if r + 1 < len(matrix) else False

                if top and bottom:
                    line += "\u2588"  # Full block
                elif top:
                    line += "\u2580"  # Upper half block
                elif bottom:
                    line += "\u2584"  # Lower half block
                else:
                    line += " "
            lines.append(line)

        return "\n".join(lines)

    except ImportError:
        # Fallback: generate a simple pattern
        return _fallback_qr_display(data)


def _fallback_qr_display(data: str) -> str:
    """Fallback QR display when qrcode library is not available."""
    lines = [
        "┌────────────────────────────────────┐",
        "│  QR code requires `qrcode` package │",
        "│  pip install qrcode[pil]           │",
        "│                                    │",
        f"│  URL: {data[:30]:<30} │",
        "│                                    │",
        "│  Scan with your phone camera       │",
        "└────────────────────────────────────┘",
    ]
    return "\n".join(lines)


def generate_mobile_qr(
    server_host: str = "127.0.0.1",
    server_port: int = 9847,
    token: str = "",
    session_id: str = "",
    ttl_seconds: float = 3600,
) -> tuple[str, QRPayload]:
    """Generate a QR code for mobile access.

    Returns (qr_text, payload).
    """
    url = f"ws://{server_host}:{server_port}"

    payload = QRPayload(
        url=url,
        token=token,
        session_id=session_id,
        expires_at=time.time() + ttl_seconds,
    )

    qr_data = json.dumps({
        "url": payload.url,
        "token": payload.token,
        "session": payload.session_id,
        "exp": int(payload.expires_at),
    })

    qr_text = generate_qr_text(qr_data)

    return qr_text, payload


def display_mobile_qr(
    server_host: str = "127.0.0.1",
    server_port: int = 9847,
    token: str = "",
    session_id: str = "",
) -> str:
    """Generate and format a QR code display for the terminal."""
    qr_text, payload = generate_mobile_qr(
        server_host, server_port, token, session_id,
    )

    header = [
        "",
        "  ╔══════════════════════════════════════╗",
        "  ║     📱 Scan to connect from phone     ║",
        "  ╚══════════════════════════════════════╝",
        "",
    ]

    footer = [
        "",
        f"  Server: {payload.url}",
        f"  Token:  {payload.token[:20]}..." if len(payload.token) > 20 else f"  Token:  {payload.token}",
        f"  Expires: {time.strftime('%H:%M:%S', time.localtime(payload.expires_at))}",
        "",
    ]

    # Indent QR code
    qr_lines = ["    " + line for line in qr_text.split("\n")]

    return "\n".join(header + qr_lines + footer)
