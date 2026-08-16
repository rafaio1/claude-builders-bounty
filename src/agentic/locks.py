from __future__ import annotations

import fcntl
import time
from pathlib import Path
from typing import Any


class AlreadyRunningError(RuntimeError):
    pass


class RunLock:
    def __init__(
        self,
        path: Path,
        *,
        busy: str = "outro processo do Agentic já está rodando",
        wait_seconds: float = 0,
    ) -> None:
        self.path = path
        self.busy = busy
        self.handle = None
        self.wait_seconds = max(0.0, float(wait_seconds))

    def __enter__(self) -> "RunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        deadline = time.monotonic() + self.wait_seconds
        while True:
            try:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    self.handle.close()
                    self.handle = None
                    raise AlreadyRunningError(self.busy)
                time.sleep(min(1.0, max(0.1, deadline - time.monotonic())))

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if not self.handle:
            return
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()
        self.handle = None
