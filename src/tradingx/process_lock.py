from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


class RuntimeLockError(RuntimeError):
    """Raised when another TradingX process already owns the data root lock."""


@contextmanager
def runtime_process_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeLockError(
                "Another TradingX process already controls this data root. "
                f"Refusing to start while lock file {lock_path} is held."
            ) from error
        handle.seek(0)
        handle.truncate()
        handle.write(
            "\n".join(
                (
                    f"pid={os.getpid()}",
                    f"started_at_utc={datetime.now(UTC).isoformat()}",
                )
            )
            + "\n"
        )
        handle.flush()
        try:
            yield
        finally:
            handle.seek(0)
            handle.truncate()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


__all__ = ("RuntimeLockError", "runtime_process_lock")
