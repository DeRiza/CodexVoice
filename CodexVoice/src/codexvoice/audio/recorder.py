"""In-memory microphone recorder."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from codexvoice.config import RecordingConfig
from codexvoice.types import AudioBuffer, StopReason

from .vad import StopRuleTracker, is_speech_frame, rms_level


class AudioRecorder:
    def __init__(
        self,
        config: RecordingConfig,
        on_level: Callable[[float], None] | None = None,
        on_auto_stop: Callable[[StopReason], None] | None = None,
    ) -> None:
        self.config = config
        self.on_level = on_level
        self.on_auto_stop = on_auto_stop
        self._tracker = StopRuleTracker(config)
        self._buffer = bytearray()
        self._stream = None
        self._lock = threading.RLock()
        self._recording = False
        self._level = 0.0
        self._auto_stop_sent = False

    def start(self) -> None:
        sd = _load_sounddevice()

        with self._lock:
            if self._recording:
                raise RuntimeError("Recorder is already running")
            self._buffer.clear()
            self._level = 0.0
            self._auto_stop_sent = False
            self._tracker.reset(time.monotonic())
            blocksize = int(self.config.sample_rate * self.config.frame_ms / 1000)
            self._stream = sd.RawInputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype="int16",
                blocksize=blocksize,
                callback=self._on_audio,
            )
            self._stream.start()
            self._recording = True

    def stop(self) -> AudioBuffer:
        with self._lock:
            stream = self._stream
            self._stream = None
            self._recording = False
            pcm = bytes(self._buffer)
            self._buffer.clear()

        if stream is not None:
            stream.stop()
            stream.close()

        bytes_per_second = self.config.sample_rate * self.config.channels * 2
        duration = len(pcm) / bytes_per_second if bytes_per_second else 0.0
        return AudioBuffer(pcm=pcm, sample_rate=self.config.sample_rate, channels=self.config.channels, duration_sec=duration)

    def cancel(self) -> None:
        with self._lock:
            stream = self._stream
            self._stream = None
            self._recording = False
            self._buffer.clear()
        if stream is not None:
            stream.stop()
            stream.close()

    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    def current_level(self) -> float:
        with self._lock:
            return self._level

    def _on_audio(self, indata: bytes, frames: int, time_info: object, status: object) -> None:
        del frames, time_info, status
        data = bytes(indata)
        now = time.monotonic()
        level = rms_level(data)
        speech = is_speech_frame(data, self.config.sample_rate, self.config.speech_threshold)

        with self._lock:
            if not self._recording:
                return
            self._buffer.extend(data)
            self._level = level

        if self.on_level is not None:
            self.on_level(level)

        reason = self._tracker.update(speech, now)
        if reason is not None and self.on_auto_stop is not None:
            with self._lock:
                if self._auto_stop_sent:
                    return
                self._auto_stop_sent = True
            threading.Thread(target=self.on_auto_stop, args=(reason,), daemon=True).start()


def _load_sounddevice():
    try:
        import sounddevice as sd  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only without optional extra.
        raise RuntimeError("Audio recording requires the optional 'audio' extra: pip install 'codexvoice[audio]'") from exc
    return sd
