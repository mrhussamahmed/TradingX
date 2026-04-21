#!/usr/bin/env python3
# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from datetime import UTC, datetime, timedelta
from decimal import Decimal
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
from tradingx.portfolio_construction import (
    PortfolioConstructionConfig,
    build_target_weight_history,
)
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
    return tuple(
        symbol.strip().upper() for symbol in value.split(",") if symbol.strip()
    )


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
        common_index = (
            frame.index
            if common_index is None
            else common_index.intersection(frame.index)
        )
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
        pooled_qlike: list[float] = []
        for symbol, forecast in method_series.items():
            actual_variance = (
                bars_by_symbol[symbol]["close"].astype(float).pct_change().pow(2.0)
            )
            forecast_variance = forecast.pow(2.0)
            valid = actual_variance.notna() & forecast_variance.notna()
            valid_index = actual_variance.loc[valid].index
            variance_error = (
                forecast_variance.loc[valid_index] - actual_variance.loc[valid_index]
            )
            errors = variance_error.abs()
            squared_errors = variance_error.pow(2.0)
            clipped_forecast_variance = forecast_variance.loc[valid_index].clip(
                lower=1e-12
            )
            qlike = (
                actual_variance.loc[valid_index] / clipped_forecast_variance
            ) + clipped_forecast_variance.map(math.log)
            symbol_metrics[symbol] = {
                "prediction_count": int(valid.sum()),
                "variance_mae": (
                    float(errors.mean()) if not errors.empty else float("nan")
                ),
                "variance_rmse": (
                    float(math.sqrt(squared_errors.mean()))
                    if not squared_errors.empty
                    else float("nan")
                ),
                "qlike": float(qlike.mean()) if not qlike.empty else float("nan"),
            }
            pooled_errors.extend(float(value) for value in errors.tolist())
            pooled_squared_errors.extend(
                float(value) for value in squared_errors.tolist()
            )
            pooled_qlike.extend(float(value) for value in qlike.tolist())
        metrics[method_name] = {
            "prediction_count": len(pooled_errors),
            "pooled_variance_mae": (
                (sum(pooled_errors) / len(pooled_errors))
                if pooled_errors
                else float("nan")
            ),
            "pooled_variance_rmse": (
                math.sqrt(sum(pooled_squared_errors) / len(pooled_squared_errors))
                if pooled_squared_errors
                else float("nan")
            ),
            "pooled_qlike": (
                sum(pooled_qlike) / len(pooled_qlike) if pooled_qlike else float("nan")
            ),
            "symbols": symbol_metrics,
        }
    return metrics


def _backtest_metrics_for_method(
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    annualized_forecasts: dict[str, pd.Series],
    garch_train_size: int,
) -> dict[str, float]:
    sleeve_weights = {}
    for symbol, bars in bars_by_symbol.items():
        signal = generate_trend_signal(bars)
        leverage = volatility_scale(
            target_vol=TARGET_VOLATILITY,
            realized_vol=annualized_forecasts[symbol],
            max_gross_leverage=MAX_GROSS_LEVERAGE,
        )
        sleeve_weights[symbol] = (
            signal.astype(float) * KELLY_FRACTION * leverage
        ).clip(
            lower=-MAX_GROSS_LEVERAGE,
            upper=MAX_GROSS_LEVERAGE,
        )

    target_weight_frame = build_target_weight_history(
        sleeve_signals={
            "trend_following": pd.DataFrame(
                sleeve_weights,
                index=next(iter(sleeve_weights.values())).index,
                dtype=float,
            )
        },
        account_equity=Decimal("100000"),
        config=PortfolioConstructionConfig(crash_overlay_symbol="SPY"),
        benchmark_bars=bars_by_symbol.get("SPY"),
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
    garch_qlike = float(forecast_metrics["garch"]["pooled_qlike"])
    realized_qlike = float(forecast_metrics["realized"]["pooled_qlike"])
    ewma_qlike = float(forecast_metrics["ewma"]["pooled_qlike"])
    if not math.isfinite(garch_qlike) or not math.isfinite(realized_qlike):
        return False
    qlike_improvement = (
        (realized_qlike - garch_qlike) / realized_qlike
        if realized_qlike > 0.0
        else 0.0
    )
    sharpe_improvement = (
        backtest_metrics["garch"]["sharpe_ratio"]
        - backtest_metrics["realized"]["sharpe_ratio"]
    )
    return garch_qlike < min(realized_qlike, ewma_qlike) and (
        qlike_improvement >= 0.10 or sharpe_improvement >= 0.10
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
            (
                "Forecast errors use variance loss (MAE/RMSE on squared returns) "
                "plus QLIKE instead of comparing volatility directly to absolute "
                "returns."
            ),
            (
                "Backtest sizing uses the existing long-only trend sleeve and the "
                "same portfolio construction path used by research backtests."
            ),
            (
                "Net-of-cost backtests disable half-spread costs because daily "
                "bars do not include bid/ask quotes."
            ),
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
