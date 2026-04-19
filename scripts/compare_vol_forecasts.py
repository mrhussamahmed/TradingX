#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from arch import arch_model

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tradingx.backtest import load_ohlcv_csv, run_daily_bar_backtest
from tradingx.config import TradingConfig
from tradingx.costs import CostModelConfig
from tradingx.data import build_default_market_data_gateway
from tradingx.features.volatility import TRADING_DAYS_PER_YEAR, volatility_scale
from tradingx.signals.trend import generate_trend_signal
from tradingx.sizing import KELLY_FRACTION, MAX_GROSS_LEVERAGE, TARGET_VOLATILITY
from tradingx.stats import lo_adjusted_sharpe_ratio
from tradingx.strategy import CANONICAL_STAGE1_UNIVERSE


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


def _parse_symbols(value: str | None) -> tuple[str, ...]:
    if not value:
        return CANONICAL_STAGE1_UNIVERSE
    return tuple(symbol.strip().upper() for symbol in value.split(",") if symbol.strip())


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare realized, EWMA, and GARCH volatility forecasts."
    )
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--ohlcv-dir", default=None)
    parser.add_argument("--symbols", default=",".join(CANONICAL_STAGE1_UNIVERSE))
    parser.add_argument("--window-start", default=None)
    parser.add_argument("--window-end", default=None)
    parser.add_argument("--artifact-dir", default="artifacts/research")
    parser.add_argument("--output-file", default=None)
    parser.add_argument("--realized-window", type=int, default=20)
    parser.add_argument("--ewma-lambda", type=float, default=0.94)
    parser.add_argument("--garch-train-size", type=int, default=252)
    return parser


def _load_bars_from_csv_dir(
    directory: Path,
    *,
    symbols: tuple[str, ...],
    start_utc: datetime | None,
    end_utc: datetime | None,
) -> dict[str, pd.DataFrame]:
    bars_by_symbol = {}
    for symbol in symbols:
        frame = load_ohlcv_csv(directory / f"{symbol}.csv")
        if start_utc is not None:
            frame = frame.loc[frame.index >= start_utc]
        if end_utc is not None:
            frame = frame.loc[frame.index <= end_utc]
        bars_by_symbol[symbol] = frame
    return bars_by_symbol


