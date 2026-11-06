"""
Ollama local model LLM provider.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any, AsyncGenerator

from lucy.api.providers.base import LLMProvider, ProviderCapabilities

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Provider for local Ollama server."""

    name: str = "ollama"
    default_base_url: str = "http://localhost:11434"

    def __init__(
        self,
        base_url: str | None = None,
    ) -> None:
        self._custom_base_url = base_url

    def get_base_url(self) -> str:
        if self._custom_base_url:
            return self._custom_base_url
        return os.environ.get("OLLAMA_HOST", self.default_base_url)

    def is_configured(self) -> bool:
        # Local Ollama is always considered available to try
        return True

    def clean_model_name(self, model: str) -> str:
        """Strip 'ollama:' prefix if present."""
        if ":" in model and not model.startswith("http"):
            prefix, rest = model.split(":", 1)
            if prefix.lower() == "ollama":
                return rest
        return model

    def get_capabilities(self, model: str) -> ProviderCapabilities:
        clean = self.clean_model_name(model).lower()
        supports_thinking = "r1" in clean or "deepseek" in clean
        supports_vision = "vision" in clean or "llava" in clean

        return ProviderCapabilities(
            supports_streaming=True,
            supports_tool_use=True,
            supports_vision=supports_vision,
            supports_thinking=supports_thinking,
            supports_system_prompt=True,
            supports_json_mode=True,
            max_context_window=128000,
            max_output_tokens=8192,
        )

    def translate_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Translate tools to Ollama function calling format."""
        ollama_tools: list[dict[str, Any]] = []
        for t in tools:
            if t.get("type") == "function" and "function" in t:
                ollama_tools.append(t)
                continue

            ollama_tools.append({
                "type": "function",
                "function": {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", t.get("parameters", {})),
                },
            })
        return ollama_tools

    def translate_messages(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """Translate messages into Ollama chat format."""
        api_messages: list[dict[str, Any]] = []

        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else "user")
            content = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")

            if isinstance(content, str):
                api_messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                text_parts: list[str] = []
                for block in content:
                    block_dict = block if isinstance(block, dict) else getattr(block, "__dict__", {})
                    b_type = block_dict.get("type", "")
                    if b_type == "text":
                        text_parts.append(block_dict.get("text", ""))
                    elif b_type == "tool_result":
                        res_content = block_dict.get("content", "")
                        if isinstance(res_content, list):
                            res_parts = [b.get("text", "") if isinstance(b, dict) else str(b) for b in res_content]
                            res_content = "\n".join(res_parts)
                        text_parts.append(str(res_content))
                api_messages.append({"role": role, "content": "\n".join(text_parts)})
            else:
                api_messages.append({"role": role, "content": str(content or "")})

        return api_messages

    async def stream(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        thinking_enabled: bool | None = None,
        max_thinking_tokens: int | None = None,
        abort_signal: asyncio.Event | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream from Ollama API."""
        clean_model = self.clean_model_name(model)
        base_url = self.get_base_url().rstrip("/")
        url = f"{base_url}/api/chat"

        api_messages = self.translate_messages(messages, system_prompt=system_prompt)

        payload: dict[str, Any] = {
            "model": clean_model,
            "messages": api_messages,
            "stream": True,
            "options": {
                "num_ctx": kwargs.get("num_ctx", 8192),
                "num_predict": max_tokens or 4096,
                "temperature": kwargs.get("temperature", 0.0),
            },
        }

        if tools:
            payload["tools"] = self.translate_tools(tools)

        logger.debug("Ollama request: model=%s, messages=%d", clean_model, len(api_messages))

        try:
            import aiohttp
        except ImportError:
            yield {
                "type": "error",
                "error": "aiohttp not installed. Install with: pip install aiohttp or pip install lucy[offline]",
            }
            return

        try:
            timeout = aiohttp.ClientTimeout(total=kwargs.get("timeout", 180), sock_read=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        try:
                            error_data = await resp.json()
                            error_text = error_data.get("error", "")
                        except Exception:
                            error_text = await resp.text()

                        if "does not support tools" in error_text.lower():
                            msg = f"Model '{clean_model}' does not support tools in Ollama. Please use 'llama3.1' or newer."
                        elif "not found" in error_text.lower():
                            msg = f"Model '{clean_model}' not found in Ollama. Run 'ollama pull {clean_model}' to download it."
                        else:
                            msg = f"Ollama error ({resp.status}): {error_text}"

                        yield {"type": "error", "error": msg}
                        return

                    full_text = ""
                    eval_count = 0
                    prompt_eval_count = 0

                    async for line in resp.content:
                        if abort_signal and abort_signal.is_set():
                            yield {"type": "error", "error": "Request cancelled by user"}
                            return

                        line_str = line.decode("utf-8", errors="replace").strip()
                        if not line_str:
                            continue

                        try:
                            chunk = json.loads(line_str)
                        except json.JSONDecodeError:
                            continue

                        message = chunk.get("message", {})
                        content = message.get("content", "")
                        if content:
                            full_text += content
                            yield {"type": "text_delta", "text": content}

                        # Ollama tool calls
                        tool_calls = message.get("tool_calls", [])
                        for tc in tool_calls:
                            func = tc.get("function", {})
                            yield {
                                "type": "tool_use",
                                "id": tc.get("id") or f"tool_{uuid.uuid4().hex[:8]}",
                                "name": func.get("name", ""),
                                "input": func.get("arguments", {}),
                            }

                        if chunk.get("done", False):
                            eval_count = chunk.get("eval_count", 0)
                            prompt_eval_count = chunk.get("prompt_eval_count", 0)
                            yield {
                                "type": "done",
                                "text": full_text,
                                "model": clean_model,
                                "eval_count": eval_count,
                                "prompt_eval_count": prompt_eval_count,
                            }

        except asyncio.CancelledError:
            yield {"type": "error", "error": "Request cancelled by user"}
        except Exception as e:
            logger.exception("Ollama streaming error")
            yield {"type": "error", "error": f"Ollama connection error: {e}"}
