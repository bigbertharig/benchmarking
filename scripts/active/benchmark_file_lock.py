"""Small stdlib advisory file lock for benchmark result writers on Linux."""

from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path


class BenchmarkFileLock:
    """Serialize access to a lock path, failing instead of waiting indefinitely."""

    def __init__(self, path: str | Path, timeout: float = 30) -> None:
        self.path = Path(path)
        self.timeout = timeout
        self._handle = None

    def __enter__(self) -> "BenchmarkFileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+", encoding="utf-8")
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    self._handle.close()
                    self._handle = None
                    raise TimeoutError(f"timed out acquiring benchmark lock: {self.path}")
                time.sleep(0.1)

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None
