"""
Direct model weight loader using llama-cpp-python or Transformers.

Provides a unified interface for loading:
1. GGUF files (via llama-cpp-python)
2. Hugging Face directories / .safetensors (via transformers + torch)
"""

from __future__ import annotations

import asyncio
import logging
import os
import queue
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)

# Global cache to keep models in memory across requests
_MODEL_CACHE: dict[str, Any] = {}

class WeightsProvider:
    """Dispatcher for direct model weight loading."""

    def __init__(self, model_path: str):
        self.model_path = os.path.abspath(model_path)

    def _get_impl(self):
        """Detect model type and return appropriate provider implementation from cache."""
        if self.model_path in _MODEL_CACHE:
            return _MODEL_CACHE[self.model_path]

        impl: Any = None
        # Detect Hugging Face directory
        if os.path.isdir(self.model_path):
            hf_markers = ["config.json", "model.safetensors", "pytorch_model.bin", "tokenizer_config.json"]
            if any(os.path.exists(os.path.join(self.model_path, m)) for m in hf_markers):
                impl = TransformersProvider(self.model_path)
        
        if not impl:
            # Default to GGUF
            impl = GGUFProvider(self.model_path)
            
        _MODEL_CACHE[self.model_path] = impl
        return impl

    async def stream(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        **kwargs,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a chat completion from the detected backend."""
        try:
            impl = self._get_impl()
            async for event in impl.stream(messages, system_prompt, **kwargs):
                yield event
        except Exception as e:
            logger.error(f"Model error: {e}")
            yield {"type": "error", "error": f"Failed to load or run model: {e}"}


class GGUFProvider:
    """Provider for GGUF files using llama-cpp-python."""

    def __init__(self, model_path: str):
        self.model_path = model_path
        self._llm = None

    def _get_llm(self, **kwargs):
        if self._llm: return self._llm
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError("llama-cpp-python not installed. Run: pip install lucycode[local]")

        n_gpu_layers = kwargs.get("n_gpu_layers", -1 if "METAL" in os.environ or "CUDA" in os.environ else 0)
        self._llm = Llama(
            model_path=self.model_path,
            n_ctx=kwargs.get("n_ctx", 8192),
            n_gpu_layers=n_gpu_layers,
            verbose=False,
            chat_format=kwargs.get("chat_format", "chatml"),
        )
        return self._llm

    async def stream(self, messages, system_prompt, **kwargs):
        loop = asyncio.get_running_loop()
        api_messages = [{"role": "system", "content": system_prompt}] + messages

        def sync_stream():
            llm = self._get_llm(**kwargs)
            return llm.create_chat_completion(
                messages=api_messages,
                stream=True,
                max_tokens=kwargs.get("max_tokens", 4096),
                temperature=kwargs.get("temperature", 0.1),
            )

        stream_iter = await loop.run_in_executor(None, sync_stream)
        full_text = ""
        for chunk in stream_iter:
            content = chunk["choices"][0].get("delta", {}).get("content", "")
            if content:
                full_text += content
                yield {"type": "text_delta", "text": content}
            if chunk["choices"][0].get("finish_reason"): break
        yield {"type": "done", "text": full_text, "model": self.model_path}


class ThreadSafeStreamer:
    """Queue-based streamer to bridge synchronous thread to async generator."""
    def __init__(self, timeout: float = 30.0):
        self.queue = queue.Queue()
        self.timeout = timeout
        self.stop_signal = object()

    def put(self, value):
        self.queue.put(value)

    def end(self):
        self.queue.put(self.stop_signal)

    def __iter__(self):
        return self

    def __next__(self):
        val = self.queue.get(timeout=self.timeout)
        if val is self.stop_signal:
            raise StopIteration
        return val


class TransformersProvider:
    """Provider for Hugging Face models using transformers + torch (MPS supported)."""

    def __init__(self, model_path: str):
        self.model_path = model_path
        self._model = None
        self._tokenizer = None

    def _load(self):
        if self._model: return
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, AutoConfig
        
        device = "cpu"
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
            
        logger.info(f"Loading HF model from {self.model_path} onto {device}...")
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        
        try:
            config = AutoConfig.from_pretrained(self.model_path)
            model_type = getattr(config, "model_type", "").lower()
        except:
            model_type = ""

        # Fallback template if missing
        if self._tokenizer.chat_template is None:
            if "llama" in model_type or "llama" in self.model_path.lower():
                logger.info("Injecting Llama-3 fallback template.")
                self._tokenizer.chat_template = (
                    "{% set loop_messages = messages %}"
                    "{% for message in loop_messages %}"
                    "{% set content = '<|start_header_id|>' + message['role'] + '<|end_header_id|>\\n\\n' + message['content'] | trim + '<|eot_id|>' %}"
                    "{% if loop.index0 == 0 %}{% set content = bos_token + content %}{% endif %}"
                    "{{ content }}"
                    "{% endfor %}"
                    "{% if add_generation_prompt %}{{ '<|start_header_id|>assistant<|end_header_id|>\\n\\n' }}{% endif %}"
                )
            elif "phi" in model_type or "phi" in self.model_path.lower():
                logger.info("Injecting Phi fallback template (Instruct/Output).")
                self._tokenizer.chat_template = (
                    "{% for message in messages %}"
                    "{{ 'Instruct: ' + message['content'] + '\\n' if message['role'] == 'user' else 'Output: ' + message['content'] + '\\n' }}"
                    "{% endfor %}"
                    "{% if add_generation_prompt %}{{ 'Output: ' }}{% endif %}"
                )
            else:
                logger.info("Injecting Generic fallback template.")
                self._tokenizer.chat_template = (
                    "{% for message in messages %}"
                    "{{ message['role'].capitalize() + ': ' + message['content'] + '\\n' }}"
                    "{% endfor %}"
                    "{% if add_generation_prompt %}{{ 'Assistant: ' }}{% endif %}"
                )

        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            dtype=torch.float16 if device != "cpu" else torch.float32,
            device_map=device,
            low_cpu_mem_usage=True,
        )

    async def stream(self, messages, system_prompt, **kwargs):
        self._load()
        from transformers import TextIteratorStreamer
        from threading import Thread

        # Use the official chat template
        api_messages = [{"role": "system", "content": system_prompt}] + messages
        prompt = self._tokenizer.apply_chat_template(
            api_messages,
            tokenize=False,
            add_generation_prompt=True
        )

        inputs = self._tokenizer([prompt], return_tensors="pt").to(self._model.device)
        # Generalized: Do not skip special tokens or start-tokens early; we'll filter manually
        # This prevents Phi-1 from skipping its first few important formatting characters.
        streamer = TextIteratorStreamer(self._tokenizer, skip_prompt=True, skip_special_tokens=False)
        
        # Determine EOS tokens
        eos_token_id = [self._tokenizer.eos_token_id]
        special_ids = set([self._tokenizer.pad_token_id, self._tokenizer.eos_token_id, self._tokenizer.bos_token_id])
        
        for token in ["<|endoftext|>", "<|eot_id|>", "<|end_of_text|>", "</s>"]:
            if token in self._tokenizer.all_special_tokens:
                eid = self._tokenizer.convert_tokens_to_ids(token)
                if eid not in eos_token_id:
                    eos_token_id.append(eid)
                special_ids.add(eid)

        if self._model.config.pad_token_id is None:
            self._model.config.pad_token_id = eos_token_id[0]

        generation_kwargs = dict(
            inputs,
            streamer=streamer,
            max_new_tokens=kwargs.get("max_tokens", 4096),
            do_sample=True,
            temperature=kwargs.get("temperature", 0.1),
            eos_token_id=eos_token_id,
            pad_token_id=self._model.config.pad_token_id,
            repetition_penalty=1.1,
        )

        # Run generation in a background thread to keep event loop free
        thread = Thread(target=self._model.generate, kwargs=generation_kwargs)
        thread.start()

        full_text = ""
        loop = asyncio.get_running_loop()
        
        # Async-friendly iteration over the streamer
        def get_next():
            try:
                return next(streamer)
            except StopIteration:
                return None

        while thread.is_alive() or not streamer.text_queue.empty():
            new_text = await loop.run_in_executor(None, get_next)
            if new_text is None:
                break
            
            # Filter common system tokens if skip_special_tokens is False
            clean_text = new_text
            for token in self._tokenizer.all_special_tokens:
                if token in clean_text:
                    clean_text = clean_text.replace(token, "")

            if clean_text:
                full_text += clean_text
                yield {"type": "text_delta", "text": clean_text}
            
        yield {"type": "done", "text": full_text, "model": self.model_path}
