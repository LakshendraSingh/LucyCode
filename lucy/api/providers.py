"""
Multi-provider API client — supports Anthropic, Ollama, OpenAI-compatible, and llama.cpp.

Provider registry maps model prefixes to backends:
  - "claude-*"     → Anthropic API
  - "ollama:*"     → Local Ollama server
  - "openai:*"     → OpenAI-compatible API (LM Studio, vLLM, text-gen-webui, etc.)
  - "llama:*"      → llama.cpp server
  - "local:*"      → Auto-detect local server (tries Ollama then OpenAI-compat)

All providers expose the same streaming interface for plug-and-play model swapping.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncGenerator
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider types
# ---------------------------------------------------------------------------

class ProviderType:
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    OPENAI = "openai"
    LLAMACPP = "llamacpp"
    LOCAL = "local"
    WEIGHTS = "weights"


@dataclass
class ProviderConfig:
    """Configuration for a model provider."""
    provider: str = ProviderType.ANTHROPIC
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""   # The actual model name to send to the provider


def detect_provider(model: str) -> tuple[str, str]:
    """Detect the provider and actual model name from a model string.

    Examples:
        "claude-sonnet-4-20250514"  → (anthropic, claude-sonnet-4-20250514)
        "ollama:deepseek-coder-v2"  → (ollama, deepseek-coder-v2)
        "openai:gpt-4"             → (openai, gpt-4)
        "llama:codellama-7b"       → (llamacpp, codellama-7b)
        "local:mistral"            → (local, mistral)
    """
    if ":" in model:
        prefix, name = model.split(":", 1)
        prefix = prefix.lower()
        mapping = {
            "ollama": ProviderType.OLLAMA,
            "openai": ProviderType.OPENAI,
            "llama": ProviderType.LLAMACPP,
            "llamacpp": ProviderType.LLAMACPP,
            "local": ProviderType.LOCAL,
            "lmstudio": ProviderType.OPENAI,
            "vllm": ProviderType.OPENAI,
        }
        return mapping.get(prefix, ProviderType.OPENAI), name

    # 3. Direct weights (local .gguf or .safetensors files)
    if model.endswith(".gguf") or model.endswith(".safetensors") or os.path.exists(model):
        return ProviderType.WEIGHTS, model
    if model.startswith("claude-"):
        return ProviderType.ANTHROPIC, model
    if model.startswith("gpt-") or model.startswith("o1-"):
        return ProviderType.OPENAI, model

    # Default: treat as Anthropic (backwards compat)
    return ProviderType.ANTHROPIC, model


def get_provider_config(model: str) -> ProviderConfig:
    """Build provider config from a model string."""
    import os
    provider, model_name = detect_provider(model)

    config = ProviderConfig(provider=provider, model_name=model_name)

    if provider == ProviderType.OLLAMA:
        config.base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    elif provider == ProviderType.OPENAI:
        config.base_url = os.environ.get(
            "OPENAI_BASE_URL",
            os.environ.get("OPENAI_API_BASE", "http://localhost:1234/v1")
        )
        config.api_key = os.environ.get("OPENAI_API_KEY", "not-needed")
    elif provider == ProviderType.LLAMACPP:
        config.base_url = os.environ.get("LLAMACPP_HOST", "http://localhost:8080")
    elif provider == ProviderType.LOCAL:
        # Try to detect which server is running
        config.base_url = os.environ.get("LOCAL_LLM_HOST", "http://localhost:11434")
    elif provider == ProviderType.WEIGHTS:
        # model_name is the path to the weights
        config.model_name = os.path.abspath(model_name)

    return config


# ---------------------------------------------------------------------------
# Ollama provider
# ---------------------------------------------------------------------------

async def stream_ollama(
    messages: list[dict],
    system_prompt: str,
    model_name: str,
    base_url: str = "http://localhost:11434",
    tools: list[dict] | None = None,
    **kwargs,
) -> AsyncGenerator[dict, None]:
    """Stream from Ollama API (chat/completions compatible)."""
    import aiohttp

    url = f"{base_url}/api/chat"

    # Build messages with system prompt
    api_messages = [{"role": "system", "content": system_prompt}]
    for m in messages:
        api_messages.append(m)

    logger.debug("Ollama request: model=%s, messages=%d", model_name, len(api_messages))

    payload = {
        "model": model_name,
        "messages": api_messages,
        "stream": True,
        "options": {
            "num_ctx": 8192,  # Optimized for performance on MacBook Air
            "num_predict": kwargs.get("max_tokens", 4096),
            "temperature": 0.0,  # Stable tool use
        }
    }

    # Ollama supports tools natively
    if tools:
        ollama_tools = []
        for t in tools:
            ollama_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            })
        payload["tools"] = ollama_tools

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    error_data = await resp.json()
                    error_text = error_data.get("error", "")
                    
                    if "does not support tools" in error_text.lower():
                        msg = f"Model '{model_name}' does not support tools in Ollama. Please use 'llama3.1' or newer."
                    elif "not found" in error_text.lower():
                        msg = f"Model '{model_name}' not found in Ollama. Use 'ollama pull {model_name}' to download it."
                    else:
                        msg = f"Ollama error {resp.status}: {error_text}"
                        
                    yield {"type": "error", "error": msg}
                    return

                full_text = ""
                async for line in resp.content:
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    message = chunk.get("message", {})
                    content = message.get("content", "")
                    if content:
                        full_text += content
                        yield {"type": "text_delta", "text": content}

                    # Tool calls
                    tool_calls = message.get("tool_calls", [])
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        yield {
                            "type": "tool_use",
                            "id": tc.get("id", f"tool_{hash(func.get('name', ''))}"),
                            "name": func.get("name", ""),
                            "input": func.get("arguments", {}),
                        }

                    if chunk.get("done", False):
                        yield {
                            "type": "done",
                            "text": full_text,
                            "model": model_name,
                            "eval_count": chunk.get("eval_count", 0),
                            "prompt_eval_count": chunk.get("prompt_eval_count", 0),
                        }
    except Exception as e:
        yield {"type": "error", "error": f"Ollama connection error: {e}"}


# ---------------------------------------------------------------------------
# OpenAI-compatible provider (LM Studio, vLLM, text-gen-webui, etc.)
# ---------------------------------------------------------------------------

async def stream_openai_compat(
    messages: list[dict],
    system_prompt: str,
    model_name: str,
    base_url: str = "http://localhost:1234/v1",
    api_key: str = "not-needed",
    tools: list[dict] | None = None,
    **kwargs,
) -> AsyncGenerator[dict, None]:
    """Stream from an OpenAI-compatible API."""
    import aiohttp

    url = f"{base_url}/chat/completions"

    api_messages = [{"role": "system", "content": system_prompt}]
    for m in messages:
        api_messages.append(m)

    payload = {
        "model": model_name,
        "messages": api_messages,
        "stream": True,
        "max_tokens": kwargs.get("max_tokens", 4096),
        "temperature": kwargs.get("temperature", 0.1),
    }

    if tools:
        oai_tools = []
        for t in tools:
            oai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            })
        payload["tools"] = oai_tools
        payload["tool_choice"] = "auto"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    yield {"type": "error", "error": f"API error {resp.status}: {error_text}"}
                    return

                full_text = ""
                tool_call_buffers: dict[int, dict] = {}

                async for line in resp.content:
                    line_str = line.decode("utf-8", errors="replace").strip()
                    if not line_str or not line_str.startswith("data: "):
                        continue
                    data_str = line_str[6:]
                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = data.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})

                    # Text content
                    content = delta.get("content", "")
                    if content:
                        full_text += content
                        yield {"type": "text_delta", "text": content}

                    # Tool calls
                    for tc in delta.get("tool_calls", []):
                        idx = tc.get("index", 0)
                        if idx not in tool_call_buffers:
                            tool_call_buffers[idx] = {
                                "id": tc.get("id", ""),
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments": "",
                            }
                        func = tc.get("function", {})
                        if "name" in func and func["name"]:
                            tool_call_buffers[idx]["name"] = func["name"]
                        if "arguments" in func:
                            tool_call_buffers[idx]["arguments"] += func["arguments"]

                # Emit completed tool calls
                for tc in tool_call_buffers.values():
                    try:
                        args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except json.JSONDecodeError:
                        args = {}
                    yield {
                        "type": "tool_use",
                        "id": tc["id"] or f"tool_{tc['name']}",
                        "name": tc["name"],
                        "input": args,
                    }

                yield {
                    "type": "done",
                    "text": full_text,
                    "model": model_name,
                }

    except Exception as e:
        yield {"type": "error", "error": f"OpenAI-compat connection error: {e}"}


# ---------------------------------------------------------------------------
# llama.cpp provider
# ---------------------------------------------------------------------------

async def stream_llamacpp(
    messages: list[dict],
    system_prompt: str,
    model_name: str,
    base_url: str = "http://localhost:8080",
    **kwargs,
) -> AsyncGenerator[dict, None]:
    """Stream from llama.cpp server (compatible with /completion or /v1/chat/completions)."""
    import aiohttp

    # llama.cpp supports OpenAI-compatible API on /v1/chat/completions
    url = f"{base_url}/v1/chat/completions"

    api_messages = [{"role": "system", "content": system_prompt}]
    for m in messages:
        api_messages.append(m)

    payload = {
        "messages": api_messages,
        "stream": True,
        "n_predict": kwargs.get("max_tokens", 4096),
        "temperature": kwargs.get("temperature", 0.1),
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    # Fallback: try /completion endpoint
                    yield {"type": "error", "error": f"llama.cpp error {resp.status}"}
                    return

                full_text = ""
                async for line in resp.content:
                    line_str = line.decode("utf-8", errors="replace").strip()
                    if not line_str or not line_str.startswith("data: "):
                        continue
                    data_str = line_str[6:]
                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = data.get("choices", [])
                    if choices:
                        content = choices[0].get("delta", {}).get("content", "")
                        if content:
                            full_text += content
                            yield {"type": "text_delta", "text": content}

                yield {"type": "done", "text": full_text, "model": model_name}

    except Exception as e:
        yield {"type": "error", "error": f"llama.cpp connection error: {e}"}


# ---------------------------------------------------------------------------
# Unified provider interface
# ---------------------------------------------------------------------------

async def stream_local(
    messages: list[dict],
    system_prompt: str,
    model: str,
    tools: list[dict] | None = None,
    **kwargs,
) -> AsyncGenerator[dict, None]:
    """Unified streaming interface for any provider.

    Automatically detects the provider from the model string and routes
    to the appropriate backend.
    """
    pc = get_provider_config(model)

    if pc.provider == ProviderType.OLLAMA:
        async for chunk in stream_ollama(
            messages, system_prompt, pc.model_name, pc.base_url, tools, **kwargs
        ):
            yield chunk

    elif pc.provider == ProviderType.OPENAI:
        async for chunk in stream_openai_compat(
            messages, system_prompt, pc.model_name, pc.base_url, pc.api_key, tools, **kwargs
        ):
            yield chunk

    elif pc.provider == ProviderType.LLAMACPP:
        async for chunk in stream_llamacpp(
            messages, system_prompt, pc.model_name, pc.base_url, **kwargs
        ):
            yield chunk

    elif pc.provider == ProviderType.WEIGHTS:
        from lucy.api.weights_provider import WeightsProvider
        provider = WeightsProvider(pc.model_name)
        async for chunk in provider.stream(messages, system_prompt, **kwargs):
            yield chunk

    elif pc.provider == ProviderType.LOCAL:
        # Try Ollama first, then OpenAI-compat
        found = False
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{pc.base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    if resp.status == 200:
                        found = True
        except Exception:
            pass

        if found:
            async for chunk in stream_ollama(
                messages, system_prompt, pc.model_name, pc.base_url, tools, **kwargs
            ):
                yield chunk
        else:
            # Try OpenAI-compat on common ports
            for port in [1234, 8080, 5000, 3000]:
                try:
                    base = f"http://localhost:{port}/v1"
                    async for chunk in stream_openai_compat(
                        messages, system_prompt, pc.model_name, base, "not-needed", tools, **kwargs
                    ):
                        yield chunk
                    return
                except Exception:
                    continue
            yield {"type": "error", "error": "No local LLM server found. Start Ollama or LM Studio."}


async def check_local_server(model: str = "ollama:llama3") -> dict[str, Any]:
    """Check if a local model server is running and available."""
    pc = get_provider_config(model)
    result = {"provider": pc.provider, "model": pc.model_name, "available": False}

    try:
        import aiohttp

        if pc.provider == ProviderType.OLLAMA:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{pc.base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=3)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m["name"] for m in data.get("models", [])]
                        result["available"] = True
                        result["models"] = models
                        result["model_loaded"] = pc.model_name in models or any(
                            pc.model_name in m for m in models
                        )

        elif pc.provider in (ProviderType.OPENAI, ProviderType.LLAMACPP):
            url = f"{pc.base_url}/models" if pc.provider == ProviderType.OPENAI else f"{pc.base_url}/v1/models"
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=3)
                ) as resp:
                    result["available"] = resp.status == 200
    except ImportError:
        result["error"] = "aiohttp not installed (pip install aiohttp)"
    except Exception as e:
        result["error"] = str(e)

    return result
