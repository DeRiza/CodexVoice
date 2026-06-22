from codexvoice.hotkey import HotkeyManager


COMMAND = 1 << 20
SHIFT = 1 << 17
OPTION = 1 << 19
CONTROL = 1 << 18


class FakeEvent:
    def __init__(self, chars: str = "", key_code: int = 0, flags: int = 0, repeat: bool = False) -> None:
        self._chars = chars
        self._key_code = key_code
        self._flags = flags
        self._repeat = repeat

    def charactersIgnoringModifiers(self) -> str:
        return self._chars

    def keyCode(self) -> int:
        return self._key_code

    def modifierFlags(self) -> int:
        return self._flags

    def isARepeat(self) -> bool:
        return self._repeat


def test_ctrl_down_matches_down_arrow_key_code() -> None:
    hotkey = HotkeyManager("ctrl+down", lambda: None)

    assert hotkey._matches(FakeEvent(key_code=125, flags=CONTROL))


def test_ctrl_down_does_not_match_other_ctrl_key() -> None:
    hotkey = HotkeyManager("ctrl+down", lambda: None)

    assert not hotkey._matches(FakeEvent(chars="a", key_code=0, flags=CONTROL))


def test_option_space_still_matches_space() -> None:
    hotkey = HotkeyManager("option+space", lambda: None)

    assert hotkey._matches(FakeEvent(chars=" ", key_code=49, flags=OPTION))


def test_hotkey_requires_declared_modifier_set() -> None:
    hotkey = HotkeyManager("ctrl+down", lambda: None)

    assert not hotkey._matches(FakeEvent(key_code=125, flags=CONTROL | SHIFT))


def test_repeated_keydown_is_ignored() -> None:
    calls = []
    hotkey = HotkeyManager("ctrl+left", lambda: calls.append("toggle"))

    hotkey._handle_global_event(FakeEvent(key_code=123, flags=CONTROL, repeat=True))

    assert calls == []


def test_hotkey_debounce_blocks_duplicate_events() -> None:
    calls = []
    times = iter([10.0, 10.1, 10.5])
    hotkey = HotkeyManager("ctrl+left", lambda: calls.append("toggle"), clock=lambda: next(times))

    event = FakeEvent(key_code=123, flags=CONTROL)
    hotkey._handle_global_event(event)
    hotkey._handle_global_event(event)
    hotkey._handle_global_event(event)

    assert calls == ["toggle", "toggle"]


def test_modifier_only_hotkey_matches_exact_modifier_flags() -> None:
    hotkey = HotkeyManager("shift+cmd", lambda: None)

    assert hotkey._matches(FakeEvent(flags=COMMAND | SHIFT))


def test_modifier_only_hotkey_rejects_extra_modifiers() -> None:
    hotkey = HotkeyManager("shift+cmd", lambda: None)

    assert not hotkey._matches(FakeEvent(flags=COMMAND | SHIFT | OPTION))


def test_modifier_only_hotkey_fires_once_until_released() -> None:
    calls = []
    times = iter([10.0, 10.5])
    hotkey = HotkeyManager("shift+cmd", lambda: calls.append("toggle"), clock=lambda: next(times))

    hotkey._handle_global_event(FakeEvent(flags=COMMAND))
    hotkey._handle_global_event(FakeEvent(flags=COMMAND | SHIFT))
    hotkey._handle_global_event(FakeEvent(flags=COMMAND | SHIFT))
    hotkey._handle_global_event(FakeEvent(flags=COMMAND))
    hotkey._handle_global_event(FakeEvent(flags=COMMAND | SHIFT))

    assert calls == ["toggle", "toggle"]
