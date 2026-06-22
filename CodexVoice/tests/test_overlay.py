from codexvoice.types import SessionState
from codexvoice.ui.overlay import (
    _BAR_MAX_HEIGHT,
    _BAR_MIN_HEIGHT,
    _PANEL_HEIGHT,
    _panel_frame_for_visible_frame,
    _processing_dot_alphas,
    _waveform_bar_heights,
    OverlayController,
)


def test_panel_frame_stays_below_visible_frame_top() -> None:
    frame = _panel_frame_for_visible_frame(visible_min_x=0, visible_width=1440, visible_max_y=900)

    assert frame.width == 300
    assert frame.height == _PANEL_HEIGHT
    assert frame.x == 570
    assert frame.y + frame.height == 884


def test_waveform_bar_heights_are_clamped_to_safe_range() -> None:
    heights = _waveform_bar_heights(level=10.0, phase=0.0)

    assert len(heights) == 16
    assert min(heights) >= _BAR_MIN_HEIGHT
    assert max(heights) <= _BAR_MAX_HEIGHT


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
