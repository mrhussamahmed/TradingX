from __future__ import annotations

from pathlib import Path

import pytest

from tradingx.config import TradingConfig
from tradingx.launcher import (
    ControlCenterLaunchError,
    ControlCenterLaunchResult,
    launch_control_center,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class FakeProcess:
    def __init__(self, exit_codes: list[int | None]) -> None:
        self._exit_codes = exit_codes
        self._index = 0

    def poll(self) -> int | None:
        if self._index >= len(self._exit_codes):
            return self._exit_codes[-1]
        value = self._exit_codes[self._index]
        self._index += 1
        return value


def test_launch_control_center_reuses_existing_server() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_WEB_HOST": "127.0.0.1",
            "TRADINGX_WEB_PORT": "8765",
        }
    )
    health_urls: list[str] = []
    browser_urls: list[str] = []

    def healthcheck(url: str) -> bool:
        health_urls.append(url)
        return True

    def unexpected_spawn(*args, **kwargs):
        raise AssertionError("launcher should not spawn a new process")

    result = launch_control_center(
        config=config,
        repo_root=Path("/repo"),
        env_file=Path("/repo/.env"),
        healthcheck=healthcheck,
        spawn_process=unexpected_spawn,
        open_browser=browser_urls.append,
    )

    assert result == ControlCenterLaunchResult(
        status="connected",
        dashboard_url="http://127.0.0.1:8765",
        reused_existing_server=True,
    )
    assert health_urls == [
        "http://127.0.0.1:8765/api/config/summary",
        "http://127.0.0.1:8765/api/platform/portfolio",
    ]
    assert browser_urls == ["http://127.0.0.1:8765"]


def test_launch_control_center_starts_server_until_ready() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_WEB_HOST": "127.0.0.1",
            "TRADINGX_WEB_PORT": "8765",
        }
    )
    clock = FakeClock()
    browser_urls: list[str] = []
    spawn_calls: list[tuple[Path, Path, str, int]] = []
    health_results = {
        "http://127.0.0.1:8765/api/config/summary": [False, False, True],
        "http://127.0.0.1:8765/api/platform/portfolio": [False, False, True],
    }

    def healthcheck(url: str) -> bool:
        series = health_results[url]
        if len(series) == 1:
            return series[0]
        return series.pop(0)

    def spawn_process(
        *,
        repo_root: Path,
        env_file: Path,
        host: str,
        port: int,
    ) -> FakeProcess:
        spawn_calls.append((repo_root, env_file, host, port))
        return FakeProcess([None, None, None])

    result = launch_control_center(
        config=config,
        repo_root=Path("/repo"),
        env_file=Path("/repo/.env"),
        healthcheck=healthcheck,
        spawn_process=spawn_process,
        open_browser=browser_urls.append,
        sleep_fn=clock.sleep,
        monotonic_fn=clock.monotonic,
        readiness_timeout_seconds=5.0,
        poll_interval_seconds=1.0,
    )

    assert result == ControlCenterLaunchResult(
        status="started",
        dashboard_url="http://127.0.0.1:8765",
        reused_existing_server=False,
    )
    assert spawn_calls == [(Path("/repo"), Path("/repo/.env"), "127.0.0.1", 8765)]
    assert browser_urls == ["http://127.0.0.1:8765"]


def test_launch_control_center_restarts_when_server_lacks_routes() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_WEB_HOST": "127.0.0.1",
            "TRADINGX_WEB_PORT": "8765",
        }
    )
    clock = FakeClock()
    browser_urls: list[str] = []
    spawn_calls: list[tuple[Path, Path, str, int]] = []
    health_state = {
        "http://127.0.0.1:8765/api/config/summary": [True, True, True],
        "http://127.0.0.1:8765/api/platform/portfolio": [False, False, True],
    }
    health_urls: list[str] = []

    def healthcheck(url: str) -> bool:
        health_urls.append(url)
        series = health_state[url]
        if len(series) == 1:
            return series[0]
        return series.pop(0)

    def spawn_process(
        *,
        repo_root: Path,
        env_file: Path,
        host: str,
        port: int,
    ) -> FakeProcess:
        spawn_calls.append((repo_root, env_file, host, port))
        return FakeProcess([None, None, None])

    result = launch_control_center(
        config=config,
        repo_root=Path("/repo"),
        env_file=Path("/repo/.env"),
        healthcheck=healthcheck,
        spawn_process=spawn_process,
        open_browser=browser_urls.append,
        sleep_fn=clock.sleep,
        monotonic_fn=clock.monotonic,
        readiness_timeout_seconds=5.0,
        poll_interval_seconds=1.0,
    )

    assert result == ControlCenterLaunchResult(
        status="started",
        dashboard_url="http://127.0.0.1:8765",
        reused_existing_server=False,
    )
    assert spawn_calls == [(Path("/repo"), Path("/repo/.env"), "127.0.0.1", 8765)]
    assert health_urls[:2] == [
        "http://127.0.0.1:8765/api/config/summary",
        "http://127.0.0.1:8765/api/platform/portfolio",
    ]
    assert browser_urls == ["http://127.0.0.1:8765"]


def test_launch_control_center_times_out_when_server_never_becomes_ready() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_WEB_HOST": "127.0.0.1",
            "TRADINGX_WEB_PORT": "8765",
        }
    )
    clock = FakeClock()

    def healthcheck(url: str) -> bool:
        return False

    with pytest.raises(ControlCenterLaunchError, match="did not become ready"):
        launch_control_center(
            config=config,
            repo_root=Path("/repo"),
            env_file=Path("/repo/.env"),
            healthcheck=healthcheck,
            spawn_process=lambda **kwargs: FakeProcess([None, None, None, None]),
            open_browser=lambda url: None,
            sleep_fn=clock.sleep,
            monotonic_fn=clock.monotonic,
            readiness_timeout_seconds=1.0,
            poll_interval_seconds=0.5,
        )


def test_launch_control_center_raises_when_background_process_exits_early() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_WEB_HOST": "127.0.0.1",
            "TRADINGX_WEB_PORT": "8765",
        }
    )
    clock = FakeClock()

    with pytest.raises(ControlCenterLaunchError, match="exit code 17"):
        launch_control_center(
            config=config,
            repo_root=Path("/repo"),
            env_file=Path("/repo/.env"),
            healthcheck=lambda url: False,
            spawn_process=lambda **kwargs: FakeProcess([17]),
            open_browser=lambda url: None,
            sleep_fn=clock.sleep,
            monotonic_fn=clock.monotonic,
            readiness_timeout_seconds=5.0,
            poll_interval_seconds=1.0,
        )
