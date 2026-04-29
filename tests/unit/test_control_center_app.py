from __future__ import annotations

from pathlib import Path


def test_control_center_app_wrapper_uses_background_server_paths() -> None:
    app_script = (
        Path(__file__).resolve().parents[2]
        / "TradingX Control Center.app"
        / "Contents"
        / "MacOS"
        / "TradingXControlCenter"
    ).read_text(encoding="utf-8")

    assert "do shell script" in app_script
    assert "background_server_start_dispatched" in app_script
    assert "scripts/start_control_center_server.command" in app_script
    assert "Application Support/TradingX/runtime" in app_script
    assert 'tell application "Terminal"' not in app_script


def test_control_center_server_script_uses_repo_root_paths() -> None:
    server_script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "start_control_center_server.command"
    ).read_text(encoding="utf-8")

    assert 'REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"' in server_script
    assert 'repo_root + "/src"' in server_script
    assert '"web"' in server_script
