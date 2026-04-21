from __future__ import annotations

import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from tradingx.config import TradingConfig


class BackgroundProcessProtocol(Protocol):
    def poll(self) -> int | None: ...


HealthcheckProtocol = Callable[[str], bool]
BrowserOpenerProtocol = Callable[[str], None]
SleepProtocol = Callable[[float], None]
MonotonicProtocol = Callable[[], float]


class ControlCenterLaunchError(RuntimeError):
    """Raised when the local TradingX control center cannot be launched."""


@dataclass(frozen=True)
class ControlCenterLaunchResult:
    status: str
    dashboard_url: str
    reused_existing_server: bool


def launch_control_center(
    *,
    config: TradingConfig,
    repo_root: Path,
    env_file: Path,
    healthcheck: HealthcheckProtocol | None = None,
    spawn_process: Callable[..., BackgroundProcessProtocol] | None = None,
    open_browser: BrowserOpenerProtocol | None = None,
    sleep_fn: SleepProtocol | None = None,
    monotonic_fn: MonotonicProtocol | None = None,
    readiness_timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.5,
) -> ControlCenterLaunchResult:
    resolved_healthcheck: HealthcheckProtocol = (
        _default_healthcheck if healthcheck is None else healthcheck
    )
    resolved_spawn_process = (
        _spawn_web_process if spawn_process is None else spawn_process
    )
    resolved_open_browser: BrowserOpenerProtocol = (
        _open_browser if open_browser is None else open_browser
    )
    resolved_sleep_fn: SleepProtocol = time.sleep if sleep_fn is None else sleep_fn
    resolved_monotonic_fn: MonotonicProtocol = (
        time.monotonic if monotonic_fn is None else monotonic_fn
    )

    dashboard_url = _dashboard_url(config)
    health_urls = _healthcheck_urls(dashboard_url)

    if _all_healthchecks_ready(health_urls, healthcheck=resolved_healthcheck):
        resolved_open_browser(dashboard_url)
        return ControlCenterLaunchResult(
            status="connected",
            dashboard_url=dashboard_url,
            reused_existing_server=True,
        )

    process = resolved_spawn_process(
        repo_root=repo_root,
        env_file=env_file,
        host=config.web.host,
        port=config.web.port,
    )
    deadline = resolved_monotonic_fn() + readiness_timeout_seconds

    while resolved_monotonic_fn() < deadline:
        if _all_healthchecks_ready(health_urls, healthcheck=resolved_healthcheck):
            resolved_open_browser(dashboard_url)
            return ControlCenterLaunchResult(
                status="started",
                dashboard_url=dashboard_url,
                reused_existing_server=False,
            )

        exit_code = process.poll()
        if exit_code is not None:
            raise ControlCenterLaunchError(
                "TradingX control center exited before becoming ready "
                f"(exit code {exit_code})."
            )

        resolved_sleep_fn(poll_interval_seconds)

    if _all_healthchecks_ready(health_urls, healthcheck=resolved_healthcheck):
        resolved_open_browser(dashboard_url)
        return ControlCenterLaunchResult(
            status="started",
            dashboard_url=dashboard_url,
            reused_existing_server=False,
        )

    raise ControlCenterLaunchError(
        "TradingX control center did not become ready within "
        f"{int(readiness_timeout_seconds)} seconds."
    )


def _dashboard_url(config: TradingConfig) -> str:
    browser_host = "127.0.0.1" if config.web.host == "0.0.0.0" else config.web.host
    return f"http://{browser_host}:{config.web.port}"


def _healthcheck_urls(dashboard_url: str) -> tuple[str, ...]:
    return (
        f"{dashboard_url}/api/config/summary",
        f"{dashboard_url}/api/platform/portfolio",
    )


def _all_healthchecks_ready(
    health_urls: tuple[str, ...],
    *,
    healthcheck: HealthcheckProtocol,
) -> bool:
    return all(healthcheck(url) for url in health_urls)


def _default_healthcheck(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            status_code = int(response.status)
            return 200 <= status_code < 300
    except (OSError, urllib.error.URLError):
        return False


def _open_browser(url: str) -> None:
    webbrowser.open(url, new=1)


def _spawn_web_process(
    *,
    repo_root: Path,
    env_file: Path,
    host: str,
    port: int,
) -> subprocess.Popen[bytes]:
    log_path = _control_center_log_path(config_root=repo_root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log_handle:
        return subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tradingx",
                "web",
                "--env-file",
                str(env_file),
                "--host",
                host,
                "--port",
                str(port),
            ],
            cwd=repo_root,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _control_center_log_path(*, config_root: Path) -> Path:
    return config_root / "data" / "logs" / "control_center_web.log"


__all__ = (
    "ControlCenterLaunchError",
    "ControlCenterLaunchResult",
    "launch_control_center",
)
