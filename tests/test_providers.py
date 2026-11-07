"""
Comprehensive unit tests for the Universal LLM Provider System.
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from typing import Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lucy.api.client import stream_query
from lucy.api.models import (
    calculate_cost,
    get_context_window,
    get_max_output_tokens,
    get_model_info,
    is_free_model,
    is_offline_model,
    resolve_model,
    supports_thinking,
)
from lucy.api.providers import (
    AnthropicProvider,
    DeepSeekProvider,
    FireworksProvider,
    GeminiProvider,
    GroqProvider,
    LLMProvider,
    LlamaCppProvider,
    MistralProvider,
    OllamaProvider,
    OpenAICompatProvider,
    OpenAIProvider,
    OpenRouterProvider,
    ProviderCapabilities,
    ProviderConfig,
    ProviderInfo,
    ProviderRegistry,
    ProviderType,
    TogetherProvider,
    WeightsLLMProvider,
    detect_from_env,
    detect_provider,
    get_provider,
    get_provider_config,
    get_registry,
    list_providers,
    register_provider,
)
from lucy.core.config import Config, load_config
from lucy.core.message import (
    AssistantMessage,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    create_user_message,
)


class TestProviderRegistry(unittest.TestCase):
    """Tests for ProviderRegistry and model-to-provider routing."""

    def setUp(self) -> None:
        self.registry = get_registry()

    def test_registered_providers_count(self) -> None:
        providers = list_providers()
        self.assertGreaterEqual(len(providers), 12)
        names = [p.name for p in providers]
        expected = [
            "anthropic",
            "openai",
            "gemini",
            "groq",
            "mistral",
            "deepseek",
            "openrouter",
            "together",
            "fireworks",
            "ollama",
            "openai_compat",
            "llamacpp",
            "weights",
        ]
        for exp in expected:
            self.assertIn(exp, names)

    def test_model_resolution(self) -> None:
        # OpenAI models and aliases
        self.assertEqual(resolve_model("gpt4"), "openai:gpt-4o")
        self.assertEqual(resolve_model("gpt4o"), "openai:gpt-4o")
        self.assertEqual(resolve_model("gpt-4o"), "openai:gpt-4o")
        self.assertEqual(resolve_model("o1"), "openai:o1")
        self.assertEqual(resolve_model("o3"), "openai:o3")
        self.assertEqual(resolve_model("o3-mini"), "openai:o3-mini")

        # Gemini models and aliases
        self.assertEqual(resolve_model("gemini"), "gemini:gemini-3.1-flash-lite")
        self.assertEqual(resolve_model("gemini-pro"), "gemini:gemini-pro-latest")

        # Groq, Mistral, DeepSeek aliases
        self.assertEqual(resolve_model("groq"), "groq:llama-3.3-70b-versatile")
        self.assertEqual(resolve_model("codestral"), "mistral:codestral-latest")
        self.assertEqual(resolve_model("deepseek-r1"), "deepseek:deepseek-reasoner")

    def test_provider_detection(self) -> None:
        self.assertEqual(get_provider("openai:gpt-4o").name, "openai")
        self.assertEqual(get_provider("gemini:gemini-2.5-flash").name, "gemini")
        self.assertEqual(get_provider("groq:llama-3.3-70b-versatile").name, "groq")
        self.assertEqual(get_provider("mistral:codestral-latest").name, "mistral")
        self.assertEqual(get_provider("deepseek:deepseek-reasoner").name, "deepseek")
        self.assertEqual(get_provider("ollama:llama3.1").name, "ollama")
        self.assertEqual(get_provider("openrouter:auto").name, "openrouter")
        self.assertEqual(get_provider("together:meta-llama/Llama-3.3-70B-Instruct-Turbo").name, "together")
        self.assertEqual(get_provider("fireworks:accounts/fireworks/models/llama-v3p3-70b-instruct").name, "fireworks")
        self.assertEqual(get_provider("llama:codellama").name, "llamacpp")
        self.assertEqual(get_provider("weights:/tmp/model.gguf").name, "weights")

    def test_detect_from_env(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-test-12345"
        os.environ["MISTRAL_API_KEY"] = "mistral-key-123"
        detected = detect_from_env()
        self.assertIn("openai", detected)
        self.assertIn("mistral", detected)

    def test_hot_swap_provider(self) -> None:
        class HotSwappedProvider(LLMProvider):
            name = "custom_test"

            def get_capabilities(self, model: str) -> ProviderCapabilities:
                return ProviderCapabilities()

            def translate_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
                return tools

            def translate_messages(
                self, messages: list[dict[str, Any]], system_prompt: str | None = None
            ) -> list[dict[str, Any]]:
                return messages

            async def stream(self, *args: Any, **kwargs: Any):
                yield {"type": "text_delta", "text": "hot-swapped"}
                yield {"type": "done", "model": "custom"}

        register_provider(
            "custom_test",
            HotSwappedProvider(),
            display_name="Custom Test Provider",
            prefixes=["custom-test"],
        )
        resolved = get_provider("custom-test:my-model")
        self.assertEqual(resolved.name, "custom_test")


class TestProviderTranslations(unittest.TestCase):
    """Tests for tool and message translation across different LLM formats."""

    def setUp(self) -> None:
        self.tools = [
            {
                "name": "edit_file",
                "description": "Edit a file on disk",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            }
        ]

    def test_openai_tool_translation(self) -> None:
        provider = OpenAIProvider()
        oai_tools = provider.translate_tools(self.tools)
        self.assertEqual(len(oai_tools), 1)
        self.assertEqual(oai_tools[0]["type"], "function")
        self.assertEqual(oai_tools[0]["function"]["name"], "edit_file")
        self.assertIn("properties", oai_tools[0]["function"]["parameters"])

    def test_gemini_tool_translation(self) -> None:
        provider = GeminiProvider()
        gemini_tools = provider.translate_tools(self.tools)
        self.assertEqual(len(gemini_tools), 1)
        self.assertIn("functionDeclarations", gemini_tools[0])
        self.assertEqual(gemini_tools[0]["functionDeclarations"][0]["name"], "edit_file")

    def test_openai_message_translation(self) -> None:
        provider = OpenAIProvider()
        messages = [
            {"role": "user", "content": "Please write hello.py"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I will create hello.py"},
                    {
                        "type": "tool_use",
                        "id": "call_123",
                        "name": "edit_file",
                        "input": {"path": "hello.py", "content": "print('hello')"},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_123",
                        "content": "File written successfully",
                    }
                ],
            },
        ]
        translated = provider.translate_messages(messages, system_prompt="You are LucyCode.")
        self.assertEqual(translated[0]["role"], "system")
        self.assertEqual(translated[0]["content"], "You are LucyCode.")
        self.assertEqual(translated[1]["role"], "user")
        self.assertEqual(translated[2]["role"], "assistant")
        self.assertEqual(len(translated[2]["tool_calls"]), 1)
        self.assertEqual(translated[2]["tool_calls"][0]["id"], "call_123")
        self.assertEqual(translated[3]["role"], "tool")
        self.assertEqual(translated[3]["tool_call_id"], "call_123")

    def test_gemini_message_translation(self) -> None:
        provider = GeminiProvider()
        messages = [
            {"role": "user", "content": "Hello Gemini"},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call_456",
                        "name": "edit_file",
                        "input": {"path": "test.txt", "content": "hi"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_456",
                        "content": "OK",
                    }
                ],
            },
        ]
        translated = provider.translate_messages(messages, system_prompt="System instructions")
        self.assertEqual(translated[0]["role"], "user")
        self.assertEqual(translated[1]["role"], "model")
        self.assertIn("functionCall", translated[1]["parts"][0])
        self.assertEqual(translated[2]["role"], "user")
        self.assertIn("functionResponse", translated[2]["parts"][0])


class TestCapabilitiesAndModels(unittest.TestCase):
    """Tests for model capabilities, pricing, and offline detection."""

    def test_model_capabilities(self) -> None:
        openai_p = OpenAIProvider()
        caps_o1 = openai_p.get_capabilities("o1")
        self.assertTrue(caps_o1.supports_thinking)
        self.assertTrue(caps_o1.supports_vision)

        caps_4o = openai_p.get_capabilities("gpt-4o")
        self.assertFalse(caps_4o.supports_thinking)
        self.assertTrue(caps_4o.supports_vision)

        gemini_p = GeminiProvider()
        caps_gemini = gemini_p.get_capabilities("gemini-2.5-pro")
        self.assertTrue(caps_gemini.supports_thinking)
        self.assertEqual(caps_gemini.max_context_window, 2_000_000)

        deepseek_p = DeepSeekProvider()
        caps_r1 = deepseek_p.get_capabilities("deepseek-reasoner")
        self.assertTrue(caps_r1.supports_thinking)

    def test_pricing_and_costs(self) -> None:
        # Claude Sonnet 4: $3 in / $15 out
        cost = calculate_cost("claude-sonnet-4-20250514", input_tokens=1_000_000, output_tokens=1_000_000)
        self.assertAlmostEqual(cost, 18.0)

        # GPT-4o: $2.50 in / $10.00 out
        cost_4o = calculate_cost("openai:gpt-4o", input_tokens=1_000_000, output_tokens=1_000_000)
        self.assertAlmostEqual(cost_4o, 12.50)

        # Ollama local is free
        self.assertTrue(is_offline_model("ollama:llama3.1"))
        self.assertTrue(is_free_model("ollama:llama3.1"))
        self.assertEqual(calculate_cost("ollama:llama3.1", 1_000_000, 1_000_000), 0.0)


class TestBackwardCompatibility(unittest.TestCase):
    """Verify that existing providers.py exports work unchanged."""

    def test_detect_provider(self) -> None:
        pt, mn = detect_provider("ollama:llama3.1")
        self.assertEqual(pt, ProviderType.OLLAMA)
        self.assertEqual(mn, "llama3.1")

        pt, mn = detect_provider("openai:gpt-4o")
        self.assertEqual(pt, ProviderType.OPENAI)
        self.assertEqual(mn, "gpt-4o")

        pt, mn = detect_provider("gemini:gemini-2.5-flash")
        self.assertEqual(pt, ProviderType.GEMINI)
        self.assertEqual(mn, "gemini-2.5-flash")

    def test_provider_config(self) -> None:
        cfg = get_provider_config("ollama:llama3.1")
        self.assertEqual(cfg.provider, ProviderType.OLLAMA)
        self.assertEqual(cfg.model_name, "llama3.1")
        self.assertIn("11434", cfg.base_url)


class TestStreamQueryPipeline(unittest.TestCase):
    """Verify that stream_query properly coordinates with providers and produces StreamEvents."""

    def test_mock_streaming_query(self) -> None:
        class PipelineMockProvider(LLMProvider):
            name = "pipeline_mock"

            def get_capabilities(self, model: str) -> ProviderCapabilities:
                return ProviderCapabilities(supports_thinking=True)

            def translate_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
                return tools

            def translate_messages(
                self, messages: list[dict[str, Any]], system_prompt: str | None = None
            ) -> list[dict[str, Any]]:
                return messages

            async def stream(self, *args: Any, **kwargs: Any):
                yield {"type": "thinking_delta", "thinking": "Thinking about the task..."}
                yield {"type": "text_delta", "text": "Here is the response."}
                yield {
                    "type": "tool_use",
                    "id": "t_01",
                    "name": "edit_file",
                    "input": {"path": "foo.py", "content": "123"},
                }
                yield {
                    "type": "done",
                    "model": "pipeline-mock-v1",
                    "prompt_eval_count": 50,
                    "eval_count": 100,
                }

        register_provider(
            "pipeline_mock",
            PipelineMockProvider(),
            prefixes=["pipelinemock"],
        )

        async def run_query():
            events = []
            async for ev in stream_query(
                messages=[create_user_message("Run tool")],
                system_prompt="Test system prompt",
                model="pipelinemock:test",
            ):
                events.append(ev)
            return events

        events = asyncio.run(run_query())
        self.assertEqual(len(events), 5)
        self.assertIsInstance(events[0], StreamEvent)
        self.assertEqual(events[0].type, "thinking_delta")
        self.assertEqual(events[0].data["thinking"], "Thinking about the task...")

        self.assertIsInstance(events[1], StreamEvent)
        self.assertEqual(events[1].type, "text_delta")
        self.assertEqual(events[1].data["text"], "Here is the response.")

        self.assertIsInstance(events[2], StreamEvent)
        self.assertEqual(events[2].type, "tool_use_start")

        self.assertIsInstance(events[3], StreamEvent)
        self.assertEqual(events[3].type, "tool_use_complete")

        final_msg = events[-1]
        self.assertIsInstance(final_msg, AssistantMessage)
        self.assertEqual(final_msg.get_text(), "Here is the response.")
        self.assertEqual(final_msg.get_thinking_text(), "Thinking about the task...")
        self.assertEqual(len(final_msg.get_tool_use_blocks()), 1)
        self.assertEqual(final_msg.usage.input_tokens, 50)
        self.assertEqual(final_msg.usage.output_tokens, 100)


if __name__ == "__main__":
    unittest.main()
