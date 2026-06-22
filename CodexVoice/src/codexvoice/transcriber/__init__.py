"""Local transcription engines."""

from __future__ import annotations

from codexvoice.config import TranscriptionConfig
from codexvoice.transcriber.base import LocalTranscriber
from codexvoice.transcriber.faster_whisper_engine import FasterWhisperTranscriber
from codexvoice.transcriber.fake import FakeTranscriber
from codexvoice.types import TranscriberUnavailable


def create_transcriber(config: TranscriptionConfig) -> LocalTranscriber:
    if config.engine == "fake":
        return FakeTranscriber(config)
    if config.engine in ("auto", "faster-whisper"):
        return FasterWhisperTranscriber(config)
    if config.engine == "mlx":
        raise TranscriberUnavailable("MLX Whisper is reserved for a later spike; use faster-whisper for MVP")
    raise TranscriberUnavailable(f"Unsupported transcription engine: {config.engine}")

