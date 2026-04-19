from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def _write_ohlcv_csv(path: Path, *, seed_price: float) -> None:
    timestamps = pd.date_range("2025-01-02", periods=120, freq="B", tz="UTC")
    closes: list[float] = []
    price = seed_price
    for offset, _timestamp in enumerate(timestamps):
        daily_return = 0.004 if offset % 9 else -0.012
        price *= 1.0 + daily_return
        closes.append(price)
    close_series = pd.Series(closes, index=timestamps, dtype=float)
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close_series.shift(1).fillna(close_series.iloc[0]),
            "high": close_series * 1.01,
            "low": close_series * 0.99,
            "close": close_series,
            "volume": 1_000_000.0,
        }
    )
    frame.to_csv(path, index=False)


def test_compare_vol_forecasts_script_writes_artifact_and_summary(
    tmp_path: Path,
) -> None:
    csv_dir = tmp_path / "ohlcv"
    csv_dir.mkdir()
    _write_ohlcv_csv(csv_dir / "SPY.csv", seed_price=100.0)
    _write_ohlcv_csv(csv_dir / "QQQ.csv", seed_price=90.0)
    output_file = tmp_path / "artifact.json"

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "compare_vol_forecasts.py"),
            "--ohlcv-dir",
            str(csv_dir),
            "--symbols",
            "SPY,QQQ",
            "--output-file",
            str(output_file),
            "--garch-train-size",
            "60",
            "--realized-window",
            "20",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert output_file.exists()
    assert payload["symbols"] == ["SPY", "QQQ"]
    assert set(payload["forecast_metrics"]) == {"realized", "ewma", "garch"}
    assert set(payload["backtest_metrics"]) == {"realized", "ewma", "garch"}
    assert isinstance(payload["garch_material_win"], bool)
