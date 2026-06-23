import pytest

from codexvoice.audio import recorder as recorder_module
from codexvoice.audio.recorder import AudioRecorder
from codexvoice.config import RecordingConfig


class StartFailingStream:
    def __init__(self) -> None:
        self.closed = False
        self.stopped = False

    def start(self) -> None:
        raise RuntimeError("start failed")

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


class FakeSoundDevice:
    def __init__(self) -> None:
        self.stream = StartFailingStream()

    def RawInputStream(self, **kwargs):  # noqa: ANN001
        return self.stream


def test_audio_recorder_cleans_up_stream_when_start_fails(monkeypatch) -> None:
    fake_sd = FakeSoundDevice()
    monkeypatch.setattr(recorder_module, "_load_sounddevice", lambda: fake_sd)
    recorder = AudioRecorder(RecordingConfig())

    with pytest.raises(RuntimeError, match="start failed"):
        recorder.start()

    assert not recorder.is_recording()
    assert recorder._stream is None
    assert fake_sd.stream.closed
