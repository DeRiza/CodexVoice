import struct
import sys
from types import SimpleNamespace

from codexvoice.audio.vad import StopRuleTracker, is_speech_frame, rms_level
from codexvoice.config import RecordingConfig
from codexvoice.types import StopReason


class AlwaysSpeechVad:
    def __init__(self, mode: int) -> None:
        self.mode = mode

    def is_speech(self, pcm_frame: bytes, sample_rate: int) -> bool:
        return True


def test_rms_level_handles_silence_and_signal() -> None:
    silence = b"\x00\x00" * 160
    signal = struct.pack("<" + "h" * 160, *([12000] * 160))

    assert rms_level(silence) == 0.0
    assert rms_level(signal) > 0.3


def test_webrtc_vad_is_gated_by_low_energy(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "webrtcvad", SimpleNamespace(Vad=AlwaysSpeechVad))
    low_energy = struct.pack("<" + "h" * 320, *([80] * 320))
    enough_energy = struct.pack("<" + "h" * 320, *([120] * 320))

    assert not is_speech_frame(low_energy, 16000)
    assert is_speech_frame(enough_energy, 16000)


def test_stop_rule_returns_no_speech_timeout() -> None:
    tracker = StopRuleTracker(RecordingConfig(pre_speech_timeout_sec=2.0, max_duration_sec=10.0))
    tracker.reset(100.0)

    assert tracker.update(False, 101.0) is None
    assert tracker.update(False, 102.0) is StopReason.NO_SPEECH


def test_stop_rule_returns_silence_after_speech() -> None:
    tracker = StopRuleTracker(RecordingConfig(post_speech_silence_sec=1.0, max_duration_sec=10.0))
    tracker.reset(50.0)

    assert tracker.update(True, 50.2) is None
    assert tracker.update(False, 50.7) is None
    assert tracker.update(False, 51.2) is StopReason.SILENCE


def test_stop_rule_max_duration_wins() -> None:
    tracker = StopRuleTracker(RecordingConfig(max_duration_sec=3.0, pre_speech_timeout_sec=1.0))
    tracker.reset(10.0)

    assert tracker.update(False, 13.0) is StopReason.MAX_DURATION
