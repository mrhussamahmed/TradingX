from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest


def test_run_backtest_script_emits_smoke_summary_json(tmp_path: Path) -> None:
    csv_path = tmp_path / "spy.csv"
    pd.DataFrame(
        {
            "timestamp": [
                "2026-04-13T00:00:00+00:00",
                "2026-04-14T00:00:00+00:00",
                "2026-04-15T00:00:00+00:00",
                "2026-04-16T00:00:00+00:00",
            ],
            "open": [100.0, 110.0, 121.0, 118.0],
            "high": [110.0, 121.0, 121.0, 130.0],
            "low": [100.0, 110.0, 118.0, 118.0],
            "close": [110.0, 121.0, 118.0, 130.0],
            "volume": [1_000_000.0, 1_000_000.0, 1_000_000.0, 1_000_000.0],
        }
    ).to_csv(csv_path, index=False)

    risk_free_path = tmp_path / "risk_free_daily.csv"
    pd.DataFrame(
        {
            "date": ["2026-04-13", "2026-04-14", "2026-04-15", "2026-04-16"],
            "annualized_rate": [0.0, 0.0, 0.0, 0.0],
            "daily_rate": [0.0, 0.0, 0.0, 0.0],
        }
    ).to_csv(risk_free_path, index=False)

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "run_backtest.py"),
            "--symbol",
            "SPY",
            "--ohlcv-csv",
            str(csv_path),
            "--risk-free-csv",
            str(risk_free_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert payload["symbol"] == "SPY"
    assert payload["active"]["excess_sharpe"] == pytest.approx(0.0)
    assert payload["active"]["excess_cagr"] == pytest.approx(0.0)
