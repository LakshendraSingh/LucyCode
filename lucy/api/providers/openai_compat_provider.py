"""
OpenAI-compatible LLM provider base class.

Provides common streaming, SSE parsing, message translation, and tool conversion
for OpenAI and OpenAI-compatible APIs (Groq, Mistral, DeepSeek, Together, Fireworks, OpenRouter, etc.).
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


class OpenAICompatProvider(LLMProvider):
    """Base provider for OpenAI and OpenAI-compatible REST APIs."""

    name: str = "openai_compat"
    default_base_url: str = "http://localhost:1234/v1"
    api_key_env_var: str = "OPENAI_API_KEY"

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._custom_base_url = base_url
        self._custom_api_key = api_key
        self.extra_headers: dict[str, str] = extra_headers or {}

    def get_base_url(self) -> str:
        """Resolve base URL from instance, environment, or default."""
        if self._custom_base_url:
            return self._custom_base_url
        env_url = os.environ.get("OPENAI_BASE_URL", os.environ.get("OPENAI_API_BASE", ""))
        if env_url:
            return env_url
        return self.default_base_url

    def get_api_key(self) -> str:
        """Resolve API key from instance, environment, or fallback."""
        if self._custom_api_key:
            return self._custom_api_key
        if self.api_key_env_var:
            val = os.environ.get(self.api_key_env_var, "")
            if val:
                return val
        return os.environ.get("OPENAI_API_KEY", "")

    def is_configured(self) -> bool:
        """Return True if credentials or local host are available."""
        # For local servers (localhost), API key is optional
        base_url = self.get_base_url()
        if "localhost" in base_url or "127.0.0.1" in base_url:
            return True
        return bool(self.get_api_key())

    def clean_model_name(self, model: str) -> str:
        """Strip provider prefix from model string if present."""
        if ":" in model:
            _, model_name = model.split(":", 1)
            return model_name
        return model

    def get_capabilities(self, model: str) -> ProviderCapabilities:
        """Return capabilities for the given model."""
        clean = self.clean_model_name(model).lower()
        supports_thinking = "r1" in clean or "reasoner" in clean or clean.startswith(("o1", "o3", "o4"))
        supports_vision = any(v in clean for v in ["vision", "vl", "pixtral", "4o", "4.1", "4.5"])
        return ProviderCapabilities(
            supports_streaming=True,
            supports_tool_use=True,
            supports_vision=supports_vision,
            supports_thinking=supports_thinking,
            supports_system_prompt=True,
            supports_json_mode=True,
            max_context_window=128000,
            max_output_tokens=16384,
        )

    def translate_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Translate Anthropic/Lucy tools schema into OpenAI function calling format."""
        openai_tools: list[dict[str, Any]] = []
        for t in tools:
            # If already in OpenAI format, keep as is
            if t.get("type") == "function" and "function" in t:
                openai_tools.append(t)
                continue

            name = t.get("name", "")
            description = t.get("description", "")
            parameters = t.get("input_schema", t.get("parameters", {"type": "object", "properties": {}}))

            openai_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            })
        return openai_tools

    def translate_messages(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """Translate Lucy/Anthropic messages into standard OpenAI message format."""
        api_messages: list[dict[str, Any]] = []

        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            # Handle object-style messages if passed
            role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else "user")
            content = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")

            if role == "system":
                text = content if isinstance(content, str) else str(content or "")
                api_messages.append({"role": "system", "content": text})
                continue

            if role == "tool":
                # Already an OpenAI tool response
                api_messages.append(msg)
                continue

            if role == "user":
                if isinstance(content, str):
                    api_messages.append({"role": "user", "content": content})
                elif isinstance(content, list):
                    text_parts: list[str] = []
                    content_parts: list[dict[str, Any]] = []
                    tool_results: list[dict[str, Any]] = []

                    for block in content:
                        block_dict = block if isinstance(block, dict) else getattr(block, "__dict__", {})
                        b_type = block_dict.get("type", "")

                        if b_type == "text":
                            t_text = block_dict.get("text", "")
                            text_parts.append(t_text)
                            content_parts.append({"type": "text", "text": t_text})
                        elif b_type == "image":
                            source = block_dict.get("source", {})
                            media_type = source.get("media_type", "image/png")
                            data = source.get("data", "")
                            content_parts.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:{media_type};base64,{data}"},
                            })
                        elif b_type == "tool_result":
                            res_content = block_dict.get("content", "")
                            if isinstance(res_content, list):
                                res_parts = [
                                    b.get("text", "") if isinstance(b, dict) else str(b)
                                    for b in res_content
                                ]
                                res_content = "\n".join(res_parts)
                            tool_results.append({
                                "role": "tool",
                                "tool_call_id": block_dict.get("tool_use_id", ""),
                                "content": str(res_content),
                            })

                    # If we had user text or image, emit user message
                    if any(p.get("type") == "image_url" for p in content_parts):
                        api_messages.append({"role": "user", "content": content_parts})
                    elif text_parts:
                        api_messages.append({"role": "user", "content": "\n".join(text_parts)})

                    # Add separate tool responses
                    api_messages.extend(tool_results)
                else:
                    api_messages.append({"role": "user", "content": str(content or "")})

            elif role == "assistant":
                if isinstance(content, str):
                    api_messages.append({"role": "assistant", "content": content})
                elif isinstance(content, list):
                    text_parts: list[str] = []
                    tool_calls: list[dict[str, Any]] = []

                    for block in content:
                        block_dict = block if isinstance(block, dict) else getattr(block, "__dict__", {})
                        b_type = block_dict.get("type", "")

                        if b_type == "text":
                            text_parts.append(block_dict.get("text", ""))
                        elif b_type == "tool_use":
                            inp = block_dict.get("input", {})
                            arg_str = json.dumps(inp) if isinstance(inp, dict) else str(inp)
                            tool_calls.append({
                                "id": block_dict.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                                "type": "function",
                                "function": {
                                    "name": block_dict.get("name", ""),
                                    "arguments": arg_str,
                                },
                            })

                    asst_msg: dict[str, Any] = {"role": "assistant"}
                    joined_text = "\n".join(text_parts)
                    if joined_text:
                        asst_msg["content"] = joined_text
                    else:
                        asst_msg["content"] = None

                    if tool_calls:
                        asst_msg["tool_calls"] = tool_calls

                    api_messages.append(asst_msg)
                else:
                    api_messages.append({"role": "assistant", "content": str(content or "")})

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
        """Stream responses from the OpenAI-compatible endpoint."""
        clean_model = self.clean_model_name(model)
        base_url = self.get_base_url().rstrip("/")
        url = f"{base_url}/chat/completions"
        api_key = self.get_api_key()

        api_messages = self.translate_messages(messages, system_prompt=system_prompt)

        payload: dict[str, Any] = {
            "model": clean_model,
            "messages": api_messages,
            "stream": True,
        }

        # Handle max tokens (use max_completion_tokens for o1/o3/o4 models if appropriate)
        if max_tokens:
            if clean_model.startswith(("o1", "o3", "o4")):
                payload["max_completion_tokens"] = max_tokens
            else:
                payload["max_tokens"] = max_tokens

        # Only set temperature if not an o-series model that rejects it
        if not clean_model.startswith(("o1", "o3", "o4")):
            payload["temperature"] = kwargs.get("temperature", 0.2)

        # Tools
        if tools:
            payload["tools"] = self.translate_tools(tools)
            payload["tool_choice"] = kwargs.get("tool_choice", "auto")

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            **self.extra_headers,
        }
        if api_key and api_key != "not-needed":
            headers["Authorization"] = f"Bearer {api_key}"

        logger.debug(
            "%s request: url=%s, model=%s, messages=%d, tools=%d",
            self.name, url, clean_model, len(api_messages), len(tools or [])
        )

        try:
            import aiohttp
        except ImportError:
            # Zero-dependency fallback: stream via urllib in background thread
            async for chunk in self._stream_urllib(url, payload, headers, clean_model, abort_signal, **kwargs):
                yield chunk
            return

        try:
            timeout = aiohttp.ClientTimeout(total=kwargs.get("timeout", 180), sock_read=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        err_body = await resp.text()
                        err_msg = err_body
                        try:
                            parsed_err = json.loads(err_body)
                            if "error" in parsed_err:
                                err_obj = parsed_err["error"]
                                err_msg = err_obj.get("message", err_body) if isinstance(err_obj, dict) else str(err_obj)
                        except Exception:
                            pass
                        yield {"type": "error", "error": f"{self.name} error ({resp.status}): {err_msg}"}
                        return

                    full_text = ""
                    tool_call_buffers: dict[int, dict[str, Any]] = {}
                    prompt_tokens = 0
                    completion_tokens = 0

                    async for line_bytes in resp.content:
                        if abort_signal and abort_signal.is_set():
                            yield {"type": "error", "error": "Request cancelled by user"}
                            return

                        line = line_bytes.decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            continue

                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        # Extract token usage if provided in stream
                        usage = data.get("usage")
                        if usage:
                            prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                            completion_tokens = usage.get("completion_tokens", completion_tokens)

                        choices = data.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})

                        # Thinking / Reasoning delta
                        reasoning = delta.get("reasoning_content") or delta.get("reasoning") or delta.get("thinking")
                        if reasoning:
                            yield {"type": "thinking_delta", "thinking": reasoning}

                        # Text delta
                        content = delta.get("content")
                        if content:
                            full_text += content
                            yield {"type": "text_delta", "text": content}

                        # Streaming tool calls
                        for tc in delta.get("tool_calls", []):
                            idx = tc.get("index", 0)
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {
                                    "id": tc.get("id", ""),
                                    "name": tc.get("function", {}).get("name", ""),
                                    "arguments": "",
                                }
                            func = tc.get("function", {})
                            if func.get("name"):
                                tool_call_buffers[idx]["name"] = func["name"]
                            if func.get("arguments"):
                                tool_call_buffers[idx]["arguments"] += func["arguments"]
                            if tc.get("id") and not tool_call_buffers[idx]["id"]:
                                tool_call_buffers[idx]["id"] = tc["id"]

                    # Emit complete tool calls
                    for tc in tool_call_buffers.values():
                        parsed_args: dict[str, Any] = {}
                        raw_args = tc.get("arguments", "")
                        if raw_args:
                            try:
                                parsed_args = json.loads(raw_args)
                            except json.JSONDecodeError:
                                logger.warning("Failed to parse tool arguments JSON: %s", raw_args)
                                parsed_args = {"raw_arguments": raw_args}

                        yield {
                            "type": "tool_use",
                            "id": tc["id"] or f"tool_{uuid.uuid4().hex[:8]}",
                            "name": tc["name"],
                            "input": parsed_args,
                        }

                    yield {
                        "type": "done",
                        "text": full_text,
                        "model": clean_model,
                        "eval_count": completion_tokens,
                        "prompt_eval_count": prompt_tokens,
                    }

        except asyncio.CancelledError:
            yield {"type": "error", "error": "Request cancelled by user"}
        except Exception as e:
            logger.exception("%s streaming error", self.name)
            yield {"type": "error", "error": f"{self.name} connection error: {e}"}

    async def _stream_urllib(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        clean_model: str,
        abort_signal: asyncio.Event | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Fallback streaming via standard library urllib and threading."""
        import queue
        import threading
        import urllib.error
        import urllib.request

        q: queue.Queue[tuple[str, Any]] = queue.Queue()

        def worker() -> None:
            try:
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=kwargs.get("timeout", 180)) as resp:
                    full_text = ""
                    prompt_tokens = 0
                    completion_tokens = 0
                    tool_call_buffers: dict[int, dict[str, Any]] = {}

                    for line_bytes in resp:
                        if abort_signal and abort_signal.is_set():
                            q.put(("chunk", {"type": "error", "error": "Request cancelled by user"}))
                            return

                        line = line_bytes.decode("utf-8", errors="replace").strip()
                        if not line or not line.startswith("data:"):
                            continue

                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            item = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        usage = item.get("usage")
                        if usage:
                            prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                            completion_tokens = usage.get("completion_tokens", completion_tokens)

                        choices = item.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})

                        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                        if reasoning:
                            q.put(("chunk", {"type": "thinking_delta", "thinking": reasoning}))

                        content = delta.get("content")
                        if content:
                            full_text += content
                            q.put(("chunk", {"type": "text_delta", "text": content}))

                        for tc in delta.get("tool_calls", []):
                            idx = tc.get("index", 0)
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {
                                    "id": tc.get("id", ""),
                                    "name": tc.get("function", {}).get("name", ""),
                                    "arguments": "",
                                }
                            func = tc.get("function", {})
                            if func.get("name"):
                                tool_call_buffers[idx]["name"] = func["name"]
                            if func.get("arguments"):
                                tool_call_buffers[idx]["arguments"] += func["arguments"]
                            if tc.get("id"):
                                tool_call_buffers[idx]["id"] = tc["id"]

                    for tc in tool_call_buffers.values():
                        raw_args = tc["arguments"].strip()
                        try:
                            parsed_args = json.loads(raw_args) if raw_args else {}
                        except json.JSONDecodeError:
                            parsed_args = {"raw_arguments": raw_args}

                        q.put(("chunk", {
                            "type": "tool_use",
                            "id": tc["id"] or f"tool_{uuid.uuid4().hex[:8]}",
                            "name": tc["name"],
                            "input": parsed_args,
                        }))

                    q.put(("chunk", {
                        "type": "done",
                        "text": full_text,
                        "model": clean_model,
                        "eval_count": completion_tokens,
                        "prompt_eval_count": prompt_tokens,
                    }))
            except urllib.error.HTTPError as e:
                err_text = e.read().decode("utf-8", errors="replace")
                q.put(("chunk", {"type": "error", "error": f"{self.name} API error ({e.code}): {err_text}"}))
            except Exception as e:
                q.put(("chunk", {"type": "error", "error": f"{self.name} connection error: {e}"}))
            finally:
                q.put(("eof", None))

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        while True:
            try:
                kind, val = q.get_nowait()
                if kind == "eof":
                    break
                yield val
            except queue.Empty:
                if not t.is_alive() and q.empty():
                    break
                await asyncio.sleep(0.01)
