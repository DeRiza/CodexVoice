"""faster-whisper transcription engine."""

from __future__ import annotations

from codexvoice.config import TranscriptionConfig
from codexvoice.transcriber.normalize import normalize_transcript
from codexvoice.types import AudioBuffer, Transcript, TranscriberUnavailable


class FasterWhisperTranscriber:
    def __init__(self, config: TranscriptionConfig) -> None:
        self.config = config
        self._model = None

    def warmup(self) -> None:
        self._load_model()

    def transcribe(self, audio: AudioBuffer, prompt: str | None = None) -> Transcript:
        if audio.is_empty:
            return Transcript(text="", language=self.config.language, duration_sec=0.0, model=self.config.model)
        model = self._load_model()
        samples = self._pcm_to_float32(audio)
        segments, info = model.transcribe(
            samples,
            language=self.config.language,
            initial_prompt=prompt,
            vad_filter=False,
            beam_size=5,
            temperature=0.0,
        )
        text = "".join(segment.text for segment in segments).strip()
        language = getattr(info, "language", self.config.language)
        return Transcript(
            text=normalize_transcript(text, language),
            language=language,
            duration_sec=audio.duration_sec,
            model=self.config.model,
        )

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:
            raise TranscriberUnavailable(
                "faster-whisper is not installed. Install CodexVoice with the transcribe extra."
            ) from exc
        try:
            self._model = WhisperModel(self.config.model, device="auto", compute_type="int8")
        except Exception as exc:
            raise TranscriberUnavailable(f"Could not load faster-whisper model {self.config.model!r}: {exc}") from exc
        return self._model

    @staticmethod
    def _pcm_to_float32(audio: AudioBuffer):
        try:
            import numpy as np  # type: ignore
        except ImportError as exc:
            raise TranscriberUnavailable("numpy is required for in-memory faster-whisper audio") from exc
        pcm = np.frombuffer(audio.pcm, dtype=np.int16)
        if audio.channels > 1:
            pcm = pcm.reshape((-1, audio.channels)).mean(axis=1).astype(np.int16)
        return pcm.astype(np.float32) / 32768.0

