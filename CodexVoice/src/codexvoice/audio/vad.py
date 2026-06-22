"""Small energy-based VAD and stop-rule tracking."""

from __future__ import annotations

import math
import struct

from codexvoice.config import RecordingConfig
from codexvoice.types import StopReason

WEBRTC_ENERGY_GATE = 0.003


def rms_level(pcm_frame: bytes) -> float:
    if len(pcm_frame) < 2:
        return 0.0
    usable = pcm_frame[: len(pcm_frame) - (len(pcm_frame) % 2)]
    samples = struct.iter_unpack("<h", usable)
    total = 0
    count = 0
    for (sample,) in samples:
        total += sample * sample
        count += 1
    if count == 0:
        return 0.0
    return min(1.0, math.sqrt(total / count) / 32768.0)


def is_speech_frame(pcm_frame: bytes, sample_rate: int, energy_threshold: float = 0.015) -> bool:
    level = rms_level(pcm_frame)
    try:
        import webrtcvad  # type: ignore
    except ImportError:
        return level >= energy_threshold

    if level < WEBRTC_ENERGY_GATE:
        return False

    try:
        vad = webrtcvad.Vad(2)
        return bool(vad.is_speech(pcm_frame, sample_rate))
    except Exception:
        return level >= energy_threshold


class StopRuleTracker:
    def __init__(self, config: RecordingConfig) -> None:
        self.config = config
        self.start_time: float | None = None
        self.last_speech_time: float | None = None
        self.has_speech = False

    def reset(self, now: float) -> None:
        self.start_time = now
        self.last_speech_time = None
        self.has_speech = False

    def update(self, is_speech: bool, now: float) -> StopReason | None:
        if self.start_time is None:
            self.reset(now)

        assert self.start_time is not None
        elapsed = now - self.start_time
        if elapsed >= self.config.max_duration_sec:
            return StopReason.MAX_DURATION

        if is_speech:
            self.has_speech = True
            self.last_speech_time = now
            return None

        if not self.has_speech and elapsed >= self.config.pre_speech_timeout_sec:
            return StopReason.NO_SPEECH

        if self.has_speech and self.last_speech_time is not None:
            if now - self.last_speech_time >= self.config.post_speech_silence_sec:
                return StopReason.SILENCE

        return None
