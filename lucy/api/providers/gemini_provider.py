"""
Google Gemini LLM provider using pure aiohttp REST API calls.
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


class GeminiProvider(LLMProvider):
    """Provider for Google Gemini models (gemini-2.5-pro, gemini-2.5-flash, etc.)."""

    name: str = "gemini"
    default_base_url: str = "https://generativelanguage.googleapis.com"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._custom_api_key = api_key
        self._custom_base_url = base_url

    def get_api_key(self) -> str:
        """Resolve API key from instance or environment."""
        if self._custom_api_key:
            return self._custom_api_key
        return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")

    def is_configured(self) -> bool:
        """Return True if an API key is available."""
        return bool(self.get_api_key())

    def clean_model_name(self, model: str) -> str:
        """Strip provider prefix if present and map to active Google API model."""
        if ":" in model:
            _, model_name = model.split(":", 1)
        else:
            model_name = model
        # Map aliases and deprecated names to active models
        if model_name in ("gemini", "gemini-flash", "gemini-lite", "gemini-2.5-flash"):
            return "gemini-3.1-flash-lite"
        if model_name in ("gemini-pro", "gemini-2.5-pro"):
            return "gemini-pro-latest"
        return model_name

    def get_capabilities(self, model: str) -> ProviderCapabilities:
        clean = self.clean_model_name(model).lower()
        raw = model.lower()
        supports_thinking = "3." in clean or "2.5" in clean or "pro" in clean or "thinking" in clean or "2.5" in raw
        is_pro = "pro" in clean or "pro" in raw
        max_context = 2000000 if is_pro else 1000000

        return ProviderCapabilities(
            supports_streaming=True,
            supports_tool_use=True,
            supports_vision=True,
            supports_thinking=supports_thinking,
            supports_system_prompt=True,
            supports_json_mode=True,
            max_context_window=max_context,
            max_output_tokens=65536 if ("3." in clean or "2.5" in clean or "2.5" in raw) else 8192,
        )

    def translate_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Translate tools into Gemini functionDeclarations format."""
        declarations: list[dict[str, Any]] = []
        for t in tools:
            # Handle if already in Gemini format
            if "functionDeclarations" in t:
                return tools

            name = t.get("name", "")
            description = t.get("description", "")
            schema = t.get("input_schema", t.get("parameters", {}))

            declarations.append({
                "name": name,
                "description": description,
                "parameters": schema,
            })

        return [{"functionDeclarations": declarations}] if declarations else []

    def translate_messages(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """Translate messages into Gemini contents format (user / model turns)."""
        raw_contents: list[dict[str, Any]] = []

        # Index tool calls to map tool_use_id -> (function_name, thought_signature)
        call_id_to_name: dict[str, str] = {}
        call_id_to_sig: dict[str, str] = {}

        for msg in messages:
            content = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")
            if isinstance(content, list):
                for block in content:
                    block_dict = block if isinstance(block, dict) else getattr(block, "__dict__", {})
                    if block_dict.get("type") == "tool_use":
                        cid = block_dict.get("id") or block_dict.get("tool_use_id", "")
                        cname = block_dict.get("name", "")
                        csig = block_dict.get("thought_signature") or block_dict.get("thoughtSignature", "")
                        if cid:
                            call_id_to_name[cid] = cname
                            if csig:
                                call_id_to_sig[cid] = csig

        for msg in messages:
            role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else "user")
            content = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")

            # Gemini maps "assistant" to "model"
            gemini_role = "model" if role == "assistant" else "user"
            parts: list[dict[str, Any]] = []

            if isinstance(content, str):
                if content:
                    parts.append({"text": content})
            elif isinstance(content, list):
                for block in content:
                    block_dict = block if isinstance(block, dict) else getattr(block, "__dict__", {})
                    b_type = block_dict.get("type", "")

                    if b_type == "text":
                        text_val = block_dict.get("text", "")
                        if text_val:
                            parts.append({"text": text_val})

                    elif b_type == "tool_use":
                        cname = block_dict.get("name", "")
                        cid = block_dict.get("id", "")
                        csig = (
                            block_dict.get("thought_signature")
                            or block_dict.get("thoughtSignature")
                            or call_id_to_sig.get(cid, "")
                        )
                        part_obj: dict[str, Any] = {
                            "functionCall": {
                                "name": cname,
                                "args": block_dict.get("input", {}),
                            }
                        }
                        if csig:
                            part_obj["thoughtSignature"] = csig
                        parts.append(part_obj)

                    elif b_type == "tool_result":
                        res_content = block_dict.get("content", "")
                        if isinstance(res_content, list):
                            res_parts = [
                                b.get("text", "") if isinstance(b, dict) else str(b)
                                for b in res_content
                            ]
                            res_content = "\n".join(res_parts)
                        call_id = block_dict.get("tool_use_id", "")
                        # Gemini requires function name, NOT call_id
                        func_name = call_id_to_name.get(call_id) or block_dict.get("name") or "tool"
                        parts.append({
                            "functionResponse": {
                                "name": func_name,
                                "response": {"result": str(res_content)},
                            }
                        })

                    elif b_type == "image":
                        source = block_dict.get("source", {})
                        media_type = source.get("media_type", "image/png")
                        data = source.get("data", "")
                        parts.append({
                            "inlineData": {
                                "mimeType": media_type,
                                "data": data,
                            }
                        })

            if parts:
                raw_contents.append({"role": gemini_role, "parts": parts})

        # Merge consecutive turns with the same role (Gemini requirement)
        merged_contents: list[dict[str, Any]] = []
        for turn in raw_contents:
            if merged_contents and merged_contents[-1]["role"] == turn["role"]:
                merged_contents[-1]["parts"].extend(turn["parts"])
            else:
                merged_contents.append(turn)

        return merged_contents

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
        """Stream responses from the Google Gemini REST API."""
        clean_model = self.clean_model_name(model)
        api_key = self.get_api_key()
        if not api_key:
            yield {"type": "error", "error": "Gemini API key not found. Set GEMINI_API_KEY or GOOGLE_API_KEY."}
            return

        base_url = (self._custom_base_url or self.default_base_url).rstrip("/")
        url = f"{base_url}/v1beta/models/{clean_model}:streamGenerateContent?alt=sse&key={api_key}"

        contents = self.translate_messages(messages)
        body: dict[str, Any] = {"contents": contents}

        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        if tools:
            gemini_tools = self.translate_tools(tools)
            if gemini_tools:
                body["tools"] = gemini_tools

        gen_config: dict[str, Any] = {}
        if max_tokens:
            gen_config["maxOutputTokens"] = max_tokens

        caps = self.get_capabilities(clean_model)
        if thinking_enabled and caps.supports_thinking:
            budget = max_thinking_tokens or 4096
            gen_config["thinkingConfig"] = {"thinkingBudget": budget}

        if gen_config:
            body["generationConfig"] = gen_config

        headers = {"Content-Type": "application/json"}

        logger.debug(
            "Gemini request: model=%s, turns=%d, tools=%d",
            clean_model, len(contents), len(tools or [])
        )

        try:
            import aiohttp
        except ImportError:
            # Zero-dependency fallback: stream via urllib in background thread with retry & model fallback
            async for chunk in self._stream_urllib(base_url, api_key, body, headers, clean_model, abort_signal, **kwargs):
                yield chunk
            return

        try:
            timeout = aiohttp.ClientTimeout(total=kwargs.get("timeout", 180), sock_read=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=body, headers=headers) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        yield {"type": "error", "error": f"Gemini API error ({resp.status}): {err_text}"}
                        return

                    full_text = ""
                    prompt_tokens = 0
                    completion_tokens = 0

                    async for line_bytes in resp.content:
                        if abort_signal and abort_signal.is_set():
                            yield {"type": "error", "error": "Request cancelled by user"}
                            return

                        line = line_bytes.decode("utf-8", errors="replace").strip()
                        if not line or not line.startswith("data:"):
                            continue

                        data_str = line[5:].strip()
                        if not data_str:
                            continue

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        # Usage metadata
                        usage = data.get("usageMetadata", {})
                        if usage:
                            prompt_tokens = usage.get("promptTokenCount", prompt_tokens)
                            completion_tokens = usage.get("candidatesTokenCount", completion_tokens)

                        candidates = data.get("candidates", [])
                        if not candidates:
                            continue

                        candidate = candidates[0]
                        candidate_content = candidate.get("content", {})
                        parts = candidate_content.get("parts", [])

                        for part in parts:
                            # Thinking / Reasoning in Gemini 2.5
                            if part.get("thought"):
                                thought_text = part.get("text", "")
                                if thought_text:
                                    yield {"type": "thinking_delta", "thinking": thought_text}
                            elif "text" in part:
                                text_val = part.get("text", "")
                                if text_val:
                                    full_text += text_val
                                    yield {"type": "text_delta", "text": text_val}
                            elif "functionCall" in part:
                                fc = part["functionCall"]
                                sig = (
                                    part.get("thoughtSignature")
                                    or part.get("thought_signature")
                                    or fc.get("thoughtSignature")
                                    or fc.get("thought_signature")
                                    or candidate.get("thoughtSignature")
                                    or candidate.get("thought_signature")
                                    or ""
                                )
                                yield {
                                    "type": "tool_use",
                                    "id": fc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                                    "name": fc.get("name", ""),
                                    "input": fc.get("args", {}),
                                    "thought_signature": sig,
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
            logger.exception("Gemini streaming error")
            yield {"type": "error", "error": f"Gemini connection error: {e}"}

    async def _stream_urllib(
        self,
        base_url: str,
        api_key: str,
        body: dict[str, Any],
        headers: dict[str, str],
        clean_model: str,
        abort_signal: asyncio.Event | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Fallback streaming via standard library urllib and threading with automatic retry & fallback."""
        import queue
        import threading
        import time
        import urllib.error
        import urllib.request

        q: queue.Queue[tuple[str, Any]] = queue.Queue()

        def worker() -> None:
            models_to_try = [clean_model]
            for alt in ("gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash", "gemini-pro-latest"):
                if alt not in models_to_try:
                    models_to_try.append(alt)

            last_error = ""
            for current_model in models_to_try:
                current_url = f"{base_url}/v1beta/models/{current_model}:streamGenerateContent?alt=sse&key={api_key}"

                for attempt in range(2):
                    if abort_signal and abort_signal.is_set():
                        q.put(("chunk", {"type": "error", "error": "Request cancelled by user"}))
                        q.put(("eof", None))
                        return

                    try:
                        data = json.dumps(body).encode("utf-8")
                        req = urllib.request.Request(current_url, data=data, headers=headers, method="POST")
                        with urllib.request.urlopen(req, timeout=kwargs.get("timeout", 180)) as resp:
                            full_text = ""
                            prompt_tokens = 0
                            completion_tokens = 0

                            for line_bytes in resp:
                                if abort_signal and abort_signal.is_set():
                                    q.put(("chunk", {"type": "error", "error": "Request cancelled by user"}))
                                    q.put(("eof", None))
                                    return

                                line = line_bytes.decode("utf-8", errors="replace").strip()
                                if not line or not line.startswith("data:"):
                                    continue

                                data_str = line[5:].strip()
                                if not data_str:
                                    continue

                                try:
                                    item = json.loads(data_str)
                                except json.JSONDecodeError:
                                    continue

                                usage = item.get("usageMetadata", {})
                                if usage:
                                    prompt_tokens = usage.get("promptTokenCount", prompt_tokens)
                                    completion_tokens = usage.get("candidatesTokenCount", completion_tokens)

                                candidates = item.get("candidates", [])
                                if not candidates:
                                    continue

                                candidate = candidates[0]
                                candidate_content = candidate.get("content", {})
                                parts = candidate_content.get("parts", [])

                                for part in parts:
                                    if part.get("thought"):
                                        thought_text = part.get("text", "")
                                        if thought_text:
                                            q.put(("chunk", {"type": "thinking_delta", "thinking": thought_text}))
                                    elif "text" in part:
                                        text_val = part.get("text", "")
                                        if text_val:
                                            full_text += text_val
                                            q.put(("chunk", {"type": "text_delta", "text": text_val}))
                                    elif "functionCall" in part:
                                        fc = part["functionCall"]
                                        sig = (
                                            part.get("thoughtSignature")
                                            or part.get("thought_signature")
                                            or fc.get("thoughtSignature")
                                            or fc.get("thought_signature")
                                            or candidate.get("thoughtSignature")
                                            or candidate.get("thought_signature")
                                            or ""
                                        )
                                        q.put(("chunk", {
                                            "type": "tool_use",
                                            "id": fc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                                            "name": fc.get("name", ""),
                                            "input": fc.get("args", {}),
                                            "thought_signature": sig,
                                        }))

                            q.put(("chunk", {
                                "type": "done",
                                "text": full_text,
                                "model": current_model,
                                "eval_count": completion_tokens,
                                "prompt_eval_count": prompt_tokens,
                            }))
                            q.put(("eof", None))
                            return

                    except urllib.error.HTTPError as e:
                        err_text = e.read().decode("utf-8", errors="replace")
                        last_error = f"Gemini API error ({e.code}): {err_text}"
                        if e.code in (503, 429):
                            # Temporary capacity spike - backoff and retry or fallback
                            logger.info(f"Gemini {current_model} busy ({e.code}). Retrying or falling back to alternate model...")
                            time.sleep(1.2)
                            continue
                        elif e.code == 404:
                            # Model not found or deprecated - immediately try next model in candidate chain
                            break
                        else:
                            # 400 or auth failure - don't hammer
                            break
                    except Exception as e:
                        last_error = f"Gemini connection error: {e}"
                        break

            q.put(("chunk", {"type": "error", "error": last_error or "All candidate Gemini models temporarily unavailable"}))
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
