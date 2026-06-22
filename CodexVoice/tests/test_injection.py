from codexvoice.config import InjectionConfig
from codexvoice.injection.clipboard import ClipboardInjector


class FakeClipboard:
    def __init__(self, initial: str = "original") -> None:
        self.value = initial
        self.writes: list[str] = []

    def available(self) -> bool:
        return True

    def read(self) -> str:
        return self.value

    def write(self, text: str) -> None:
        self.value = text
        self.writes.append(text)


class FakePasteRunner:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def available(self) -> bool:
        return True

    def paste(self, delay_sec: float) -> None:
        self.calls += 1
        if self.fail:
            raise RuntimeError("paste failed")


def test_clipboard_injector_writes_pastes_and_restores() -> None:
    clipboard = FakeClipboard("before")
    paste = FakePasteRunner()
    injector = ClipboardInjector(InjectionConfig(paste_delay_ms=0), clipboard=clipboard, paste_runner=paste)

    result = injector.inject("你好")

    assert result.ok is True
    assert paste.calls == 1
    assert clipboard.writes == ["你好", "before"]
    assert clipboard.value == "before"


def test_clipboard_injector_rejects_empty_text() -> None:
    clipboard = FakeClipboard()
    paste = FakePasteRunner()
    injector = ClipboardInjector(InjectionConfig(), clipboard=clipboard, paste_runner=paste)

    result = injector.inject("")

    assert result.ok is False
    assert paste.calls == 0
    assert clipboard.writes == []


def test_clipboard_injector_restores_after_paste_failure() -> None:
    clipboard = FakeClipboard("before")
    paste = FakePasteRunner(fail=True)
    injector = ClipboardInjector(InjectionConfig(paste_delay_ms=0), clipboard=clipboard, paste_runner=paste)

    result = injector.inject("hello")

    assert result.ok is False
    assert result.error == "paste failed"
    assert clipboard.writes == ["hello", "before"]
    assert clipboard.value == "before"

