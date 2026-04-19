from __future__ import annotations

from pathlib import Path

import pytest

from tradingx.process_lock import RuntimeLockError, runtime_process_lock


def test_runtime_process_lock_rejects_second_holder(tmp_path: Path) -> None:
    lock_path = tmp_path / "runtime.pid"

    with runtime_process_lock(lock_path):
        with pytest.raises(RuntimeLockError):
            with runtime_process_lock(lock_path):
                pass


def test_runtime_process_lock_releases_on_exit(tmp_path: Path) -> None:
    lock_path = tmp_path / "runtime.pid"

    with runtime_process_lock(lock_path):
        pass

    with runtime_process_lock(lock_path):
        assert lock_path.exists()
