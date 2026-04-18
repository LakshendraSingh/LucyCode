"""
NDJSON structure emitter for IPC with the Node.js Ink frontend.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from pydantic import BaseModel

class NDJSONEmitter:
    """Emits strictly formatted NDJSON lines to stdout."""

    @staticmethod
    def emit(event_type: str, data: dict[str, Any] = None) -> None:
        """Encode an event to NDJSON and write to stdout immediately."""
        payload = {"type": event_type}
        if data:
            # Handle non-serializable objects gently
            clean_data = {}
            for k, v in data.items():
                if isinstance(v, BaseModel):
                    clean_data[k] = v.model_dump()
                else:
                    clean_data[k] = v
            payload["data"] = clean_data
            
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()

    @staticmethod
    def emit_text_delta(text: str) -> None:
        NDJSONEmitter.emit("text_delta", {"text": text})

    @staticmethod
    def emit_tool_start(tool_name: str, input_fragment: dict | None = None) -> None:
        NDJSONEmitter.emit("tool_use_start", {"name": tool_name, "input": input_fragment or {}})

    @staticmethod
    def emit_tool_complete(tool_name: str, input_obj: dict | None = None, result_text: str | None = None, is_error: bool = False) -> None:
        NDJSONEmitter.emit("tool_use_complete", {
            "name": tool_name,
            "input": input_obj or {},
            "result": result_text,
            "is_error": is_error
        })

    @staticmethod
    def emit_message(role: str, content: str) -> None:
        NDJSONEmitter.emit("message", {"role": role, "content": content})

    @staticmethod
    def emit_error(message: str) -> None:
        NDJSONEmitter.emit("error", {"message": message})
