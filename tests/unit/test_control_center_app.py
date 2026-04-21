from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_control_center_app_wrapper_uses_repo_root_paths(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    app_script_source = (
        Path(__file__).resolve().parents[2]
        / "TradingX Control Center.app"
        / "Contents"
        / "MacOS"
        / "TradingXControlCenter"
    )
    app_script_path = (
        repo_root
        / "TradingX Control Center.app"
        / "Contents"
        / "MacOS"
        / "TradingXControlCenter"
    )
    app_script_path.parent.mkdir(parents=True, exist_ok=True)
    app_script_path.write_text(app_script_source.read_text(encoding="utf-8"))
    app_script_path.chmod(0o755)

    env_file = repo_root / ".env"
    env_file.write_text("ALPACA_PAPER_API_KEY=pk\nALPACA_PAPER_API_SECRET=sk\n")

    invocation_log = repo_root / "invocation.log"
    fake_python = repo_root / "fake-python"
    fake_python.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$PWD" > "$TEST_LOG"\n'
        'printf \'%s\\n\' "$@" >> "$TEST_LOG"\n'
        'printf \'{"status":"started","dashboard_url":"http://127.0.0.1:8765","reused_existing_server":false}\\n\'\n',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    python_bin = repo_root / ".venv" / "bin" / "python"
    python_bin.parent.mkdir(parents=True, exist_ok=True)
    python_bin.symlink_to(fake_python)
    (repo_root / ".venv" / "lib" / "python3.12" / "site-packages").mkdir(
        parents=True, exist_ok=True
    )

    completed = subprocess.run(
        [str(app_script_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "TEST_LOG": str(invocation_log),
        },
        check=False,
    )

    assert completed.returncode == 0
    lines = invocation_log.read_text(encoding="utf-8").splitlines()
    assert lines[0] == str(repo_root)
    assert lines[1:] == [
        "-m",
        "tradingx",
        "launch-control-center",
        "--env-file",
        str(env_file),
    ]
