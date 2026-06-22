"""Single-instance process lock."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path


def default_lock_path() -> Path:
    return Path.home() / "Library" / "Application Support" / "CodexVoice" / "codexvoice.lock"


class SingleInstanceLock:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_lock_path()
        self._file = None
        self.acquired = False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.acquired = False
            return False
        self._file.seek(0)
        self._file.truncate()
        self._file.write(f"{os.getpid()}\n")
        self._file.flush()
        self.acquired = True
        return True

    def release(self) -> None:
        if self._file is None:
            return
        try:
            if self.acquired:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None
            self.acquired = False

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.release()

