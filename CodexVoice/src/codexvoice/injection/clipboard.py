"""Clipboard-based text injection for macOS."""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import time
from typing import Protocol

from codexvoice.config import InjectionConfig
from codexvoice.types import InjectionResult


class ClipboardBackend(Protocol):
    def available(self) -> bool: ...
    def read(self) -> str: ...
    def write(self, text: str) -> None: ...


class PasteRunner(Protocol):
    def available(self) -> bool: ...
    def paste(self, delay_sec: float) -> None: ...


class MacClipboardBackend:
    def available(self) -> bool:
        return platform.system() == "Darwin" and shutil.which("pbcopy") is not None and shutil.which("pbpaste") is not None

    def read(self) -> str:
        result = subprocess.run(["pbpaste"], check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "pbpaste failed")
        return result.stdout

    def write(self, text: str) -> None:
        result = subprocess.run(["pbcopy"], input=text, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "pbcopy failed")


class AppleScriptPasteRunner:
    def available(self) -> bool:
        return platform.system() == "Darwin" and shutil.which("osascript") is not None

    def paste(self, delay_sec: float) -> None:
        script = 'tell application "System Events" to keystroke "v" using command down'
        result = subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "osascript paste failed")
        if delay_sec > 0:
            time.sleep(delay_sec)


class ClipboardInjector:
    def __init__(
        self,
        config: InjectionConfig,
        clipboard: ClipboardBackend | None = None,
        paste_runner: PasteRunner | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.clipboard = clipboard or MacClipboardBackend()
        self.paste_runner = paste_runner or AppleScriptPasteRunner()
        self.logger = logger or logging.getLogger("codexvoice")

    def can_inject(self) -> bool:
        return self.clipboard.available() and self.paste_runner.available()

    def inject(self, text: str) -> InjectionResult:
        if not text:
            return InjectionResult(ok=False, method="clipboard", error="empty text")
        if not self.can_inject():
            return InjectionResult(ok=False, method="clipboard", error="clipboard injection is not available")

        original: str | None = None
        try:
            original = self.clipboard.read()
            self.clipboard.write(text)
            self.paste_runner.paste(self.config.paste_delay_ms / 1000)
            return InjectionResult(ok=True, method="clipboard")
        except Exception as exc:
            return InjectionResult(ok=False, method="clipboard", error=str(exc))
        finally:
            if self.config.restore_clipboard and original is not None:
                try:
                    self.clipboard.write(original)
                except Exception:
                    self.logger.exception("Failed to restore clipboard")

