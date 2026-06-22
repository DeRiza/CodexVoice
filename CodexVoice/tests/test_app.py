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

