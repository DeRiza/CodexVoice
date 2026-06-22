"""Native macOS overlay for recording and processing state.

The public controller intentionally stays small: callers only show, hide, set a
state, and feed audio levels. All AppKit windowing, animation, and thread
marshalling are hidden inside this module.
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
_BAR_COUNT = 16
_BAR_WIDTH = 6.0
_BAR_GAP = 5.0
_BAR_MIN_HEIGHT = 6.0
_BAR_MAX_HEIGHT = 40.0
_DOT_COUNT = 5
_DOT_SIZE = 9.0
_DOT_GAP = 13.0
_ANIMATION_INTERVAL_SEC = 1.0 / 30.0
_SHADOW_OFFSET_X = 2.0
_SHADOW_OFFSET_Y = -2.0
_SHADOW_ALPHA = 0.10
_PROCESSING_TRANSITION_SEC = 0.42


@dataclass(frozen=True)
class _PanelFrame:
    x: float
    y: float
    width: float = _PANEL_WIDTH
    height: float = _PANEL_HEIGHT


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


def _waveform_bar_heights(
    level: float,
    phase: float,
    count: int = _BAR_COUNT,
    min_height: float = _BAR_MIN_HEIGHT,
    max_height: float = _BAR_MAX_HEIGHT,
) -> list[float]:
    clamped = _clamp(level, 0.0, 1.0)
    heights: list[float] = []
    for index in range(count):
        wave = 0.55 + 0.45 * math.sin((phase * 5.0) + index * 0.78)
        shaped = _clamp((clamped * 1.45 * wave) + 0.06, 0.0, 1.0)
        heights.append(min_height + (max_height - min_height) * shaped)
    return heights


def _processing_dot_alphas(phase: float, count: int = _DOT_COUNT) -> list[float]:
    active = int((phase * 5.0) % count)
    return [1.0 if index == active else 0.32 for index in range(count)]


class OverlayController:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.visible = False
        self.current_state = SessionState.IDLE
        self.level = 0.0
        self._smoothed_level = 0.0
        self._lock = threading.RLock()
        self._native_failed = False
        self._window = None
        self._container = None
        self._bar_shadow_views: list[object] = []
        self._bar_views: list[object] = []
        self._dot_shadow_views: list[object] = []
        self._dot_views: list[object] = []
        self._animation_running = False
        self._phase = 0.0
        self._processing_transition = 1.0

    def show(self, state: SessionState) -> None:
        with self._lock:
            self.visible = self.enabled
            self.current_state = state
        if self.enabled:
            self._dispatch_ui(lambda: self._show_native(state))

    def hide(self) -> None:
        with self._lock:
            self.visible = False
        self._dispatch_ui(self._hide_native)
        logger.debug("overlay hidden")

    def set_state(self, state: SessionState) -> None:
        with self._lock:
            previous = self.current_state
            self.current_state = state
            if previous is SessionState.RECORDING and state is SessionState.PROCESSING:
                self._processing_transition = 0.0
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
        self._dispatch_ui(lambda: self._show_native(state))

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

    def _show_native(self, state: SessionState) -> None:
        if not self._ensure_native():
            return
        self._apply_state_style(state)
        if self._window is not None:
            self._window.orderFrontRegardless()
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
        except Exception:
            self._native_failed = True
            logger.debug("PyObjC AppKit unavailable; overlay disabled", exc_info=True)
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
        if layer is not None:
            layer.setMasksToBounds_(False)
            layer.setBackgroundColor_(_cg_color(0.0, 0.0, 0.0, 0.0))

        panel.setContentView_(container)
        self._window = panel
        self._container = container
        self._bar_shadow_views = self._make_bar_views(NSView, NSMakeRect, color=(0.0, 0.0, 0.0, _SHADOW_ALPHA))
        self._bar_views = self._make_bar_views(NSView, NSMakeRect, color=(0.35, 0.78, 1.0, 0.95))
        self._dot_shadow_views = self._make_dot_views(NSView, NSMakeRect, color=(0.0, 0.0, 0.0, _SHADOW_ALPHA))
        self._dot_views = self._make_dot_views(NSView, NSMakeRect, color=(0.78, 0.72, 1.0, 0.95))
        return True

    def _make_bar_views(self, NSView, NSMakeRect, color: tuple[float, float, float, float]) -> list[object]:  # noqa: ANN001, N803
        assert self._container is not None
        views = []
        total_width = _BAR_COUNT * _BAR_WIDTH + (_BAR_COUNT - 1) * _BAR_GAP
        start_x = (_PANEL_WIDTH - total_width) / 2.0
        for index in range(_BAR_COUNT):
            view = NSView.alloc().initWithFrame_(
                NSMakeRect(start_x + index * (_BAR_WIDTH + _BAR_GAP), (_PANEL_HEIGHT - _BAR_MIN_HEIGHT) / 2.0, _BAR_WIDTH, _BAR_MIN_HEIGHT)
            )
            view.setWantsLayer_(True)
            layer = view.layer()
            if layer is not None:
                layer.setCornerRadius_(_BAR_WIDTH / 2.0)
                layer.setBackgroundColor_(_cg_color(*color))
            self._container.addSubview_(view)
            views.append(view)
        return views

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
        if not visible or state is SessionState.IDLE:
            self._animation_running = False
            return
        self._phase += _ANIMATION_INTERVAL_SEC
        self._smoothed_level = (self._smoothed_level * 0.78) + (level * 0.22)
        self._render_state(state)
        self._schedule_tick()

    def _render_state(self, state: SessionState) -> None:
        if state is SessionState.RECORDING:
            self._render_waveform()
            return
        if state is SessionState.PROCESSING:
            self._render_processing()
            return
        if state is SessionState.INJECTING:
            self._render_static_dots((0.32, 0.95, 0.70, 0.95), alpha=0.88)
            return
        if state is SessionState.ERROR:
            self._render_static_dots((1.0, 0.28, 0.34, 0.95), alpha=0.95)

    def _render_waveform(self) -> None:
        if self._window is None:
            return
        heights = _waveform_bar_heights(self._smoothed_level, self._phase)
        self._render_bar_group(self._bar_shadow_views, heights, alpha=_SHADOW_ALPHA, x_offset=_SHADOW_OFFSET_X, y_offset=_SHADOW_OFFSET_Y)
        self._render_bar_group(self._bar_views, heights, alpha=1.0, x_offset=0.0, y_offset=0.0)
        self._hide_dots()

    def _render_bar_group(
        self,
        views: list[object],
        heights: list[float],
        alpha: float,
        x_offset: float,
        y_offset: float,
        shrink: float = 0.0,
    ) -> None:
        NSMakeRect = _ns_make_rect()
        total_width = _BAR_COUNT * _BAR_WIDTH + (_BAR_COUNT - 1) * _BAR_GAP
        start_x = (_PANEL_WIDTH - total_width) / 2.0
        target_x = (_PANEL_WIDTH - _BAR_WIDTH) / 2.0
        for index, view in enumerate(views):
            original_x = start_x + index * (_BAR_WIDTH + _BAR_GAP)
            x = original_x + (target_x - original_x) * shrink
            height = heights[index] + (_DOT_SIZE - heights[index]) * shrink
            view.setHidden_(False)
            view.setAlphaValue_(alpha * (1.0 - shrink))
            view.setFrame_(NSMakeRect(x + x_offset, ((_PANEL_HEIGHT - height) / 2.0) + y_offset, _BAR_WIDTH, height))

    def _render_processing(self) -> None:
        if self._processing_transition < 1.0:
            self._render_processing_transition(self._processing_transition)
            return
        self._hide_bars()
        alphas = _processing_dot_alphas(self._phase)
        self._render_dot_group(self._dot_shadow_views, alphas, alpha_scale=_SHADOW_ALPHA, x_offset=_SHADOW_OFFSET_X, y_offset=_SHADOW_OFFSET_Y)
        self._render_dot_group(self._dot_views, alphas, alpha_scale=1.0, x_offset=0.0, y_offset=0.0)

    def _render_processing_transition(self, progress: float) -> None:
        heights = _waveform_bar_heights(self._smoothed_level, self._phase)
        self._render_bar_group(self._bar_shadow_views, heights, alpha=_SHADOW_ALPHA, x_offset=_SHADOW_OFFSET_X, y_offset=_SHADOW_OFFSET_Y, shrink=progress)
        self._render_bar_group(self._bar_views, heights, alpha=1.0, x_offset=0.0, y_offset=0.0, shrink=progress)
        alphas = [value * progress for value in _processing_dot_alphas(self._phase)]
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
        self._hide_bars()
        for view in self._dot_shadow_views:
            view.setHidden_(False)
            view.setAlphaValue_(_SHADOW_ALPHA)
        for view in self._dot_views:
            view.setHidden_(False)
            view.setAlphaValue_(alpha)
            layer = view.layer()
            if layer is not None:
                layer.setBackgroundColor_(_cg_color(*color))

    def _hide_bars(self) -> None:
        for view in [*self._bar_shadow_views, *self._bar_views]:
            view.setHidden_(True)

    def _hide_dots(self) -> None:
        for view in [*self._dot_shadow_views, *self._dot_views]:
            view.setHidden_(True)

    def _apply_state_style(self, state: SessionState) -> None:
        if self._container is None:
            return
        layer = self._container.layer()
        if layer is None:
            return
        layer.setBackgroundColor_(_cg_color(0.0, 0.0, 0.0, 0.0))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _cg_color(red: float, green: float, blue: float, alpha: float):
    from Quartz import CGColorCreateGenericRGB  # type: ignore

    return CGColorCreateGenericRGB(red, green, blue, alpha)


def _ns_make_rect():
    try:
        from AppKit import NSMakeRect  # type: ignore
    except Exception as exc:  # pragma: no cover - only reachable when native UI creation has failed.
        raise RuntimeError("NSMakeRect unavailable") from exc
    return NSMakeRect
