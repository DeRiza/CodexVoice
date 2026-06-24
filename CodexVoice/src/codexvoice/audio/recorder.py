"""In-memory microphone recorder."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from codexvoice.config import RecordingConfig
from codexvoice.types import AudioBuffer, AudioDeviceError, StopReason

from .vad import StopRuleTracker, is_speech_frame, rms_level

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _InputDevice:
    index: int
    name: str


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
            try:
                stream = _open_input_stream(sd, self.config, blocksize, self._on_audio)
            except Exception:
                self._stream = None
                self._recording = False
                raise
            self._stream = stream
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


def _open_input_stream(sd, config: RecordingConfig, blocksize: int, callback: Callable[[bytes, int, object, object], None]):  # noqa: ANN001
    """Open an input stream against the best currently available microphone.

    PortAudio's implicit default input can stay stale after devices disappear.
    Re-enumerating candidates on every start and passing an explicit device
    index lets a later retry pick up newly attached microphones.
    """

    last_error: Exception | None = None
    for attempt in range(2):
        candidates = _input_device_candidates(sd, config)
        if not candidates:
            last_error = AudioDeviceError("No available microphone input device")
        for candidate in candidates:
            stream = None
            try:
                stream = sd.RawInputStream(
                    device=candidate.index,
                    samplerate=config.sample_rate,
                    channels=config.channels,
                    dtype="int16",
                    blocksize=blocksize,
                    callback=callback,
                )
                stream.start()
            except Exception as exc:
                last_error = exc
                if stream is not None:
                    _close_stream_after_start_failure(stream)
                logger.debug(
                    "Failed to open audio input device candidate: index=%s name=%s",
                    candidate.index,
                    candidate.name,
                    exc_info=True,
                )
                continue
            logger.info("Audio input stream started: device=%s name=%s", candidate.index, candidate.name)
            return stream

        if attempt == 0:
            _reset_sounddevice_runtime(sd)

    if last_error is None:
        last_error = AudioDeviceError("No available microphone input device")
    raise last_error


def _close_stream_after_start_failure(stream) -> None:  # noqa: ANN001
    try:
        stream.close()
    except Exception:
        logger.debug("Failed to close audio stream after start failure", exc_info=True)


def _input_device_candidates(sd, config: RecordingConfig) -> list[_InputDevice]:  # noqa: ANN001
    devices = _query_devices(sd)
    candidates: list[_InputDevice] = []
    seen: set[int] = set()

    default_index = _default_input_index(sd)
    if default_index is not None:
        _append_input_candidate(sd, config, devices, default_index, candidates, seen)

    for index in range(len(devices)):
        _append_input_candidate(sd, config, devices, index, candidates, seen)

    return candidates


def _query_devices(sd) -> list[object]:  # noqa: ANN001
    query_devices = getattr(sd, "query_devices", None)
    if not callable(query_devices):
        return []
    try:
        return list(query_devices())
    except Exception:
        logger.debug("Failed to query PortAudio devices", exc_info=True)
        return []


def _default_input_index(sd) -> int | None:  # noqa: ANN001
    default = getattr(sd, "default", None)
    device = getattr(default, "device", None)
    if isinstance(device, (list, tuple)):
        value = device[0] if device else None
    else:
        value = device
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _append_input_candidate(
    sd,  # noqa: ANN001
    config: RecordingConfig,
    devices: list[object],
    index: int,
    candidates: list[_InputDevice],
    seen: set[int],
) -> None:
    if index in seen or index < 0 or index >= len(devices):
        return
    device = devices[index]
    if not _is_usable_input_device(sd, config, index, device):
        return
    seen.add(index)
    candidates.append(_InputDevice(index=index, name=str(_device_value(device, "name", f"Input {index}"))))


def _is_usable_input_device(sd, config: RecordingConfig, index: int, device: object) -> bool:  # noqa: ANN001
    max_input_channels = _device_value(device, "max_input_channels", 0)
    try:
        if int(max_input_channels) < config.channels:
            return False
    except (TypeError, ValueError):
        return False

    check_input_settings = getattr(sd, "check_input_settings", None)
    if callable(check_input_settings):
        try:
            check_input_settings(
                device=index,
                samplerate=config.sample_rate,
                channels=config.channels,
                dtype="int16",
            )
        except Exception:
            logger.debug("Input device rejected by PortAudio settings check: index=%s", index, exc_info=True)
            return False
    return True


def _device_value(device: object, key: str, default: object) -> object:
    if hasattr(device, "get"):
        return device.get(key, default)  # type: ignore[attr-defined]
    return getattr(device, key, default)


def _reset_sounddevice_runtime(sd) -> None:  # noqa: ANN001
    """Best-effort PortAudio refresh after device-open failures.

    macOS can leave PortAudio's device state stale after the default input
    device disappears. Reinitializing sounddevice's PortAudio layer after a
    failed open lets the next recording attempt see newly connected microphones.
    The original start failure is still raised to the caller.
    """

    terminate = getattr(sd, "_terminate", None)
    initialize = getattr(sd, "_initialize", None)
    query_devices = getattr(sd, "query_devices", None)

    try:
        if callable(terminate):
            terminate()
        if callable(initialize):
            initialize()
        if callable(query_devices):
            query_devices()
        logger.info("Refreshed PortAudio device state after input stream start failure")
    except Exception:
        logger.debug("Failed to refresh PortAudio device state after input stream start failure", exc_info=True)
