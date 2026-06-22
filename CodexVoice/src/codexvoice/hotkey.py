"""Global hotkey manager for macOS."""

from __future__ import annotations

import platform
import time
from collections.abc import Callable

_MODIFIERS = {"cmd", "command", "shift", "alt", "option", "ctrl", "control"}
_KEY_CODES = {
    "space": 49,
    "down": 125,
    "downarrow": 125,
    "arrowdown": 125,
    "up": 126,
    "uparrow": 126,
    "arrowup": 126,
    "left": 123,
    "leftarrow": 123,
    "arrowleft": 123,
    "right": 124,
    "rightarrow": 124,
    "arrowright": 124,
}


class HotkeyManager:
    def __init__(
        self,
        hotkey: str,
        on_toggle: Callable[[], None],
        min_interval_sec: float = 0.35,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not hotkey.strip():
            raise ValueError("hotkey must not be empty")
        self.hotkey = hotkey.lower()
        self.on_toggle = on_toggle
        self.min_interval_sec = min_interval_sec
        self._clock = clock
        self._last_fire_at = -float("inf")
        self._modifier_only_active = False
        self._global_monitor = None
        self._local_monitor = None

    def register(self) -> None:
        if platform.system() != "Darwin":
            raise RuntimeError("Global hotkeys are only supported on macOS for CodexVoice MVP")
        try:
            from AppKit import NSEvent, NSEventMaskFlagsChanged, NSEventMaskKeyDown  # type: ignore
        except ImportError as exc:
            raise RuntimeError("PyObjC AppKit is required for global hotkeys. Install codexvoice[ui].") from exc

        event_mask = NSEventMaskFlagsChanged if self._is_modifier_only_hotkey() else NSEventMaskKeyDown
        self._global_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            event_mask,
            self._handle_global_event,
        )
        self._local_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            event_mask,
            self._handle_local_event,
        )

    def unregister(self) -> None:
        try:
            from AppKit import NSEvent  # type: ignore
        except ImportError:
            return
        for monitor in (self._global_monitor, self._local_monitor):
            if monitor is not None:
                NSEvent.removeMonitor_(monitor)
        self._global_monitor = None
        self._local_monitor = None

    def set_hotkey(self, hotkey: str) -> None:
        if not hotkey.strip():
            raise ValueError("hotkey must not be empty")
        was_registered = self._global_monitor is not None or self._local_monitor is not None
        if was_registered:
            self.unregister()
        self.hotkey = hotkey.lower()
        self._modifier_only_active = False
        if was_registered:
            self.register()

    def _handle_global_event(self, event) -> None:  # noqa: ANN001
        if self._should_fire(event):
            self.on_toggle()

    def _handle_local_event(self, event):  # noqa: ANN001
        if self._should_fire(event):
            self.on_toggle()
            if self._is_modifier_only_hotkey():
                return event
            return None
        return event

    def _should_fire(self, event) -> bool:  # noqa: ANN001
        if self._is_modifier_only_hotkey():
            if not self._matches(event):
                self._modifier_only_active = False
                return False
            if self._modifier_only_active:
                return False
            self._modifier_only_active = True
        else:
            is_repeat = getattr(event, "isARepeat", lambda: False)
            if is_repeat():
                return False
            if not self._matches(event):
                return False
        now = self._clock()
        if now - self._last_fire_at < self.min_interval_sec:
            return False
        self._last_fire_at = now
        return True

    def _matches(self, event) -> bool:  # noqa: ANN001
        wanted = {part.strip() for part in self.hotkey.split("+") if part.strip()}
        if not self._is_modifier_only(wanted) and not self._key_matches(wanted, event):
            return False

        flags = int(event.modifierFlags())
        command = bool(flags & (1 << 20))
        shift = bool(flags & (1 << 17))
        option = bool(flags & (1 << 19))
        control = bool(flags & (1 << 18))

        return (
            ("cmd" in wanted or "command" in wanted) == command
            and ("shift" in wanted) == shift
            and ("alt" in wanted or "option" in wanted) == option
            and ("ctrl" in wanted or "control" in wanted) == control
        )

    def _is_modifier_only_hotkey(self) -> bool:
        wanted = {part.strip() for part in self.hotkey.split("+") if part.strip()}
        return self._is_modifier_only(wanted)

    def _is_modifier_only(self, wanted: set[str]) -> bool:
        return bool(wanted) and wanted <= _MODIFIERS

    def _key_matches(self, wanted: set[str], event) -> bool:  # noqa: ANN001
        key_tokens = wanted - _MODIFIERS
        if len(key_tokens) != 1:
            return False
        token = next(iter(key_tokens))
        expected_key_code = _KEY_CODES.get(token)
        if expected_key_code is not None:
            return int(event.keyCode()) == expected_key_code
        key = (event.charactersIgnoringModifiers() or "").lower()
        return key == token