def _load_bars_from_alpaca(
    *,
    env_file: Path,
    symbols: tuple[str, ...],
    start_utc: datetime,
    end_utc: datetime,
) -> dict[str, pd.DataFrame]:
    config = TradingConfig.from_env_file(env_file)
    gateway = build_default_market_data_gateway(config)
    return {
        symbol: gateway.get_daily_bar_history(
            symbol,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        for symbol in symbols
    }


def _align_bars(bars_by_symbol: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    common_index = None
    for frame in bars_by_symbol.values():
        common_index = frame.index if common_index is None else common_index.intersection(frame.index)
    if common_index is None or common_index.empty:
        raise ValueError("vol forecast comparison requires aligned daily bars.")
    return {
        symbol: frame.loc[common_index].astype(float).copy()
        for symbol, frame in bars_by_symbol.items()
    }


def _realized_daily_vol(returns: pd.Series, *, window: int) -> pd.Series:
    return returns.astype(float).shift(1).rolling(window).std(ddof=1)


def _ewma_daily_vol(returns: pd.Series, *, ewma_lambda: float) -> pd.Series:
    squared_returns = returns.astype(float).pow(2.0).shift(1)
    ewma_variance = squared_returns.ewm(alpha=1.0 - ewma_lambda, adjust=False).mean()
    return ewma_variance.pow(0.5)


def _garch_daily_vol(returns: pd.Series, *, train_size: int) -> pd.Series:
    clean_returns = returns.dropna().astype(float)
    if len(clean_returns) <= train_size:
        return pd.Series(index=returns.index, dtype=float)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = arch_model(
            clean_returns * 100.0,
            vol="Garch",
            p=1,
            q=1,
            mean="Zero",
            dist="normal",
            rescale=False,
        )
        fitted = model.fit(last_obs=train_size - 1, disp="off")
        forecast = fitted.forecast(horizon=1, start=train_size, reindex=True)

    variance = forecast.variance["h.1"] / 10_000.0
    return variance.pow(0.5).reindex(returns.index)


def _method_forecasts(
    bars_by_symbol: dict[str, pd.DataFrame],
    *,
    realized_window: int,
    ewma_lambda: float,
    garch_train_size: int,
) -> dict[str, dict[str, pd.Series]]:
    forecasts: dict[str, dict[str, pd.Series]] = {
        "realized": {},
        "ewma": {},
        "garch": {},
    }
    for symbol, bars in bars_by_symbol.items():
        returns = bars["close"].astype(float).pct_change()
        forecasts["realized"][symbol] = _realized_daily_vol(
            returns,
            window=realized_window,
        )
        forecasts["ewma"][symbol] = _ewma_daily_vol(
            returns,
            ewma_lambda=ewma_lambda,
        )
        forecasts["garch"][symbol] = _garch_daily_vol(
            returns,
            train_size=garch_train_size,
        )
    return forecasts


def _forecast_error_metrics(
    bars_by_symbol: dict[str, pd.DataFrame],
    forecasts: dict[str, dict[str, pd.Series]],
) -> dict[str, dict[str, object]]:
    metrics: dict[str, dict[str, object]] = {}
    for method_name, method_series in forecasts.items():
        symbol_metrics: dict[str, dict[str, float | int]] = {}
        pooled_errors: list[float] = []
        pooled_squared_errors: list[float] = []
        for symbol, forecast in method_series.items():
            actual = bars_by_symbol[symbol]["close"].astype(float).pct_change().abs()
            valid = actual.notna() & forecast.notna()
            errors = (forecast.loc[valid] - actual.loc[valid]).abs()
            squared_errors = (forecast.loc[valid] - actual.loc[valid]).pow(2.0)
            symbol_metrics[symbol] = {
                "prediction_count": int(valid.sum()),
                "mae": float(errors.mean()) if not errors.empty else float("nan"),
                "rmse": (
                    float(math.sqrt(squared_errors.mean()))
                    if not squared_errors.empty
                    else float("nan")
                ),
            }
            pooled_errors.extend(float(value) for value in errors.tolist())
            pooled_squared_errors.extend(float(value) for value in squared_errors.tolist())
        metrics[method_name] = {
            "prediction_count": len(pooled_errors),
            "pooled_mae": (
                sum(pooled_errors) / len(pooled_errors) if pooled_errors else float("nan")
            ),
            "pooled_rmse": (
                math.sqrt(sum(pooled_squared_errors) / len(pooled_squared_errors))
                if pooled_squared_errors
                else float("nan")
            ),
            "symbols": symbol_metrics,
        }
    return metrics


def _normalize_target_weights(target_weights: pd.DataFrame) -> pd.DataFrame:
    normalized = target_weights.fillna(0.0).astype(float).copy()
    gross_exposure = normalized.abs().sum(axis=1)
    for timestamp in normalized.index[gross_exposure > 1.0]:
        normalized.loc[timestamp] = normalized.loc[timestamp] / float(
            gross_exposure.loc[timestamp]
        )
    return normalized


def _backtest_metrics_for_method(
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    annualized_forecasts: dict[str, pd.Series],
    garch_train_size: int,
) -> dict[str, float]:
    target_weights = {}
    for symbol, bars in bars_by_symbol.items():
        signal = generate_trend_signal(bars)
        leverage = volatility_scale(
            target_vol=TARGET_VOLATILITY,
            realized_vol=annualized_forecasts[symbol],
            max_gross_leverage=MAX_GROSS_LEVERAGE,
        )
        target_weights[symbol] = (signal.astype(float) * KELLY_FRACTION * leverage).clip(
            lower=-MAX_GROSS_LEVERAGE,
            upper=MAX_GROSS_LEVERAGE,
        )

    target_weight_frame = _normalize_target_weights(
        pd.DataFrame(target_weights, index=next(iter(target_weights.values())).index)
    )
    result = run_daily_bar_backtest(
        bars_by_symbol,
        target_weights=target_weight_frame,
        cost_model_config=CostModelConfig(half_spread_multiplier=0.0),
    )
    oos_returns = result.portfolio_returns.iloc[garch_train_size:]
    sharpe = lo_adjusted_sharpe_ratio(
        returns=[float(value) for value in oos_returns.tolist()],
        risk_free_daily_rates=[0.0] * len(oos_returns),
        periods_per_year=TRADING_DAYS_PER_YEAR,
    )
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in oos_returns.tolist():
        equity *= 1.0 + float(value)
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, (equity / peak) - 1.0)
    total_return = equity - 1.0
    return {
        "sharpe_ratio": 0.0 if sharpe is None else float(sharpe),
        "total_return": float(total_return),
        "max_drawdown": abs(float(max_drawdown)),
    }


def _backtest_metrics(
    bars_by_symbol: dict[str, pd.DataFrame],
    forecasts: dict[str, dict[str, pd.Series]],
    *,
    garch_train_size: int,
) -> dict[str, dict[str, float]]:
    annualized_forecasts = {
        method_name: {
            symbol: forecast * math.sqrt(TRADING_DAYS_PER_YEAR)
            for symbol, forecast in method_series.items()
        }
        for method_name, method_series in forecasts.items()
    }
    return {
        method_name: _backtest_metrics_for_method(
            bars_by_symbol=bars_by_symbol,
            annualized_forecasts=forecast_by_symbol,
            garch_train_size=garch_train_size,
        )
        for method_name, forecast_by_symbol in annualized_forecasts.items()
    }


def _material_garch_win(
    *,
    forecast_metrics: dict[str, dict[str, object]],
    backtest_metrics: dict[str, dict[str, float]],
) -> bool:
    garch_mae = float(forecast_metrics["garch"]["pooled_mae"])
    realized_mae = float(forecast_metrics["realized"]["pooled_mae"])
    ewma_mae = float(forecast_metrics["ewma"]["pooled_mae"])
    if not math.isfinite(garch_mae) or not math.isfinite(realized_mae):
        return False
    mae_improvement = (
        (realized_mae - garch_mae) / realized_mae if realized_mae > 0.0 else 0.0
    )
    sharpe_improvement = (
        backtest_metrics["garch"]["sharpe_ratio"]
        - backtest_metrics["realized"]["sharpe_ratio"]
    )
    return garch_mae < min(realized_mae, ewma_mae) and (
        mae_improvement >= 0.10 or sharpe_improvement >= 0.10
    )


def _default_output_path(artifact_dir: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return artifact_dir / f"vol-forecast-comparison-{timestamp}.json"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    symbols = _parse_symbols(args.symbols)
    start_utc = _parse_datetime(args.window_start)
    end_utc = _parse_datetime(args.window_end) or datetime.now(UTC)

    if args.ohlcv_dir:
        bars_by_symbol = _load_bars_from_csv_dir(
            Path(args.ohlcv_dir),
            symbols=symbols,
            start_utc=start_utc,
            end_utc=end_utc,
        )
    else:
        resolved_start = start_utc or (end_utc - timedelta(days=365 * 5))
        bars_by_symbol = _load_bars_from_alpaca(
            env_file=Path(args.env_file),
            symbols=symbols,
            start_utc=resolved_start,
            end_utc=end_utc,
        )

    aligned_bars = _align_bars(bars_by_symbol)
    forecasts = _method_forecasts(
        aligned_bars,
        realized_window=args.realized_window,
        ewma_lambda=float(args.ewma_lambda),
        garch_train_size=int(args.garch_train_size),
    )
    forecast_metrics = _forecast_error_metrics(aligned_bars, forecasts)
    backtest_metrics = _backtest_metrics(
        aligned_bars,
        forecasts,
        garch_train_size=int(args.garch_train_size),
    )
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output_file) if args.output_file else _default_output_path(
        artifact_dir
    )
    summary = {
        "symbols": list(symbols),
        "window_start_utc": next(iter(aligned_bars.values())).index[0].to_pydatetime(),
        "window_end_utc": next(iter(aligned_bars.values())).index[-1].to_pydatetime(),
        "forecast_metrics": forecast_metrics,
        "backtest_metrics": backtest_metrics,
        "garch_material_win": _material_garch_win(
            forecast_metrics=forecast_metrics,
            backtest_metrics=backtest_metrics,
        ),
        "assumptions": [
            "Forecast errors compare daily volatility forecasts to same-day absolute close-to-close returns.",
            "Backtest sizing uses the existing long-only trend signal with 33% Kelly scaling and gross exposure capped at 1.0.",
            "Net-of-cost backtests disable half-spread costs because daily bars do not include bid/ask quotes.",
        ],
        "artifact_path": output_path,
    }
    output_path.write_text(
        json.dumps(_serialize(summary), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(_serialize(summary), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
