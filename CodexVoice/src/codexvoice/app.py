"""Core voice session orchestration."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from .config import AppConfig, default_user_config_path, load_config, save_config, validate_config
from .logging_setup import setup_logging
from .runtime_lock import SingleInstanceLock
from .types import AudioBuffer, InjectionResult, SessionState, StopReason, Transcript

_ERROR_RECOVERY_DELAY_SEC = 3.0


class BusyError(RuntimeError):
    """Raised when a session action conflicts with current state."""


class RecorderProtocol(Protocol):
    def start(self) -> None: ...
    def stop(self) -> AudioBuffer: ...
    def cancel(self) -> None: ...
    def is_recording(self) -> bool: ...


class TranscriberProtocol(Protocol):
    def transcribe(self, audio: AudioBuffer, prompt: str | None = None) -> Transcript: ...


class InjectorProtocol(Protocol):
    def inject(self, text: str) -> InjectionResult: ...


class OverlayProtocol(Protocol):
    def show(self, state: SessionState) -> None: ...
    def hide(self) -> None: ...
    def set_state(self, state: SessionState) -> None: ...
    def set_level(self, level: float) -> None: ...


class NullOverlay:
    def show(self, state: SessionState) -> None:
        return None

    def hide(self) -> None:
        return None

    def set_state(self, state: SessionState) -> None:
        return None

    def set_level(self, level: float) -> None:
        return None


class VoiceSessionController:
    def __init__(
        self,
        config: AppConfig,
        recorder: RecorderProtocol,
        transcriber: TranscriberProtocol,
        injector: InjectorProtocol,
        overlay: OverlayProtocol | None = None,
        logger: logging.Logger | None = None,
        recorder_factory: Callable[[], RecorderProtocol] | None = None,
    ) -> None:
        self.config = config
        self.recorder = recorder
        self.transcriber = transcriber
        self.injector = injector
        self.overlay = overlay or NullOverlay()
        self.logger = logger or logging.getLogger("codexvoice")
        self._recorder_factory = recorder_factory
        self._state = SessionState.IDLE
        self._lock = threading.RLock()
        self._error_recovery_timer: threading.Timer | None = None

    def toggle(self) -> None:
        current = self.state()
        if current in {SessionState.IDLE, SessionState.ERROR}:
            self.start_recording()
            return
        if current is SessionState.RECORDING:
            self.stop_and_process(StopReason.MANUAL)
            return
        self.logger.info("Ignoring hotkey while session is %s", current.value)

    def start_recording(self) -> None:
        with self._lock:
            if self._state not in {SessionState.IDLE, SessionState.ERROR}:
                raise BusyError(f"Cannot start recording while {self._state.value}")
            self._set_state(SessionState.RECORDING)

        try:
            self.recorder.start()
            self.overlay.show(SessionState.RECORDING)
        except Exception:
            self.logger.exception("Failed to start recording")
            with self._lock:
                self._replace_recorder_after_start_failure()
                self._set_state(SessionState.ERROR)
            return

    def stop_and_process(self, reason: StopReason = StopReason.MANUAL) -> None:
        with self._lock:
            if self._state is not SessionState.RECORDING:
                self.logger.info("Ignoring stop while session is %s", self._state.value)
                return
            self._set_state(SessionState.PROCESSING)

        try:
            process_started = time.perf_counter()
            audio = self.recorder.stop()
            self.logger.info("Recording stopped: reason=%s duration=%.3fs bytes=%d", reason.value, audio.duration_sec, len(audio.pcm))
            if not audio.pcm or audio.duration_sec <= 0:
                self.logger.info("Skipping empty audio buffer")
                self._finish_idle()
                return

            transcribe_started = time.perf_counter()
            transcript = self.transcriber.transcribe(audio)
            transcribe_elapsed = time.perf_counter() - transcribe_started
            text = transcript.text.strip()
            self.logger.info(
                "Transcription completed: seconds=%.3f chars=%d model=%s language=%s",
                transcribe_elapsed,
                len(text),
                transcript.model,
                transcript.language,
            )
            if not text:
                self.logger.info("Skipping empty transcript")
                self._finish_idle()
                return

            with self._lock:
                self._set_state(SessionState.INJECTING)

            inject_started = time.perf_counter()
            result = self.injector.inject(text)
            inject_elapsed = time.perf_counter() - inject_started
            if not result.ok:
                raise RuntimeError(result.error or "Text injection failed")
            total_elapsed = time.perf_counter() - process_started
            self.logger.info(
                "Injection completed: seconds=%.3f chars=%d method=%s",
                inject_elapsed,
                len(text),
                result.method,
            )
            self.logger.info(
                "Voice session completed: processing_seconds=%.3f audio_seconds=%.3f chars=%d",
                total_elapsed,
                audio.duration_sec,
                len(text),
            )
            self._finish_idle()
        except Exception:
            self.logger.exception("Failed to process voice session")
            with self._lock:
                self._set_state(SessionState.ERROR)
            return

    def cancel(self) -> None:
        with self._lock:
            current = self._state
            self._set_state(SessionState.IDLE)
        if current is SessionState.RECORDING:
            self.recorder.cancel()
        self.overlay.hide()

    def state(self) -> SessionState:
        with self._lock:
            return self._state

    def _finish_idle(self) -> None:
        with self._lock:
            self._set_state(SessionState.IDLE)
        self.overlay.hide()

    def _set_state(self, state: SessionState) -> None:
        self._state = state
        if state is SessionState.ERROR:
            self._schedule_error_recovery()
        else:
            self._cancel_error_recovery()
        self.overlay.set_state(state)

    def _schedule_error_recovery(self) -> None:
        self._cancel_error_recovery()
        timer = threading.Timer(_ERROR_RECOVERY_DELAY_SEC, self._recover_from_error)
        timer.daemon = True
        self._error_recovery_timer = timer
        timer.start()

    def _cancel_error_recovery(self) -> None:
        timer = self._error_recovery_timer
        self._error_recovery_timer = None
        if timer is not None:
            timer.cancel()

    def _recover_from_error(self) -> None:
        with self._lock:
            if self._state is not SessionState.ERROR:
                return
            self._error_recovery_timer = None
            self.logger.info("Recovering from error state after %.1fs", _ERROR_RECOVERY_DELAY_SEC)
            self._set_state(SessionState.IDLE)

    def _replace_recorder_after_start_failure(self) -> None:
        if self._recorder_factory is None:
            return
        try:
            self.recorder.cancel()
        except Exception:
            self.logger.debug("Failed to cancel recorder while resetting after start failure", exc_info=True)
        self.recorder = self._recorder_factory()
        self.logger.info("Audio recorder reset after start failure")


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv or [])
    config_path = _config_path_from_args(args)
    hotkey = _hotkey_from_args(args)
    if hotkey is not None:
        target_path = config_path or default_user_config_path()
        config = load_config(target_path if target_path.exists() else None)
        config.hotkey = hotkey
        validate_config(config)
        save_config(config, target_path)
        print(f"CodexVoice hotkey saved to {target_path}: {hotkey}")
        return 0

    config = load_config(_effective_config_path(config_path))
    logger = setup_logging(config.logging)

    if "--check" in args:
        logger.info("CodexVoice core check passed")
        print("CodexVoice core check passed.")
        return 0

    with SingleInstanceLock() as lock:
        if not lock.acquired:
            message = "Another CodexVoice instance is already running"
            logger.error(message)
            print(message)
            return 3
        try:
            _run_macos_app(config, logger)
        except Exception as exc:
            logger.error("CodexVoice failed to start: %s", exc)
            print(f"CodexVoice failed to start: {exc}")
            return 2
    return 0


def _config_path_from_args(args: list[str]) -> Path | None:
    if "--config" not in args:
        return None
    index = args.index("--config")
    try:
        return Path(args[index + 1])
    except IndexError as exc:
        raise ValueError("--config requires a path") from exc


def _hotkey_from_args(args: list[str]) -> str | None:
    if "--set-hotkey" not in args:
        return None
    index = args.index("--set-hotkey")
    try:
        return args[index + 1]
    except IndexError as exc:
        raise ValueError("--set-hotkey requires a hotkey like option+space") from exc


def _effective_config_path(explicit_path: Path | None) -> Path | None:
    if explicit_path is not None:
        return explicit_path
    user_path = default_user_config_path()
    if user_path.exists():
        return user_path
    local_path = Path("config.yaml")
    if local_path.exists():
        return local_path
    return None


def _run_macos_app(config: AppConfig, logger: logging.Logger) -> None:
    from .audio.recorder import AudioRecorder
    from .hotkey import HotkeyManager
    from .injection.clipboard import ClipboardInjector
    from .permissions import check_accessibility_permission, check_microphone_permission
    from .transcriber import create_transcriber
    from .ui.overlay import OverlayController
    from .ui.status_item import StatusItemApp

    mic = check_microphone_permission()
    accessibility = check_accessibility_permission()
    logger.info("Permission status: microphone=%s accessibility=%s", mic.state.value, accessibility.state.value)

    overlay = OverlayController(enabled=config.ui.show_overlay)
    controller_box: dict[str, VoiceSessionController] = {}

    def on_auto_stop(reason: StopReason) -> None:
        controller = controller_box.get("controller")
        if controller is not None:
            controller.stop_and_process(reason)

    def make_recorder() -> AudioRecorder:
        return AudioRecorder(config.recording, on_level=overlay.set_level, on_auto_stop=on_auto_stop)

    recorder = make_recorder()
    transcriber = create_transcriber(config.transcription)
    injector = ClipboardInjector(config.injection, logger=logger)
    controller = VoiceSessionController(config, recorder, transcriber, injector, overlay, logger, recorder_factory=make_recorder)
    controller_box["controller"] = controller

    hotkey = HotkeyManager(config.hotkey, controller.toggle)
    hotkey.register()

    app = StatusItemApp(on_quit=hotkey.unregister)
    logger.info("CodexVoice started; hotkey=%s", config.hotkey)
    app.run()
