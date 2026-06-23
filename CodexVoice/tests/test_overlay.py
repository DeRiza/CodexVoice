import sys
from types import SimpleNamespace

from codexvoice.types import SessionState
from codexvoice.ui.overlay import (
    _ANIMATION_INTERVAL_SEC,
    _PANEL_HEIGHT,
    _REPLICATOR_FINAL_SCALE,
    _WAVE_COLORS,
    _WAVE_COUNT,
    _WAVE_REPLICATOR_INSTANCE_COUNT,
    _WAVE_SAMPLES,
    _WAVE_TOTAL_VISIBLE_LINES_PER_COLOR,
    _WaveMotionModel,
    _panel_frame_for_visible_frame,
    _processing_dot_alphas,
    _replicator_amplitude_decay,
    _visual_level_from_audio_level,
    _waveform_centerline_points,
    _waveform_points,
    OverlayController,
)


def test_panel_frame_stays_below_visible_frame_top() -> None:
    frame = _panel_frame_for_visible_frame(visible_min_x=0, visible_width=1440, visible_max_y=900)

    assert frame.width == 300
    assert frame.height == _PANEL_HEIGHT
    assert frame.x == 570
    assert frame.y + frame.height == 884


def test_waveform_points_stay_inside_panel_height() -> None:
    points = _waveform_points(amplitude_multiplier=1.3, phase=0.0, wave_index=0)
    ys = [point[1] for point in points]

    assert len(points) == _WAVE_SAMPLES
    assert min(ys) >= 0
    assert max(ys) <= _PANEL_HEIGHT


def test_waveform_uses_five_distinct_siri_style_colors() -> None:
    assert _WAVE_COUNT == 5
    assert len(_WAVE_COLORS) == _WAVE_COUNT
    assert len({color[:3] for color in _WAVE_COLORS}) == _WAVE_COUNT


def test_waveform_waves_have_stronger_distinct_motion() -> None:
    ranges = []
    midpoints = []
    for index in range(_WAVE_COUNT):
        points = _waveform_points(amplitude_multiplier=1.3, phase=0.7, wave_index=index)
        ys = [point[1] for point in points]
        ranges.append(max(ys) - min(ys))
        midpoints.append(round(ys[_WAVE_SAMPLES // 2], 1))

        assert min(ys) >= 0
        assert max(ys) <= _PANEL_HEIGHT

    assert max(ranges) >= 42.0
    assert len(set(midpoints)) >= 4


def test_visual_level_maps_speech_rms_to_visible_motion() -> None:
    assert _visual_level_from_audio_level(0.0) == 0.0
    assert _visual_level_from_audio_level(0.003) == 0.0
    assert _visual_level_from_audio_level(0.015) >= 0.35
    assert _visual_level_from_audio_level(0.06) == 1.0


def test_animation_runs_at_sixty_fps() -> None:
    assert _ANIMATION_INTERVAL_SEC == 1.0 / 60.0


def test_waveform_has_base_motion_and_voice_boost() -> None:
    base_points = _waveform_points(amplitude_multiplier=1.0, phase=0.4, wave_index=0)
    boosted_points = _waveform_points(amplitude_multiplier=1.3, phase=0.4, wave_index=0)
    base_range = max(y for _, y in base_points) - min(y for _, y in base_points)
    boosted_range = max(y for _, y in boosted_points) - min(y for _, y in boosted_points)

    assert base_range > 20.0
    assert boosted_range > base_range * 1.2


def test_waveform_collapse_flattens_to_centerline() -> None:
    points = _waveform_points(amplitude_multiplier=1.3, phase=1.5, wave_index=_WAVE_COUNT - 1, collapse=1.0)
    center_y = _PANEL_HEIGHT / 2.0

    assert all(abs(y - center_y) < 0.001 for _, y in points)


def test_replicator_line_plan_uses_ninety_nine_instances_plus_centerline() -> None:
    assert _WAVE_REPLICATOR_INSTANCE_COUNT == 99
    assert _WAVE_TOTAL_VISIBLE_LINES_PER_COLOR == 100
    assert round(_replicator_amplitude_decay(_WAVE_REPLICATOR_INSTANCE_COUNT) ** (_WAVE_REPLICATOR_INSTANCE_COUNT - 1), 4) == _REPLICATOR_FINAL_SCALE


def test_waveform_centerline_is_flat_at_panel_center() -> None:
    points = _waveform_centerline_points()
    center_y = _PANEL_HEIGHT / 2.0

    assert len(points) == 2
    assert all(y == center_y for _, y in points)


def test_wave_motion_model_keeps_base_motion_without_sound() -> None:
    model = _WaveMotionModel()

    frame = model.next_frame(_ANIMATION_INTERVAL_SEC)

    assert frame.phase == _ANIMATION_INTERVAL_SEC
    assert frame.voice_intensity == 0.0
    assert frame.amplitude_multiplier == 1.0


def test_wave_motion_model_boosts_and_releases_amplitude() -> None:
    model = _WaveMotionModel()

    model.set_audio_level(0.06)
    boosted = model.next_frame(_ANIMATION_INTERVAL_SEC)
    for _ in range(8):
        boosted = model.next_frame(_ANIMATION_INTERVAL_SEC)

    assert 1.25 <= boosted.amplitude_multiplier <= 1.3
    assert 0.8 <= boosted.voice_intensity <= 1.0

    model.set_audio_level(0.0)
    released = model.next_frame(_ANIMATION_INTERVAL_SEC)

    assert 1.0 < released.amplitude_multiplier < boosted.amplitude_multiplier
    assert 0.0 < released.voice_intensity < boosted.voice_intensity


def test_processing_dot_alphas_has_one_active_dot() -> None:
    alphas = _processing_dot_alphas(phase=0.0)

    assert alphas.count(1.0) == 1
    assert len(alphas) == 5


def test_overlay_controller_preserves_noop_interface_when_disabled() -> None:
    overlay = OverlayController(enabled=False)

    overlay.show(SessionState.RECORDING)
    overlay.set_level(2.0)
    overlay.set_state(SessionState.PROCESSING)
    overlay.hide()

    assert not overlay.visible
    assert overlay.current_state is SessionState.PROCESSING
    assert overlay.level == 1.0


def test_system_sound_replays_same_token(monkeypatch) -> None:
    class FakeSound:
        def __init__(self) -> None:
            self.play_count = 0
            self.stop_count = 0
            self.current_times: list[float] = []
            self.volumes: list[float] = []

        def setVolume_(self, volume: float) -> None:
            self.volumes.append(volume)

        def stop(self) -> None:
            self.stop_count += 1

        def setCurrentTime_(self, value: float) -> None:
            self.current_times.append(value)

        def play(self) -> bool:
            self.play_count += 1
            return True

    fake_sound = FakeSound()
    fake_nssound = SimpleNamespace(soundNamed_=lambda name: fake_sound)
    monkeypatch.setitem(sys.modules, "AppKit", SimpleNamespace(NSSound=fake_nssound))

    overlay = OverlayController()
    overlay._play_system_sound("Tink", token="recording-start")
    overlay._play_system_sound("Tink", token="recording-start")

    assert fake_sound.play_count == 2
    assert fake_sound.stop_count == 2
    assert fake_sound.current_times == [0.0, 0.0]
