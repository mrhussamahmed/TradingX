"""Minimal daily-bar backtest engine with explicit next-open execution.

The engine models portfolio state in two phases for each trading day:

- overnight close-to-open returns accrue to the existing position
- scheduled rebalances execute at the open
- intraday open-to-close returns accrue to the post-open position

This makes entries, exits, and overnight gaps auditable instead of
implicitly assuming close-to-close fills.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from tradingx.costs import CostModelConfig, estimate_trade_costs
from tradingx.risk_free import daily_risk_free_rate_for_date
from tradingx.stats import lo_adjusted_sharpe_ratio

TRADING_DAYS_PER_YEAR = 252
REQUIRED_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class DailyBarBacktestResult:
    portfolio_returns: pd.Series
    equity_curve: pd.Series
    applied_weights: pd.DataFrame
    scheduled_weights: pd.DataFrame


def run_daily_bar_backtest(
    bars_by_symbol: dict[str, pd.DataFrame],
    *,
    target_weights: pd.DataFrame,
    initial_weights: dict[str, float] | None = None,
    cost_model_config: CostModelConfig | None = None,
) -> DailyBarBacktestResult:
    _validate_inputs(bars_by_symbol, target_weights)

    symbols = tuple(target_weights.columns)
    normalized_initial_weights = {
        symbol: float((initial_weights or {}).get(symbol, 0.0)) for symbol in symbols
    }
    current_weights = normalized_initial_weights.copy()

    returns: list[float] = []
    applied_rows: list[dict[str, float]] = []
    equity_values: list[float] = []
    equity = 1.0

    for bar_offset, _timestamp in enumerate(target_weights.index):
        daily_growth = 1.0

        if bar_offset > 0:
            overnight_return = 0.0
            for symbol in symbols:
                symbol_bars = bars_by_symbol[symbol]
                previous_close = float(symbol_bars.iloc[bar_offset - 1]["close"])
                current_open = float(symbol_bars.iloc[bar_offset]["open"])
                overnight_return += current_weights[symbol] * (
                    (current_open / previous_close) - 1.0
                )
            daily_growth *= 1.0 + overnight_return
            if cost_model_config is not None:
                trade_cost_fraction = _trade_cost_fraction(
                    bars_by_symbol=bars_by_symbol,
                    current_weights=current_weights,
                    target_weights={
                        symbol: float(target_weights.iloc[bar_offset - 1][symbol])
                        for symbol in symbols
                    },
                    bar_offset=bar_offset,
                    equity=equity * daily_growth,
                    cost_model_config=cost_model_config,
                )
                daily_growth *= 1.0 - trade_cost_fraction
            current_weights = {
                symbol: float(target_weights.iloc[bar_offset - 1][symbol])
                for symbol in symbols
            }

        applied_rows.append(current_weights.copy())

        intraday_return = 0.0
        for symbol in symbols:
            symbol_bars = bars_by_symbol[symbol]
            current_open = float(symbol_bars.iloc[bar_offset]["open"])
            current_close = float(symbol_bars.iloc[bar_offset]["close"])
            intraday_return += current_weights[symbol] * (
                (current_close / current_open) - 1.0
            )
        daily_growth *= 1.0 + intraday_return
        equity *= daily_growth
        returns.append(daily_growth - 1.0)
        equity_values.append(equity)

    index = target_weights.index
    return DailyBarBacktestResult(
        portfolio_returns=pd.Series(returns, index=index, dtype=float, name="returns"),
        equity_curve=pd.Series(
            equity_values,
            index=index,
            dtype=float,
            name="equity",
        ),
        applied_weights=pd.DataFrame(applied_rows, index=index, dtype=float),
        scheduled_weights=target_weights.astype(float).copy(),
    )


def run_buy_and_hold_smoke_backtest(
    *,
    symbol: str,
    bars: pd.DataFrame,
    risk_free_cache_path: Path,
) -> dict[str, object]:
    target_weights = pd.DataFrame(
        {symbol: [1.0] * len(bars)},
        index=bars.index,
        dtype=float,
    )
    strategy = run_daily_bar_backtest(
        {symbol: bars},
        target_weights=target_weights,
        initial_weights={symbol: 1.0},
    )
    benchmark = run_daily_bar_backtest(
        {symbol: bars},
        target_weights=target_weights,
        initial_weights={symbol: 1.0},
    )
    strategy_metrics = summarize_returns(
        strategy.portfolio_returns,
        risk_free_cache_path=risk_free_cache_path,
    )
    benchmark_metrics = summarize_returns(
        benchmark.portfolio_returns,
        risk_free_cache_path=risk_free_cache_path,
    )

    return {
        "symbol": symbol,
        "window_start_utc": strategy.portfolio_returns.index[0].to_pydatetime(),
        "window_end_utc": strategy.portfolio_returns.index[-1].to_pydatetime(),
        "strategy": strategy_metrics,
        "benchmark": benchmark_metrics,
        "active": {
            "excess_cagr": strategy_metrics["cagr"] - benchmark_metrics["cagr"],
            "excess_sharpe": (
                strategy_metrics["sharpe_ratio"] - benchmark_metrics["sharpe_ratio"]
            ),
        },
    }


def load_ohlcv_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    expected_columns = ("timestamp", "open", "high", "low", "close", "volume")
    missing = tuple(
        column for column in expected_columns if column not in frame.columns
    )
    if missing:
        raise ValueError(
            "OHLCV CSV is missing required columns: " + ", ".join(missing) + "."
        )
    loaded = frame.loc[:, expected_columns].copy()
    loaded["timestamp"] = pd.to_datetime(loaded["timestamp"], utc=True)
    loaded = loaded.sort_values("timestamp", kind="stable").set_index("timestamp")
    return loaded.astype(float)


def summarize_returns(
    returns: pd.Series,
    *,
    risk_free_cache_path: Path,
) -> dict[str, float]:
    realized_returns = [float(value) for value in returns]
    risk_free_daily_rates = [
        daily_risk_free_rate_for_date(
            risk_free_cache_path,
            as_of_date=timestamp.date(),
        )
        for timestamp in returns.index
    ]
    sharpe = lo_adjusted_sharpe_ratio(
        returns=realized_returns,
        risk_free_daily_rates=risk_free_daily_rates,
        periods_per_year=TRADING_DAYS_PER_YEAR,
    )
    total_return = _total_return(realized_returns)
    max_drawdown = _max_drawdown(realized_returns)
    return {
        "total_return": total_return,
        "cagr": _cagr(total_return, len(realized_returns)),
        "sharpe_ratio": 0.0 if sharpe is None else sharpe,
        "max_drawdown": max_drawdown,
    }


def _validate_inputs(
    bars_by_symbol: dict[str, pd.DataFrame],
    target_weights: pd.DataFrame,
) -> None:
    if not bars_by_symbol:
        raise ValueError("bars_by_symbol must not be empty.")
    if target_weights.empty:
        raise ValueError("target_weights must not be empty.")

    symbols = tuple(target_weights.columns)
    if set(symbols) != set(bars_by_symbol):
        raise ValueError("target_weights columns must match the bars_by_symbol keys.")

    reference_index = target_weights.index
    for symbol, bars in bars_by_symbol.items():
        missing = tuple(
            column for column in REQUIRED_OHLCV_COLUMNS if column not in bars
        )
        if missing:
            raise ValueError(
                f"{symbol} bars are missing required OHLCV columns: "
                + ", ".join(missing)
                + "."
            )
        if not bars.index.equals(reference_index):
            raise ValueError("All bar frames must share the target_weights index.")


def _trade_cost_fraction(
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    bar_offset: int,
    equity: float,
    cost_model_config: CostModelConfig,
) -> float:
    if equity <= 0.0:
        return 0.0

    total_cost = 0.0
    for symbol, current_weight in current_weights.items():
        target_weight = target_weights[symbol]
        delta_weight = target_weight - current_weight
        if delta_weight == 0.0:
            continue

        symbol_bars = bars_by_symbol[symbol]
        current_bar = symbol_bars.iloc[bar_offset]
        fill_price = float(current_bar["open"])
        trade_notional = abs(delta_weight) * equity
        quantity = trade_notional / fill_price if fill_price > 0.0 else 0.0
        bid_price = float(current_bar["bid"]) if "bid" in symbol_bars.columns else None
        ask_price = float(current_bar["ask"]) if "ask" in symbol_bars.columns else None
        sigma_20d_bps = _sigma_20d_bps(symbol_bars["close"], bar_offset)
        daily_dollar_volume = float(current_bar["volume"]) * fill_price
        trade_costs = estimate_trade_costs(
            side="buy" if delta_weight > 0.0 else "sell",
            quantity=quantity,
            fill_price=fill_price,
            bid_price=bid_price,
            ask_price=ask_price,
            daily_dollar_volume=daily_dollar_volume,
            sigma_20d_bps=sigma_20d_bps,
            config=cost_model_config,
        )
        total_cost += trade_costs.total
    return total_cost / equity


def _sigma_20d_bps(close_series: pd.Series, bar_offset: int) -> float:
    if bar_offset <= 0:
        return 0.0
    close_returns = close_series.astype(float).pct_change()
    window = close_returns.iloc[max(0, bar_offset - 20) : bar_offset]
    if len(window.dropna()) < 2:
        return 0.0
    return float(window.std(ddof=1) * 10_000.0)


def _total_return(returns: list[float]) -> float:
    equity = 1.0
    for value in returns:
        equity *= 1.0 + value
    return equity - 1.0


def _cagr(total_return: float, periods: int) -> float:
    if periods <= 0:
        return 0.0
    return float((1.0 + total_return) ** (TRADING_DAYS_PER_YEAR / periods) - 1.0)


def _max_drawdown(returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        drawdown = (equity / peak) - 1.0
        max_drawdown = min(max_drawdown, drawdown)
    return abs(max_drawdown)


__all__ = (
    "CostModelConfig",
    "DailyBarBacktestResult",
    "REQUIRED_OHLCV_COLUMNS",
    "TRADING_DAYS_PER_YEAR",
    "load_ohlcv_csv",
    "run_buy_and_hold_smoke_backtest",
    "run_daily_bar_backtest",
    "summarize_returns",
)
