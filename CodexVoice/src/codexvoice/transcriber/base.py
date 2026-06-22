"""Transcription interface."""

from __future__ import annotations

from typing import Protocol

from codexvoice.config import TranscriptionConfig
from codexvoice.types import AudioBuffer, Transcript


class LocalTranscriber(Protocol):
    config: TranscriptionConfig

    def transcribe(self, audio: AudioBuffer, prompt: str | None = None) -> Transcript: ...
    def warmup(self) -> None: ...

