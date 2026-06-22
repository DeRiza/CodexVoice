"""macOS menu bar status item."""

from __future__ import annotations

import platform
from typing import Callable

from codexvoice.types import SessionState


class StatusItemApp:
    def __init__(self, on_quit: Callable[[], None]) -> None:
        self._on_quit = on_quit
        self._state = SessionState.IDLE
        self._app = None
        self._status_item = None

    def run(self) -> None:
        if platform.system() != "Darwin":
            raise RuntimeError("CodexVoice menu bar UI is macOS-only")
        try:
            from AppKit import (  # type: ignore
                NSApplication,
                NSApplicationActivationPolicyAccessory,
                NSMenu,
                NSMenuItem,
                NSStatusBar,
                NSVariableStatusItemLength,
            )
        except ImportError as exc:
            raise RuntimeError("PyObjC AppKit is required for the menu bar UI") from exc

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        menu = NSMenu.alloc().init()
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit CodexVoice", "terminate:", "q")
        menu.addItem_(quit_item)
        status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        status_item.button().setTitle_("CV")
        status_item.setMenu_(menu)
        self._app = app
        self._status_item = status_item
        app.run()

    def set_state(self, state: SessionState) -> None:
        self._state = state
        if self._status_item is not None:
            self._status_item.button().setTitle_(self._title_for_state(state))

    def show_error(self, message: str) -> None:
        self.set_state(SessionState.ERROR)

    @staticmethod
    def _title_for_state(state: SessionState) -> str:
        return {
            SessionState.IDLE: "CV",
            SessionState.RECORDING: "REC",
            SessionState.PROCESSING: "...",
            SessionState.INJECTING: "INJ",
            SessionState.ERROR: "ERR",
        }[state]

