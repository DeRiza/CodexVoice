"""Native macOS overlay for recording and processing state.

The public controller intentionally stays small: callers only show, hide, set a
state, and feed audio levels. All AppKit windowing, animation, sound feedback,
and thread marshalling are hidden inside this module.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass

from codexvoice.types import SessionState

logger = logging.getLogger(__name__)

_PANEL_WIDTH = 300.0
_PANEL_HEIGHT = 72.0
_TOP_MARGIN = 16.0
_WAVE_COLORS = (
    (0.00, 0.92, 1.00, 1.00),
    (0.18, 0.56, 1.00, 1.00),
    (0.68, 0.38, 1.00, 1.00),
    (1.00, 0.34, 0.66, 1.00),
    (1.00, 0.72, 0.18, 1.00),
)
_WAVE_COUNT = len(_WAVE_COLORS)
_WAVE_SAMPLES = 84
_WAVE_ACTIVE_WIDTH = 228.0
_WAVE_BASE_AMPLITUDE = 26.0
_WAVE_LINE_WIDTHS = (0.95, 0.86, 0.78, 0.72, 0.68)
_WAVE_ALPHAS = (0.62, 0.50, 0.46, 0.42, 0.38)
_WAVE_CENTERLINE_WIDTH = 0.62
_WAVE_CENTERLINE_ALPHA = 0.24
_WAVE_AMPLITUDE_MULTIPLIERS = (1.00, 0.86, 0.95, 0.80, 0.90)
_WAVE_FREQUENCIES = (1.25, 1.68, 2.05, 1.52, 2.32)
_WAVE_SECONDARY_FREQUENCIES = (2.45, 2.95, 3.35, 2.70, 3.85)
_WAVE_PHASE_SPEEDS = (2.25, 1.75, 2.65, 1.35, 2.95)
_WAVE_PHASE_OFFSETS = (0.0, 1.7, 3.2, 4.8, 6.4)
_WAVE_Y_OFFSETS = (0.0, -3.2, 2.6, -1.8, 3.4)
_WAVE_SECONDARY_MIX = (0.20, 0.28, 0.24, 0.30, 0.22)
_WAVE_SHADOW_COLORS = tuple((0.0, 0.0, 0.0, 1.0) for _ in range(_WAVE_COUNT))
_WAVE_REPLICATOR_INSTANCE_COUNT = 99
_WAVE_TOTAL_VISIBLE_LINES_PER_COLOR = _WAVE_REPLICATOR_INSTANCE_COUNT + 1
_REPLICATOR_FINAL_SCALE = 0.01
_WAVE_REPLICATOR_ALPHA_OFFSET = -0.0045
_DOT_COUNT = 5
_DOT_SIZE = 9.0
_DOT_GAP = 13.0
_ANIMATION_INTERVAL_SEC = 1.0 / 60.0
_SHADOW_OFFSET_X = 2.0
_SHADOW_OFFSET_Y = -2.0
_SHADOW_ALPHA = 0.10
_PROCESSING_TRANSITION_SEC = 0.42
_START_SOUND = "Tink"
_STOP_SOUND = "Pop"
_SOUND_VOLUME = 0.45
_VISUAL_LEVEL_NOISE_FLOOR = 0.003
_VISUAL_LEVEL_SPEECH_CEILING = 0.060
_VISUAL_LEVEL_CURVE = 0.55
_VISUAL_LEVEL_ATTACK = 0.64
_VISUAL_LEVEL_RELEASE = 0.24
_VOICE_BOOST_MAX = 0.30


@dataclass(frozen=True)
class _PanelFrame:
    x: float
    y: float
    width: float = _PANEL_WIDTH
    height: float = _PANEL_HEIGHT


@dataclass(frozen=True)
class _WaveRenderFrame:
    phase: float
    amplitude_multiplier: float
    voice_intensity: float


def _panel_frame_for_visible_frame(
    visible_min_x: float,
    visible_width: float,
    visible_max_y: float,
    panel_width: float = _PANEL_WIDTH,
    panel_height: float = _PANEL_HEIGHT,
    top_margin: float = _TOP_MARGIN,
) -> _PanelFrame:
    x = visible_min_x + (visible_width - panel_width) / 2.0
    y = visible_max_y - top_margin - panel_height
    return _PanelFrame(x=x, y=y, width=panel_width, height=panel_height)


def _visual_level_from_audio_level(level: float) -> float:
    if level <= _VISUAL_LEVEL_NOISE_FLOOR:
        return 0.0
    normalized = (level - _VISUAL_LEVEL_NOISE_FLOOR) / (_VISUAL_LEVEL_SPEECH_CEILING - _VISUAL_LEVEL_NOISE_FLOOR)
    return _clamp(normalized, 0.0, 1.0) ** _VISUAL_LEVEL_CURVE


def _replicator_amplitude_decay(
    instance_count: int = _WAVE_REPLICATOR_INSTANCE_COUNT,
    final_scale: float = _REPLICATOR_FINAL_SCALE,
) -> float:
    if instance_count <= 1:
        return 1.0
    return final_scale ** (1.0 / (instance_count - 1))


def _waveform_points(
    amplitude_multiplier: float,
    phase: float,
    wave_index: int,
    collapse: float = 0.0,
    x_offset: float = 0.0,
    y_offset: float = 0.0,
) -> list[tuple[float, float]]:
    profile_index = wave_index % _WAVE_COUNT
    clamped_multiplier = _clamp(amplitude_multiplier, 1.0, 1.0 + _VOICE_BOOST_MAX)
    collapse = _clamp(collapse, 0.0, 1.0)
    center_y = _PANEL_HEIGHT / 2.0
    start_x = (_PANEL_WIDTH - _WAVE_ACTIVE_WIDTH) / 2.0
    amplitude = (
        _WAVE_BASE_AMPLITUDE
        * clamped_multiplier
        * _WAVE_AMPLITUDE_MULTIPLIERS[profile_index]
        * (1.0 - collapse)
    )
    frequency = _WAVE_FREQUENCIES[profile_index]
    secondary_frequency = _WAVE_SECONDARY_FREQUENCIES[profile_index]
    phase_speed = _WAVE_PHASE_SPEEDS[profile_index]
    phase_offset = _WAVE_PHASE_OFFSETS[profile_index]
    secondary_mix = _WAVE_SECONDARY_MIX[profile_index]
    vertical_offset = _WAVE_Y_OFFSETS[profile_index] * (1.0 - collapse)
    points: list[tuple[float, float]] = []
    for sample in range(_WAVE_SAMPLES):
        t = sample / (_WAVE_SAMPLES - 1)
        envelope = math.sin(math.pi * t) ** 0.72
        primary = math.sin((math.tau * frequency * t) + phase * phase_speed + phase_offset)
        secondary = math.sin((math.tau * secondary_frequency * t) - phase * (phase_speed * 0.68) + phase_offset * 1.35)
        shape = (primary * (1.0 - secondary_mix)) + (secondary * secondary_mix)
        local_breath = 0.90 + 0.10 * math.sin((math.tau * t) + phase_offset)
        x = start_x + t * _WAVE_ACTIVE_WIDTH + x_offset
        y = center_y + (shape * amplitude * envelope * local_breath) + (vertical_offset * envelope) + y_offset
        points.append((x, y))
    return points


def _waveform_centerline_points(
    x_offset: float = 0.0,
    y_offset: float = 0.0,
) -> list[tuple[float, float]]:
    center_y = (_PANEL_HEIGHT / 2.0) + y_offset
    start_x = (_PANEL_WIDTH - _WAVE_ACTIVE_WIDTH) / 2.0
    end_x = start_x + _WAVE_ACTIVE_WIDTH
    return [(start_x + x_offset, center_y), (end_x + x_offset, center_y)]


class _WaveMotionModel:
    def __init__(self) -> None:
        self._audio_level = 0.0
        self._voice_intensity = 0.0
        self._phase = 0.0

    def set_audio_level(self, level: float) -> None:
        self._audio_level = _clamp(level, 0.0, 1.0)

    def next_frame(self, dt: float) -> _WaveRenderFrame:
        self._phase += max(0.0, dt)
        target_intensity = _visual_level_from_audio_level(self._audio_level)
        response = _VISUAL_LEVEL_ATTACK if target_intensity > self._voice_intensity else _VISUAL_LEVEL_RELEASE
        self._voice_intensity = (self._voice_intensity * (1.0 - response)) + (target_intensity * response)
        amplitude_multiplier = 1.0 + (_VOICE_BOOST_MAX * self._voice_intensity)
        return _WaveRenderFrame(
            phase=self._phase,
            amplitude_multiplier=amplitude_multiplier,
            voice_intensity=self._voice_intensity,
        )


def _processing_dot_alphas(phase: float, count: int = _DOT_COUNT) -> list[float]:
    active = int((phase * 5.0) % count)
    return [1.0 if index == active else 0.32 for index in range(count)]


class OverlayController:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.visible = False
        self.current_state = SessionState.IDLE
        self.level = 0.0
        self._motion = _WaveMotionModel()
        self._lock = threading.RLock()
        self._native_failed = False
        self._window = None
        self._container = None
        self._wave_shadow_replicators: list[object] = []
        self._wave_shadow_source_layers: list[object] = []
        self._wave_replicators: list[object] = []
        self._wave_source_layers: list[object] = []
        self._wave_centerline_layers: list[object] = []
        self._dot_shadow_views: list[object] = []
        self._dot_views: list[object] = []
        self._animation_running = False
        self._processing_transition = 1.0
        self._sound_cache: dict[str, object] = {}

    def show(self, state: SessionState) -> None:
        with self._lock:
            self.visible = self.enabled
            self.current_state = state
        if self.enabled:
            self._dispatch_ui(lambda: self._show_native(state, play_start_sound=state is SessionState.RECORDING))

    def hide(self) -> None:
        with self._lock:
            self.visible = False
        self._dispatch_ui(self._hide_native)
        logger.debug("overlay hidden")

    def set_state(self, state: SessionState) -> None:
        play_stop_sound = False
        with self._lock:
            previous = self.current_state
            self.current_state = state
            if previous is SessionState.RECORDING and state is SessionState.PROCESSING:
                self._processing_transition = 0.0
                play_stop_sound = True
            elif state is not SessionState.PROCESSING:
                self._processing_transition = 1.0
            should_show = self.enabled and state is not SessionState.IDLE
            if should_show:
                self.visible = True
        logger.info("CodexVoice state: %s", state.value)
        if not self.enabled:
            return
        if state is SessionState.IDLE:
            self._dispatch_ui(self._hide_native)
            return
        self._dispatch_ui(lambda: self._show_native(state, play_stop_sound=play_stop_sound))

    def set_level(self, level: float) -> None:
        with self._lock:
            self.level = _clamp(level, 0.0, 1.0)

    def _dispatch_ui(self, callback) -> None:  # noqa: ANN001
        if threading.current_thread() is threading.main_thread():
            callback()
            return
        try:
            from PyObjCTools import AppHelper  # type: ignore
        except Exception:
            logger.debug("PyObjCTools unavailable; overlay UI callback skipped", exc_info=True)
            return
        AppHelper.callAfter(callback)

    def _show_native(self, state: SessionState, play_start_sound: bool = False, play_stop_sound: bool = False) -> None:
        if not self._ensure_native():
            return
        self._apply_state_style(state)
        if self._window is not None:
            self._window.orderFrontRegardless()
        if play_start_sound:
            self._play_system_sound(_START_SOUND, token="recording-start")
        if play_stop_sound:
            self._play_system_sound(_STOP_SOUND, token="recording-stop")
        self._start_animation()

    def _hide_native(self) -> None:
        self._animation_running = False
        if self._window is not None:
            self._window.orderOut_(None)

    def _ensure_native(self) -> bool:
        if not self.enabled or self._native_failed:
            return False
        if self._window is not None:
            return True
        try:
            from AppKit import (  # type: ignore
                NSBackingStoreBuffered,
                NSColor,
                NSFloatingWindowLevel,
                NSMakeRect,
                NSPanel,
                NSScreen,
                NSView,
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorFullScreenAuxiliary,
                NSWindowCollectionBehaviorTransient,
                NSWindowStyleMaskBorderless,
            )
            from Quartz import CAReplicatorLayer, CAShapeLayer, CATransform3DMakeScale, kCALineCapRound  # type: ignore
        except Exception:
            self._native_failed = True
            logger.debug("PyObjC AppKit/Quartz unavailable; overlay disabled", exc_info=True)
            return False

        screen = NSScreen.mainScreen()
        if screen is None:
            self._native_failed = True
            logger.debug("No NSScreen available; overlay disabled")
            return False

        visible = screen.visibleFrame()
        frame = _panel_frame_for_visible_frame(
            float(visible.origin.x),
            float(visible.size.width),
            float(visible.origin.y + visible.size.height),
        )
        rect = NSMakeRect(frame.x, frame.y, frame.width, frame.height)
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(False)
        panel.setIgnoresMouseEvents_(True)
        panel.setLevel_(NSFloatingWindowLevel)
        panel.setHidesOnDeactivate_(False)
        panel.setReleasedWhenClosed_(False)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorTransient
        )

        container = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, frame.width, frame.height))
        container.setWantsLayer_(True)
        layer = container.layer()
        if layer is None:
            self._native_failed = True
            logger.debug("Overlay container layer unavailable; overlay disabled")
            return False
        layer.setMasksToBounds_(False)
        layer.setBackgroundColor_(_cg_color(0.0, 0.0, 0.0, 0.0))

        panel.setContentView_(container)
        self._window = panel
        self._container = container
        self._wave_shadow_replicators, self._wave_shadow_source_layers = self._make_wave_replicators(
            CAReplicatorLayer,
            CAShapeLayer,
            CATransform3DMakeScale,
            kCALineCapRound,
            colors=_WAVE_SHADOW_COLORS,
            line_width_extra=0.25,
        )
        self._wave_replicators, self._wave_source_layers = self._make_wave_replicators(
            CAReplicatorLayer,
            CAShapeLayer,
            CATransform3DMakeScale,
            kCALineCapRound,
            colors=_WAVE_COLORS,
            line_width_extra=0.0,
        )
        self._wave_centerline_layers = self._make_wave_centerline_layers(CAShapeLayer, kCALineCapRound, colors=_WAVE_COLORS)
        self._dot_shadow_views = self._make_dot_views(NSView, NSMakeRect, color=(0.0, 0.0, 0.0, _SHADOW_ALPHA))
        self._dot_views = self._make_dot_views(NSView, NSMakeRect, color=(0.78, 0.72, 1.0, 0.95))
        return True

    def _make_wave_replicators(
        self,
        CAReplicatorLayer,
        CAShapeLayer,
        CATransform3DMakeScale,
        line_cap,
        colors: tuple[tuple[float, float, float, float], ...],
        line_width_extra: float,
        line_widths: tuple[float, ...] = _WAVE_LINE_WIDTHS,
    ) -> tuple[list[object], list[object]]:  # noqa: ANN001, N803
        assert self._container is not None
        container_layer = self._container.layer()
        replicators = []
        source_layers = []
        decay = _replicator_amplitude_decay()
        for index in range(_WAVE_COUNT):
            replicator = CAReplicatorLayer.layer()
            replicator.setFrame_(self._container.bounds())
            replicator.setInstanceCount_(_WAVE_REPLICATOR_INSTANCE_COUNT)
            replicator.setInstanceTransform_(CATransform3DMakeScale(1.0, decay, 1.0))
            set_alpha_offset = getattr(replicator, "setInstanceAlphaOffset_", None)
            if callable(set_alpha_offset):
                set_alpha_offset(_WAVE_REPLICATOR_ALPHA_OFFSET)
            replicator.setHidden_(True)

            source = CAShapeLayer.layer()
            source.setFrame_(self._container.bounds())
            source.setFillColor_(_cg_color(0.0, 0.0, 0.0, 0.0))
            source.setStrokeColor_(_cg_color(*colors[index]))
            source.setLineWidth_(line_widths[index] + line_width_extra)
            source.setLineCap_(line_cap)
            source.setHidden_(False)

            replicator.addSublayer_(source)
            container_layer.addSublayer_(replicator)
            replicators.append(replicator)
            source_layers.append(source)
        return replicators, source_layers

    def _make_wave_centerline_layers(self, CAShapeLayer, line_cap, colors: tuple[tuple[float, float, float, float], ...]) -> list[object]:  # noqa: ANN001, N803
        assert self._container is not None
        container_layer = self._container.layer()
        layers = []
        for index in range(_WAVE_COUNT):
            layer = CAShapeLayer.layer()
            layer.setFrame_(self._container.bounds())
            layer.setFillColor_(_cg_color(0.0, 0.0, 0.0, 0.0))
            layer.setStrokeColor_(_cg_color(*colors[index]))
            layer.setLineWidth_(_WAVE_CENTERLINE_WIDTH)
            layer.setLineCap_(line_cap)
            layer.setHidden_(True)
            container_layer.addSublayer_(layer)
            layers.append(layer)
        return layers

    def _make_dot_views(self, NSView, NSMakeRect, color: tuple[float, float, float, float]) -> list[object]:  # noqa: ANN001, N803
        assert self._container is not None
        views = []
        total_width = _DOT_COUNT * _DOT_SIZE + (_DOT_COUNT - 1) * _DOT_GAP
        start_x = (_PANEL_WIDTH - total_width) / 2.0
        for index in range(_DOT_COUNT):
            view = NSView.alloc().initWithFrame_(
                NSMakeRect(start_x + index * (_DOT_SIZE + _DOT_GAP), (_PANEL_HEIGHT - _DOT_SIZE) / 2.0, _DOT_SIZE, _DOT_SIZE)
            )
            view.setWantsLayer_(True)
            view.setHidden_(True)
            layer = view.layer()
            if layer is not None:
                layer.setCornerRadius_(_DOT_SIZE / 2.0)
                layer.setBackgroundColor_(_cg_color(*color))
            self._container.addSubview_(view)
            views.append(view)
        return views

    def _start_animation(self) -> None:
        if self._animation_running:
            return
        self._animation_running = True
        self._schedule_tick()

    def _schedule_tick(self) -> None:
        try:
            from PyObjCTools import AppHelper  # type: ignore
        except Exception:
            self._animation_running = False
            logger.debug("PyObjCTools unavailable; overlay animation stopped", exc_info=True)
            return
        AppHelper.callLater(_ANIMATION_INTERVAL_SEC, self._tick)

    def _tick(self) -> None:
        if not self._animation_running:
            return
        with self._lock:
            state = self.current_state
            level = self.level
            visible = self.visible
            if state is SessionState.PROCESSING and self._processing_transition < 1.0:
                self._processing_transition = min(1.0, self._processing_transition + (_ANIMATION_INTERVAL_SEC / _PROCESSING_TRANSITION_SEC))
            transition = self._processing_transition
        if not visible or state is SessionState.IDLE:
            self._animation_running = False
            return
        self._motion.set_audio_level(level)
        frame = self._motion.next_frame(_ANIMATION_INTERVAL_SEC)
        self._render_state(state, transition, frame)
        self._schedule_tick()

    def _render_state(self, state: SessionState, transition: float, frame: _WaveRenderFrame) -> None:
        if state is SessionState.RECORDING:
            self._render_waveform(frame, collapse=0.0, alpha_scale=1.0)
            return
        if state is SessionState.PROCESSING:
            self._render_processing(transition, frame)
            return
        if state is SessionState.INJECTING:
            self._render_static_dots((0.32, 0.95, 0.70, 0.95), alpha=0.88)
            return
        if state is SessionState.ERROR:
            self._render_static_dots((1.0, 0.28, 0.34, 0.95), alpha=0.95)

    def _render_waveform(self, frame: _WaveRenderFrame, collapse: float, alpha_scale: float) -> None:
        for index, replicator in enumerate(self._wave_shadow_replicators):
            replicator.setHidden_(False)
            replicator.setOpacity_(_WAVE_ALPHAS[index] * _SHADOW_ALPHA * alpha_scale)
            self._wave_shadow_source_layers[index].setPath_(
                _cg_path_from_points(
                    _waveform_points(frame.amplitude_multiplier, frame.phase, index, collapse, _SHADOW_OFFSET_X, _SHADOW_OFFSET_Y)
                )
            )
        for index, replicator in enumerate(self._wave_replicators):
            replicator.setHidden_(False)
            replicator.setOpacity_(_WAVE_ALPHAS[index] * alpha_scale)
            self._wave_source_layers[index].setPath_(_cg_path_from_points(_waveform_points(frame.amplitude_multiplier, frame.phase, index, collapse)))
        for index, layer in enumerate(self._wave_centerline_layers):
            layer.setHidden_(False)
            layer.setOpacity_(_WAVE_CENTERLINE_ALPHA * alpha_scale)
            layer.setPath_(_cg_path_from_points(_waveform_centerline_points()))
        self._hide_dots()

    def _render_processing(self, transition: float, frame: _WaveRenderFrame) -> None:
        if transition < 1.0:
            self._render_waveform(frame, collapse=transition, alpha_scale=1.0 - transition)
            alphas = [value * transition for value in _processing_dot_alphas(frame.phase)]
            self._render_dot_group(self._dot_shadow_views, alphas, alpha_scale=_SHADOW_ALPHA, x_offset=_SHADOW_OFFSET_X, y_offset=_SHADOW_OFFSET_Y)
            self._render_dot_group(self._dot_views, alphas, alpha_scale=1.0, x_offset=0.0, y_offset=0.0)
            return
        self._hide_wave_layers()
        alphas = _processing_dot_alphas(frame.phase)
        self._render_dot_group(self._dot_shadow_views, alphas, alpha_scale=_SHADOW_ALPHA, x_offset=_SHADOW_OFFSET_X, y_offset=_SHADOW_OFFSET_Y)
        self._render_dot_group(self._dot_views, alphas, alpha_scale=1.0, x_offset=0.0, y_offset=0.0)

    def _render_dot_group(self, views: list[object], alphas: list[float], alpha_scale: float, x_offset: float, y_offset: float) -> None:
        NSMakeRect = _ns_make_rect()
        total_width = _DOT_COUNT * _DOT_SIZE + (_DOT_COUNT - 1) * _DOT_GAP
        start_x = (_PANEL_WIDTH - total_width) / 2.0
        for index, view in enumerate(views):
            view.setHidden_(False)
            view.setAlphaValue_(alphas[index] * alpha_scale)
            view.setFrame_(NSMakeRect(start_x + index * (_DOT_SIZE + _DOT_GAP) + x_offset, ((_PANEL_HEIGHT - _DOT_SIZE) / 2.0) + y_offset, _DOT_SIZE, _DOT_SIZE))

    def _render_static_dots(self, color: tuple[float, float, float, float], alpha: float) -> None:
        self._hide_wave_layers()
        for view in self._dot_shadow_views:
            view.setHidden_(False)
            view.setAlphaValue_(_SHADOW_ALPHA)
        for view in self._dot_views:
            view.setHidden_(False)
            view.setAlphaValue_(alpha)
            layer = view.layer()
            if layer is not None:
                layer.setBackgroundColor_(_cg_color(*color))

    def _hide_wave_layers(self) -> None:
        for layer in [*self._wave_shadow_replicators, *self._wave_replicators, *self._wave_centerline_layers]:
            layer.setHidden_(True)

    def _hide_dots(self) -> None:
        for view in [*self._dot_shadow_views, *self._dot_views]:
            view.setHidden_(True)

    def _apply_state_style(self, state: SessionState) -> None:
        if self._container is None:
            return
        layer = self._container.layer()
        if layer is not None:
            layer.setBackgroundColor_(_cg_color(0.0, 0.0, 0.0, 0.0))

    def _play_system_sound(self, name: str, token: str | None = None) -> None:
        del token
        try:
            from AppKit import NSSound  # type: ignore
        except Exception:
            logger.debug("NSSound unavailable; skipping system sound %s", name, exc_info=True)
            return
        sound = self._sound_cache.get(name)
        if sound is None:
            sound = NSSound.soundNamed_(name)
            if sound is None:
                logger.debug("System sound not found: %s", name)
                return
            self._sound_cache[name] = sound
        try:
            sound.setVolume_(_SOUND_VOLUME)
            stop = getattr(sound, "stop", None)
            if callable(stop):
                stop()
            set_current_time = getattr(sound, "setCurrentTime_", None)
            if callable(set_current_time):
                set_current_time(0.0)
            played = sound.play()
            if played is False:
                logger.debug("System sound did not start: %s", name)
        except Exception:
            logger.debug("System sound playback failed: %s", name, exc_info=True)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _cg_color(red: float, green: float, blue: float, alpha: float):
    from Quartz import CGColorCreateGenericRGB  # type: ignore

    return CGColorCreateGenericRGB(red, green, blue, alpha)


def _cg_path_from_points(points: list[tuple[float, float]]):
    from Quartz import CGPathAddLineToPoint, CGPathCreateMutable, CGPathMoveToPoint  # type: ignore

    path = CGPathCreateMutable()
    if not points:
        return path
    first_x, first_y = points[0]
    CGPathMoveToPoint(path, None, first_x, first_y)
    for x, y in points[1:]:
        CGPathAddLineToPoint(path, None, x, y)
    return path


def _ns_make_rect():
    try:
        from AppKit import NSMakeRect  # type: ignore
    except Exception as exc:  # pragma: no cover - only reachable when native UI creation has failed.
        raise RuntimeError("NSMakeRect unavailable") from exc
    return NSMakeRect
