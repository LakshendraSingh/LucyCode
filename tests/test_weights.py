"""
Unit tests for connecting directly to model weights (GGUF / Hugging Face Safetensors).
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from lucy.api.models import resolve_model, get_model_info, is_offline_model
from lucy.api.providers.registry import get_provider
from lucy.api.providers.weights_provider import WeightsLLMProvider
from lucy.api.weights_provider import WeightsProvider, GGUFProvider, TransformersProvider
from lucy.core.commands import WeightsCommand, ModelsCommand
from lucy.core.config import Config, load_config
from lucy.core.state import AppState
from lucy.main import cli


class TestDirectModelWeights(unittest.TestCase):
    """Test suite for direct model weight loading options."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.gguf_file = os.path.join(self.temp_dir.name, "test_model.gguf")
        with open(self.gguf_file, "wb") as f:
            f.write(b"GGUF_TEST_BYTES")

        self.hf_dir = os.path.join(self.temp_dir.name, "hf_model")
        os.makedirs(self.hf_dir, exist_ok=True)
        with open(os.path.join(self.hf_dir, "config.json"), "w") as f:
            f.write('{"model_type": "llama"}')
        with open(os.path.join(self.hf_dir, "model.safetensors"), "wb") as f:
            f.write(b"SAFETENSORS_BYTES")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_resolve_model_with_weights_prefix(self):
        res = resolve_model(f"weights:{self.gguf_file}")
        self.assertEqual(res, f"weights:{os.path.abspath(self.gguf_file)}")

    def test_resolve_model_with_direct_files(self):
        # Direct .gguf file
        res_gguf = resolve_model(self.gguf_file)
        self.assertEqual(res_gguf, f"weights:{os.path.abspath(self.gguf_file)}")

        # Direct HF directory
        res_hf = resolve_model(self.hf_dir)
        self.assertEqual(res_hf, f"weights:{os.path.abspath(self.hf_dir)}")

    def test_is_offline_and_model_info_for_weights(self):
        weights_id = f"weights:{self.gguf_file}"
        self.assertTrue(is_offline_model(weights_id))

        info = get_model_info(weights_id)
        self.assertIsNotNone(info)
        self.assertEqual(info.input_price_per_mtok, 0.0)
        self.assertEqual(info.output_price_per_mtok, 0.0)
        self.assertIn("test_model.gguf", info.name)

    def test_provider_detection_for_weights(self):
        p1 = get_provider(f"weights:{self.gguf_file}")
        self.assertEqual(p1.name, "weights")

        p2 = get_provider(self.gguf_file)
        self.assertEqual(p2.name, "weights")

        p3 = get_provider(self.hf_dir)
        self.assertEqual(p3.name, "weights")

    def test_weights_provider_dispatch(self):
        # GGUF file dispatches to GGUFProvider
        wp_gguf = WeightsProvider(self.gguf_file)
        impl_gguf = wp_gguf._get_impl()
        self.assertIsInstance(impl_gguf, GGUFProvider)

        # HF directory dispatches to TransformersProvider
        wp_hf = WeightsProvider(self.hf_dir)
        impl_hf = wp_hf._get_impl()
        self.assertIsInstance(impl_hf, TransformersProvider)

        # Non-existent file raises FileNotFoundError
        wp_nonexistent = WeightsProvider(os.path.join(self.temp_dir.name, "missing.gguf"))
        with self.assertRaises(FileNotFoundError):
            wp_nonexistent._get_impl()

    def test_weights_llm_provider_message_translation(self):
        provider = WeightsLLMProvider()
        messages = [
            {"role": "user", "content": "Hello"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Part 1"},
                    {"type": "text", "text": "Part 2"},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "content": "Result 42"},
                ],
            },
        ]
        translated = provider.translate_messages(messages, "System text")
        self.assertEqual(len(translated), 3)
        self.assertEqual(translated[0]["content"], "Hello")
        self.assertEqual(translated[1]["content"], "Part 1\nPart 2")
        self.assertIn("Result 42", translated[2]["content"])

    async def _run_command(self, cmd, args, state):
        return await cmd.execute(args, state)

    def test_weights_slash_command(self):
        import asyncio
        cmd = WeightsCommand()
        state = AppState(model="claude-sonnet-4-20250514")

        # 1. No args - show usage
        res = asyncio.run(self._run_command(cmd, "", state))
        self.assertIn("Usage: /weights", res.output)

        # 2. Invalid path
        bad_path = os.path.join(self.temp_dir.name, "does_not_exist.gguf")
        res_bad = asyncio.run(self._run_command(cmd, bad_path, state))
        self.assertIsNotNone(res_bad.error)
        self.assertIn("not found", res_bad.error)

        # 3. Valid GGUF path
        res_ok = asyncio.run(self._run_command(cmd, self.gguf_file, state))
        self.assertIn("Connected directly to model weights", res_ok.output)
        self.assertEqual(state.model, f"weights:{os.path.abspath(self.gguf_file)}")

        # 4. No args after connected - show current connected weights
        res_curr = asyncio.run(self._run_command(cmd, "", state))
        self.assertIn("Currently connected to model weights", res_curr.output)

    def test_models_command_lists_weights(self):
        import asyncio
        cmd = ModelsCommand()
        state = AppState(model="claude-sonnet-4-20250514")
        res = asyncio.run(self._run_command(cmd, "", state))
        self.assertIn("Direct Model Weights", res.output)
        self.assertIn("/weights", res.output)

    def test_config_env_weights_path(self):
        with patch.dict(os.environ, {"LUCY_WEIGHTS": self.gguf_file}, clear=False):
            cfg = load_config()
            self.assertEqual(cfg.weights_path, self.gguf_file)
            self.assertEqual(cfg.model, f"weights:{os.path.abspath(self.gguf_file)}")

    def test_cli_weights_flag_invalid(self):
        runner = CliRunner()
        bad_path = os.path.join(self.temp_dir.name, "not_found.gguf")
        result = runner.invoke(cli, ["-w", bad_path, "-p", "hello"])
        self.assertIn("Model weights path not found", result.output)

    def test_cli_weights_flag_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--weights", result.output)
        self.assertIn("Direct path to model weights", result.output)


if __name__ == "__main__":
    unittest.main()

