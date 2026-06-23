import time

from codexvoice import app as app_module
from codexvoice.app import VoiceSessionController
from codexvoice.config import default_config
from codexvoice.transcriber.fake import FakeTranscriber
from codexvoice.types import AudioBuffer, InjectionResult, SessionState


class FakeRecorder:
    def __init__(self) -> None:
        self.recording = False
        self.audio = AudioBuffer(b"\x01\x00" * 160, 16000, 1, 0.01)

    def start(self) -> None:
        self.recording = True

    def stop(self) -> AudioBuffer:
        self.recording = False
        return self.audio

    def cancel(self) -> None:
        self.recording = False

    def is_recording(self) -> bool:
        return self.recording


class FailingStartRecorder(FakeRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.start_calls = 0

    def start(self) -> None:
        self.start_calls += 1
        self.recording = False
        raise RuntimeError("microphone unavailable")


class FailingStopRecorder(FakeRecorder):
    def stop(self) -> AudioBuffer:
        self.recording = False
        raise RuntimeError("stop failed")


class RecoveringStartRecorder(FailingStartRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.should_fail = True

    def start(self) -> None:
        self.start_calls += 1
        if self.should_fail:
            self.recording = False
            raise RuntimeError("microphone unavailable")
        self.recording = True


class FakeInjector:
    def __init__(self) -> None:
        self.text = ""

    def inject(self, text: str) -> InjectionResult:
        self.text = text
        return InjectionResult(ok=True, method="fake")


def test_toggle_runs_full_session() -> None:
    config = default_config()
    config.transcription.engine = "fake"
    recorder = FakeRecorder()
    injector = FakeInjector()
    controller = VoiceSessionController(config, recorder, FakeTranscriber(config.transcription, "完成"), injector)

    controller.toggle()
    assert controller.state() == SessionState.RECORDING
    controller.toggle()

    assert controller.state() == SessionState.IDLE
    assert injector.text == "完成"


def test_toggle_recovers_from_recorder_start_failure_without_raising() -> None:
    config = default_config()
    recorder = FailingStartRecorder()
    injector = FakeInjector()
    controller = VoiceSessionController(config, recorder, FakeTranscriber(config.transcription, "完成"), injector)

    controller.toggle()

    assert controller.state() == SessionState.ERROR
    assert recorder.start_calls == 1


def test_start_failure_replaces_recorder_before_next_retry() -> None:
    config = default_config()
    first_recorder = FailingStartRecorder()
    second_recorder = FakeRecorder()
    created = [second_recorder]
    injector = FakeInjector()
    controller = VoiceSessionController(
        config,
        first_recorder,
        FakeTranscriber(config.transcription, "完成"),
        injector,
        recorder_factory=lambda: created.pop(0),
    )

    controller.toggle()
    assert controller.state() == SessionState.ERROR
    assert controller.recorder is second_recorder

    controller.toggle()
    assert controller.state() == SessionState.RECORDING
    assert second_recorder.recording


def test_error_state_auto_recovers_to_idle_after_delay(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_ERROR_RECOVERY_DELAY_SEC", 0.01, raising=False)
    config = default_config()
    recorder = FailingStartRecorder()
    injector = FakeInjector()
    controller = VoiceSessionController(config, recorder, FakeTranscriber(config.transcription, "完成"), injector)

    controller.toggle()
    assert controller.state() == SessionState.ERROR

    time.sleep(0.05)

    assert controller.state() == SessionState.IDLE


def test_error_recovery_timer_does_not_override_successful_retry(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_ERROR_RECOVERY_DELAY_SEC", 0.02, raising=False)
    config = default_config()
    recorder = RecoveringStartRecorder()
    injector = FakeInjector()
    controller = VoiceSessionController(config, recorder, FakeTranscriber(config.transcription, "完成"), injector)

    controller.toggle()
    assert controller.state() == SessionState.ERROR

    recorder.should_fail = False
    controller.toggle()
    assert controller.state() == SessionState.RECORDING

    time.sleep(0.05)

    assert controller.state() == SessionState.RECORDING


def test_toggle_recovers_from_processing_failure_without_raising() -> None:
    config = default_config()
    recorder = FailingStopRecorder()
    injector = FakeInjector()
    controller = VoiceSessionController(config, recorder, FakeTranscriber(config.transcription, "完成"), injector)

    controller.toggle()
    controller.toggle()

    assert controller.state() == SessionState.ERROR
    assert injector.text == ""
