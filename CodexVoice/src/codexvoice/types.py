"""Shared data structures for CodexVoice MVP."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SessionState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    INJECTING = "injecting"
    ERROR = "error"


class StopReason(str, Enum):
    MANUAL = "manual"
    NO_SPEECH = "no_speech"
    SILENCE = "silence"
    MAX_DURATION = "max_duration"


class PermissionState(str, Enum):
    GRANTED = "granted"
    DENIED = "denied"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


class CodexVoiceError(Exception):
    """Base exception for recoverable CodexVoice failures."""


class TranscriberUnavailable(CodexVoiceError):
    """Raised when the configured local transcription engine is unavailable."""


class AudioDeviceError(CodexVoiceError):
    """Raised when the microphone cannot be opened."""


@dataclass(frozen=True)
class AudioBuffer:
    pcm: bytes
    sample_rate: int
    channels: int
    duration_sec: float

    @property
    def is_empty(self) -> bool:
        return not self.pcm or self.duration_sec <= 0


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str | None
    duration_sec: float
    model: str


@dataclass(frozen=True)
class InjectionResult:
    ok: bool
    method: str
    error: str | None = None


@dataclass(frozen=True)
class PermissionStatus:
    name: str
    state: PermissionState
    message: str
    can_request: bool = False
