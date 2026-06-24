import pytest

from codexvoice.audio import recorder as recorder_module
from codexvoice.audio.recorder import AudioRecorder
from codexvoice.config import RecordingConfig
from codexvoice.types import AudioDeviceError


class FakeStream:
    def __init__(self, fail_on_start: bool = False) -> None:
        self.fail_on_start = fail_on_start
        self.closed = False
        self.stopped = False
        self.started = False

    def start(self) -> None:
        if self.fail_on_start:
            raise RuntimeError("start failed")
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


class FakeSoundDevice:
    def __init__(
        self,
        devices: list[dict] | None = None,
        default_input: int | None = 0,
        start_failures: set[int] | None = None,
    ) -> None:
        self.devices = devices if devices is not None else [{"name": "Built-in Mic", "max_input_channels": 1}]
        self.default = type("Default", (), {"device": [default_input, None]})()
        self.start_failures = start_failures or set()
        self.streams: list[FakeStream] = []
        self.raw_input_stream_calls: list[dict] = []
        self.terminated = False
        self.initialized = False
        self.queried = False
        self.checks: list[int] = []

    def RawInputStream(self, **kwargs):  # noqa: ANN001
        self.raw_input_stream_calls.append(kwargs)
        device = kwargs.get("device")
        if device is None:
            device = self.default.device[0]
        if not isinstance(device, int) or not self._is_input_device(device):
            raise RuntimeError("default input unavailable")
        stream = FakeStream(fail_on_start=device in self.start_failures)
        self.streams.append(stream)
        return stream

    def _terminate(self) -> None:
        self.terminated = True

    def _initialize(self) -> None:
        self.initialized = True

    def query_devices(self):  # noqa: ANN001
        self.queried = True
        return self.devices

    def check_input_settings(self, *, device, samplerate, channels, dtype) -> None:  # noqa: ANN001
        del samplerate, channels, dtype
        self.checks.append(device)
        if not self._is_input_device(device):
            raise RuntimeError("invalid input device")

    def _is_input_device(self, index: int) -> bool:
        return 0 <= index < len(self.devices) and self.devices[index].get("max_input_channels", 0) > 0


def test_audio_recorder_cleans_up_stream_when_start_fails(monkeypatch) -> None:
    fake_sd = FakeSoundDevice(start_failures={0})
    monkeypatch.setattr(recorder_module, "_load_sounddevice", lambda: fake_sd)
    recorder = AudioRecorder(RecordingConfig())

    with pytest.raises(RuntimeError, match="start failed"):
        recorder.start()

    assert not recorder.is_recording()
    assert recorder._stream is None
    assert fake_sd.streams
    assert all(stream.closed for stream in fake_sd.streams)
    assert fake_sd.terminated
    assert fake_sd.initialized
    assert fake_sd.queried


def test_audio_recorder_reenumerates_after_microphone_appears(monkeypatch) -> None:
    fake_sd = FakeSoundDevice(devices=[], default_input=99)
    monkeypatch.setattr(recorder_module, "_load_sounddevice", lambda: fake_sd)
    recorder = AudioRecorder(RecordingConfig())

    with pytest.raises(AudioDeviceError, match="No available microphone input device"):
        recorder.start()

    assert not recorder.is_recording()
    assert fake_sd.terminated
    assert fake_sd.initialized
    assert fake_sd.queried

    fake_sd.devices = [{"name": "USB Microphone", "max_input_channels": 1}]

    recorder.start()

    assert recorder.is_recording()
    assert fake_sd.raw_input_stream_calls[-1]["device"] == 0
    assert fake_sd.streams[-1].started


def test_audio_recorder_falls_back_when_default_input_stream_cannot_open(monkeypatch) -> None:
    fake_sd = FakeSoundDevice(
        devices=[
            {"name": "Stale AirPods", "max_input_channels": 1},
            {"name": "MacBook Pro Microphone", "max_input_channels": 1},
        ],
        default_input=0,
        start_failures={0},
    )
    monkeypatch.setattr(recorder_module, "_load_sounddevice", lambda: fake_sd)
    recorder = AudioRecorder(RecordingConfig())

    recorder.start()

    assert recorder.is_recording()
    assert [call["device"] for call in fake_sd.raw_input_stream_calls] == [0, 1]
    assert fake_sd.streams[0].closed
    assert fake_sd.streams[1].started
