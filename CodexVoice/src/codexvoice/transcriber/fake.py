"""Test transcription engine."""

from __future__ import annotations

from codexvoice.config import TranscriptionConfig
from codexvoice.types import AudioBuffer, Transcript


class FakeTranscriber:
    def __init__(self, config: TranscriptionConfig, text: str = "测试文本") -> None:
        self.config = config
        self.text = text

    def warmup(self) -> None:
        return None

    def transcribe(self, audio: AudioBuffer, prompt: str | None = None) -> Transcript:
        return Transcript(
            text=self.text,
            language=self.config.language,
            duration_sec=audio.duration_sec,
            model=f"fake:{self.config.model}",
        )

