"""Cross-sectional mean reversion via SPY-residualized returns.

Sources:
- Khandani, A. E., and A. W. Lo, "What Happened To The Quants In August
  2007?", Journal of Investment Management 5(4), 2007.
- Lehmann, B. N., "Fads, Martingales, and Market Efficiency",
  Quarterly Journal of Economics 105(1), 1990.
"""

from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]

from tradingx.signals.trend import REQUIRED_OHLCV_COLUMNS

BETA_WINDOW_DAYS = 60
RESIDUAL_SUM_DAYS = 5
ZSCORE_WINDOW_DAYS = 60
ZSCORE_THRESHOLD = 2.0
PRE_SIZED = False


def generate_mean_revert_signal(
    ohlcv: pd.DataFrame,
    *,
    benchmark_symbol: str = "SPY",
    tradable_symbols: tuple[str, ...] | None = None,
    beta_window_days: int = BETA_WINDOW_DAYS,
    residual_sum_days: int = RESIDUAL_SUM_DAYS,
    zscore_window_days: int = ZSCORE_WINDOW_DAYS,
    zscore_threshold: float = ZSCORE_THRESHOLD,
) -> pd.DataFrame:
    closes = _close_matrix(ohlcv)
    if benchmark_symbol not in closes.columns:
        raise ValueError(
            f"benchmark_symbol '{benchmark_symbol}' is missing from OHLCV."
        )

    tradables = tradable_symbols or tuple(
        symbol for symbol in closes.columns if symbol != benchmark_symbol
    )
    if benchmark_symbol in tradables:
        raise ValueError("tradable_symbols must not include the benchmark symbol.")
    benchmark_returns = closes[benchmark_symbol].pct_change()
    signal = pd.DataFrame(0.0, index=closes.index, columns=tradables, dtype=float)

    for symbol in tradables:
        if symbol not in closes.columns:
            raise ValueError(f"tradable symbol '{symbol}' is missing from OHLCV.")
        symbol_returns = closes[symbol].pct_change()
        beta = symbol_returns.rolling(beta_window_days).cov(benchmark_returns) / (
            benchmark_returns.rolling(beta_window_days).var(ddof=1)
        )
        residual = symbol_returns - (beta * benchmark_returns)
        residual_sum = residual.rolling(
            residual_sum_days,
            min_periods=residual_sum_days,
        ).sum()
        residual_sum_history = residual_sum.shift(1)
        residual_std = (
            residual_sum.rolling(
                zscore_window_days,
                min_periods=zscore_window_days,
            )
            .std(ddof=1)
            .shift(1)
        )
        zscore = (residual_sum_history / residual_std).replace(
            [float("inf"), float("-inf")],
            pd.NA,
        )
        signal.loc[(zscore < (-1.0 * zscore_threshold)).fillna(False), symbol] = 1.0
        signal.loc[(zscore > zscore_threshold).fillna(False), symbol] = -1.0

    return signal


def _close_matrix(ohlcv: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(ohlcv.columns, pd.MultiIndex) or ohlcv.columns.nlevels != 2:
        raise ValueError(
            "mean_revert expects a wide OHLCV frame with MultiIndex columns."
        )
    fields = tuple(str(field) for field in ohlcv.columns.get_level_values(1).unique())
    missing = tuple(column for column in REQUIRED_OHLCV_COLUMNS if column not in fields)
    if missing:
        raise ValueError(
            "OHLCV frame is missing required columns: " + ", ".join(missing) + "."
        )
    return ohlcv.xs("close", axis=1, level=1).astype(float)


__all__ = (
    "BETA_WINDOW_DAYS",
    "PRE_SIZED",
    "RESIDUAL_SUM_DAYS",
    "ZSCORE_THRESHOLD",
    "ZSCORE_WINDOW_DAYS",
    "generate_mean_revert_signal",
)
