"""
Voice mode — microphone input, transcription, and text-to-speech.

Pipeline: mic → VAD → transcribe → query → synthesize → speaker

Optional dependencies:
  - sounddevice (microphone capture)
  - numpy (audio processing)
  - whisper or openai (transcription)
  - pyttsx3 or macOS 'say' (TTS)
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class VoiceState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"


@dataclass
class VoiceConfig:
    """Voice mode configuration."""
    sample_rate: int = 16000
    channels: int = 1
    chunk_duration: float = 0.5      # seconds per audio chunk
    silence_threshold: float = 0.01  # VAD threshold
    silence_duration: float = 1.5    # seconds of silence to stop
    max_recording_seconds: float = 60.0
    whisper_model: str = "base"      # tiny, base, small, medium, large
    tts_engine: str = "auto"         # auto, say, espeak, pyttsx3
    language: str = "en"


class VoiceInput:
    """Record audio from the microphone."""

    def __init__(self, config: VoiceConfig | None = None):
        self.config = config or VoiceConfig()
        self._recording = False

    def is_available(self) -> bool:
        """Check if audio recording is available."""
        try:
            import sounddevice  # noqa: F401
            return True
        except ImportError:
            return False

    async def record_until_silence(self) -> bytes | None:
        """Record audio until silence is detected (VAD)."""
        if not self.is_available():
            logger.warning("sounddevice not installed — voice input unavailable")
            return None

        import numpy as np
        import sounddevice as sd

        cfg = self.config
        chunk_samples = int(cfg.sample_rate * cfg.chunk_duration)
        max_chunks = int(cfg.max_recording_seconds / cfg.chunk_duration)
        silence_chunks = int(cfg.silence_duration / cfg.chunk_duration)

        frames: list[bytes] = []
        consecutive_silence = 0
        self._recording = True

        def _record_sync():
            nonlocal consecutive_silence
            for _ in range(max_chunks):
                if not self._recording:
                    break
                audio = sd.rec(
                    chunk_samples, samplerate=cfg.sample_rate,
                    channels=cfg.channels, dtype="int16",
                )
                sd.wait()

                frames.append(audio.tobytes())

                # VAD: check RMS energy
                rms = np.sqrt(np.mean(audio.astype(float) ** 2)) / 32768.0
                if rms < cfg.silence_threshold:
                    consecutive_silence += 1
                    if consecutive_silence >= silence_chunks and len(frames) > 2:
                        break
                else:
                    consecutive_silence = 0

        await asyncio.get_event_loop().run_in_executor(None, _record_sync)
        self._recording = False

        if not frames:
            return None

        return b"".join(frames)

    async def record_push_to_talk(self, stop_event: asyncio.Event) -> bytes | None:
        """Record audio until stop_event is set (push-to-talk)."""
        if not self.is_available():
            return None

        import sounddevice as sd

        cfg = self.config
        chunk_samples = int(cfg.sample_rate * cfg.chunk_duration)
        frames: list[bytes] = []
        self._recording = True

        def _record_sync():
            while not stop_event.is_set() and self._recording:
                audio = sd.rec(
                    chunk_samples, samplerate=cfg.sample_rate,
                    channels=cfg.channels, dtype="int16",
                )
                sd.wait()
                frames.append(audio.tobytes())

        await asyncio.get_event_loop().run_in_executor(None, _record_sync)
        self._recording = False

        return b"".join(frames) if frames else None

    def stop(self):
        self._recording = False


class VoiceTranscriber:
    """Transcribe audio to text."""

    def __init__(self, config: VoiceConfig | None = None):
        self.config = config or VoiceConfig()

    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio bytes to text."""
        # Try local whisper first
        result = await self._transcribe_local_whisper(audio_data)
        if result:
            return result

        # Fallback: use whisper CLI if available
        result = await self._transcribe_whisper_cli(audio_data)
        if result:
            return result

        return ""

    async def _transcribe_local_whisper(self, audio_data: bytes) -> str | None:
        """Transcribe using local whisper Python library."""
        try:
            import whisper
        except ImportError:
            return None

        # Write to temp WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name
            self._write_wav(f, audio_data)

        try:
            model = whisper.load_model(self.config.whisper_model)
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: model.transcribe(wav_path, language=self.config.language)
            )
            return result.get("text", "").strip()
        except Exception as e:
            logger.warning("Whisper transcription failed: %s", e)
            return None
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    async def _transcribe_whisper_cli(self, audio_data: bytes) -> str | None:
        """Transcribe using whisper CLI (whisper.cpp or openai-whisper)."""
        whisper_cmd = shutil.which("whisper")
        if not whisper_cmd:
            return None

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name
            self._write_wav(f, audio_data)

        try:
            proc = await asyncio.create_subprocess_exec(
                whisper_cmd, wav_path,
                "--language", self.config.language,
                "--model", self.config.whisper_model,
                "--output_format", "txt",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            return stdout.decode("utf-8", errors="replace").strip()
        except Exception as e:
            logger.warning("Whisper CLI failed: %s", e)
            return None
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    def _write_wav(self, f, audio_data: bytes) -> None:
        """Write raw audio to WAV format."""
        cfg = self.config
        with wave.open(f, "wb") as wav:
            wav.setnchannels(cfg.channels)
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(cfg.sample_rate)
            wav.writeframes(audio_data)


class VoiceSynthesizer:
    """Text-to-speech output."""

    def __init__(self, config: VoiceConfig | None = None):
        self.config = config or VoiceConfig()
        self._speaking = False

    async def speak(self, text: str) -> bool:
        """Speak text aloud."""
        engine = self.config.tts_engine

        if engine == "auto":
            if platform.system() == "Darwin":
                engine = "say"
            elif shutil.which("espeak"):
                engine = "espeak"
            else:
                engine = "pyttsx3"

        self._speaking = True
        try:
            if engine == "say":
                return await self._speak_macos(text)
            elif engine == "espeak":
                return await self._speak_espeak(text)
            elif engine == "pyttsx3":
                return await self._speak_pyttsx3(text)
            return False
        finally:
            self._speaking = False

    async def _speak_macos(self, text: str) -> bool:
        """Use macOS 'say' command."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "say", text,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode == 0
        except Exception:
            return False

    async def _speak_espeak(self, text: str) -> bool:
        """Use espeak for TTS."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "espeak", text,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode == 0
        except Exception:
            return False

    async def _speak_pyttsx3(self, text: str) -> bool:
        """Use pyttsx3 for TTS."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: (engine.say(text), engine.runAndWait())
            )
            return True
        except ImportError:
            logger.warning("pyttsx3 not installed")
            return False
        except Exception as e:
            logger.warning("pyttsx3 failed: %s", e)
            return False

    def stop(self):
        self._speaking = False


class VoiceMode:
    """Integrated voice mode pipeline."""

    def __init__(self, config: VoiceConfig | None = None):
        self.config = config or VoiceConfig()
        self.input = VoiceInput(self.config)
        self.transcriber = VoiceTranscriber(self.config)
        self.synthesizer = VoiceSynthesizer(self.config)
        self.state = VoiceState.IDLE
        self._on_state_change: Callable[[VoiceState], None] | None = None

    def is_available(self) -> bool:
        return self.input.is_available()

    def set_state(self, state: VoiceState) -> None:
        self.state = state
        if self._on_state_change:
            self._on_state_change(state)

    async def listen_and_transcribe(self) -> str:
        """Record audio and transcribe to text."""
        self.set_state(VoiceState.LISTENING)
        audio = await self.input.record_until_silence()

        if not audio:
            self.set_state(VoiceState.IDLE)
            return ""

        self.set_state(VoiceState.TRANSCRIBING)
        text = await self.transcriber.transcribe(audio)

        self.set_state(VoiceState.IDLE)
        return text

    async def speak_response(self, text: str) -> None:
        """Speak a response."""
        self.set_state(VoiceState.SPEAKING)
        await self.synthesizer.speak(text)
        self.set_state(VoiceState.IDLE)

    def get_status(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "available": self.is_available(),
            "tts_engine": self.config.tts_engine,
            "whisper_model": self.config.whisper_model,
        }
