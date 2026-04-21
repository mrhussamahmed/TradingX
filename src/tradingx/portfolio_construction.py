"""Portfolio construction helpers for research backtests and runtime weights.

This module combines sleeve-level target-weight frames into portfolio-level
weights, then applies portfolio controls such as concentration, gross-exposure,
position-count, no-trade-band, and crash-overlay adjustments.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]

from tradingx.features.volatility import realized_vol
from tradingx.signals.mean_revert import generate_mean_revert_signal
from tradingx.signals.trend import generate_trend_signal
from tradingx.signals.vol_target_spy import generate_vol_target_spy_signal
from tradingx.sizing import apply_position_sizing
from tradingx.types import StrategyCandidate


@dataclass(frozen=True)
class PortfolioConstructionConfig:
    concentration_cap: float = 0.20
    gross_exposure_cap: float = 1.0
    max_positions: int = 10
    min_trade_notional: Decimal = Decimal("50")
    min_trade_fraction_of_equity: Decimal = Decimal("0.0025")
    crash_overlay_factor: float = 0.5
    crash_overlay_vol_window_days: int = 20
    crash_overlay_lookback_days: int = 756
    crash_overlay_quantile: float = 0.90
    crash_overlay_symbol: str = "SPY"
    crash_overlay_active: bool = False
    long_equity_sleeves: tuple[str, ...] = (
        "trend_following",
        "baseline_long",
        "vol_target",
    )


@dataclass(frozen=True)
class CandidateRuntimeWeights:
    raw_weights: dict[str, Decimal]
    target_weights: dict[str, Decimal]
    crash_overlay_active: bool


def build_target_weights(
    sleeve_signals: dict[str, pd.DataFrame],
    current_positions: dict[str, Decimal],
    account_equity: Decimal,
    config: PortfolioConstructionConfig,
) -> dict[str, Decimal]:
    if not sleeve_signals:
        return {}

    latest_rows = {
        sleeve_name: frame.fillna(0.0).astype(float).iloc[-1]
        for sleeve_name, frame in sleeve_signals.items()
        if not frame.empty
    }
    return _build_target_weights_from_rows(
        sleeve_rows=latest_rows,
        current_positions=current_positions,
        account_equity=account_equity,
        config=config,
    )


def build_target_weight_history(
    *,
    sleeve_signals: dict[str, pd.DataFrame],
    account_equity: Decimal,
    config: PortfolioConstructionConfig,
    benchmark_bars: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if not sleeve_signals:
        return pd.DataFrame(dtype=float)

    common_index = _common_index(sleeve_signals, benchmark_bars=benchmark_bars)
    aligned_sleeves = {
        sleeve_name: frame.reindex(common_index).fillna(0.0).astype(float)
        for sleeve_name, frame in sleeve_signals.items()
    }
    crash_overlay_mask = _crash_overlay_mask(
        benchmark_bars,
        config=config,
        reference_index=common_index,
    )
    current_positions: dict[str, Decimal] = {}
    rows: list[dict[str, float]] = []

    for timestamp in common_index:
        current_config = replace(
            config,
            crash_overlay_active=bool(crash_overlay_mask.loc[timestamp]),
        )
        weights = _build_target_weights_from_rows(
            sleeve_rows={
                sleeve_name: frame.loc[timestamp]
                for sleeve_name, frame in aligned_sleeves.items()
            },
            current_positions=current_positions,
            account_equity=account_equity,
            config=current_config,
        )
        current_positions = weights
        rows.append({symbol: float(weight) for symbol, weight in weights.items()})

    return pd.DataFrame(rows, index=common_index, dtype=float).fillna(0.0)


def build_candidate_target_weight_history(
    candidate: StrategyCandidate,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    account_equity: Decimal = Decimal("100000"),
    config: PortfolioConstructionConfig | None = None,
) -> pd.DataFrame:
    resolved_config = config or PortfolioConstructionConfig(
        crash_overlay_symbol=candidate.benchmark_symbol
    )
    sleeve_signals = _candidate_sleeve_signals(candidate, bars_by_symbol=bars_by_symbol)

    return build_target_weight_history(
        sleeve_signals=sleeve_signals,
        account_equity=account_equity,
        config=resolved_config,
        benchmark_bars=bars_by_symbol.get(candidate.benchmark_symbol),
    )


def build_candidate_runtime_weights(
    candidate: StrategyCandidate,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    current_positions: dict[str, Decimal],
    account_equity: Decimal = Decimal("100000"),
    config: PortfolioConstructionConfig | None = None,
) -> CandidateRuntimeWeights:
    resolved_config = config or PortfolioConstructionConfig(
        crash_overlay_symbol=candidate.benchmark_symbol
    )
    sleeve_signals = _candidate_sleeve_signals(candidate, bars_by_symbol=bars_by_symbol)
    benchmark_bars = bars_by_symbol.get(candidate.benchmark_symbol)
    common_index = _common_index(sleeve_signals, benchmark_bars=benchmark_bars)
    latest_timestamp = common_index[-1]
    crash_overlay_mask = _crash_overlay_mask(
        benchmark_bars,
        config=resolved_config,
        reference_index=common_index,
    )
    current_config = replace(
        resolved_config,
        crash_overlay_active=bool(crash_overlay_mask.loc[latest_timestamp]),
    )
    latest_rows = {
        sleeve_name: frame.reindex(common_index)
        .fillna(0.0)
        .astype(float)
        .loc[latest_timestamp]
        for sleeve_name, frame in sleeve_signals.items()
    }
    raw_weights = _build_raw_target_weights_from_rows(
        sleeve_rows=latest_rows,
        config=current_config,
    )
    target_weights = _apply_no_trade_band(
        target_weights=raw_weights,
        current_positions=current_positions,
        account_equity=account_equity,
        config=current_config,
    )
    return CandidateRuntimeWeights(
        raw_weights=raw_weights,
        target_weights=target_weights,
        crash_overlay_active=current_config.crash_overlay_active,
    )


def _build_target_weights_from_rows(
    *,
    sleeve_rows: dict[str, pd.Series],
    current_positions: dict[str, Decimal],
    account_equity: Decimal,
    config: PortfolioConstructionConfig,
) -> dict[str, Decimal]:
    raw_weights = _build_raw_target_weights_from_rows(
        sleeve_rows=sleeve_rows,
        config=config,
    )
    return _apply_no_trade_band(
        target_weights=raw_weights,
        current_positions=current_positions,
        account_equity=account_equity,
        config=config,
    )


def _build_raw_target_weights_from_rows(
    *,
    sleeve_rows: dict[str, pd.Series],
    config: PortfolioConstructionConfig,
) -> dict[str, Decimal]:
    active_sleeves = {
        sleeve_name: row.fillna(0.0).astype(float)
        for sleeve_name, row in sleeve_rows.items()
        if row.abs().fillna(0.0).sum() > 0.0
    }
    if not active_sleeves:
        tracked_symbols = sorted(
            symbol
            for row in sleeve_rows.values()
            for symbol in row.index
        )
        return {symbol: Decimal("0") for symbol in tracked_symbols}

    adjusted_rows = {}
    for sleeve_name, row in active_sleeves.items():
        adjusted_row = row.copy()
        if config.crash_overlay_active and sleeve_name in config.long_equity_sleeves:
            adjusted_row = adjusted_row * float(config.crash_overlay_factor)
        adjusted_rows[sleeve_name] = adjusted_row

    adjusted_frame = pd.DataFrame(adjusted_rows).T.fillna(0.0)
    combined = (adjusted_frame.sum(axis=0) / float(len(sleeve_rows))).fillna(0.0)
    combined = _cap_concentration(combined, config=config)
    combined = _limit_positions(combined, config=config)
    combined = _cap_gross_exposure(combined, config=config)

    combined_weights = {
        symbol: _to_decimal_weight(value)
        for symbol, value in combined.items()
    }
    return combined_weights


def _cap_concentration(
    weights: pd.Series,
    *,
    config: PortfolioConstructionConfig,
) -> pd.Series:
    return weights.clip(
        lower=-float(config.concentration_cap),
        upper=float(config.concentration_cap),
    )


def _limit_positions(
    weights: pd.Series,
    *,
    config: PortfolioConstructionConfig,
) -> pd.Series:
    if len(weights[weights != 0.0]) <= config.max_positions:
        return weights
    ranking = pd.DataFrame(
        {
            "abs_weight": weights.abs(),
            "symbol": weights.index.astype(str),
        },
        index=weights.index,
    )
    keep_symbols = set(
        ranking.sort_values(
            by=["abs_weight", "symbol"],
            ascending=[False, True],
            kind="stable",
        )
        .head(config.max_positions)
        .index
    )
    limited = weights.copy()
    for symbol in limited.index:
        if symbol not in keep_symbols:
            limited.loc[symbol] = 0.0
    return limited


def _cap_gross_exposure(
    weights: pd.Series,
    *,
    config: PortfolioConstructionConfig,
) -> pd.Series:
    gross_exposure = float(weights.abs().sum())
    if gross_exposure <= float(config.gross_exposure_cap) or gross_exposure == 0.0:
        return weights
    return weights * (float(config.gross_exposure_cap) / gross_exposure)


def _apply_no_trade_band(
    *,
    target_weights: dict[str, Decimal],
    current_positions: dict[str, Decimal],
    account_equity: Decimal,
    config: PortfolioConstructionConfig,
) -> dict[str, Decimal]:
    symbols = sorted(set(target_weights) | set(current_positions))
    minimum_trade_notional = max(
        config.min_trade_notional,
        account_equity * config.min_trade_fraction_of_equity,
    )
    held_weights: dict[str, Decimal] = {}
    for symbol in symbols:
        target_weight = target_weights.get(symbol, Decimal("0"))
        current_weight = current_positions.get(symbol, Decimal("0"))
        weight_delta = abs(target_weight - current_weight)
        trade_notional = weight_delta * account_equity
        if trade_notional < minimum_trade_notional:
            held_weights[symbol] = current_weight
        else:
            held_weights[symbol] = target_weight
    return held_weights


def _common_index(
    sleeve_signals: dict[str, pd.DataFrame],
    *,
    benchmark_bars: pd.DataFrame | None,
) -> pd.Index:
    common_index = None
    for frame in sleeve_signals.values():
        common_index = (
            frame.index
            if common_index is None
            else common_index.intersection(frame.index)
        )
    if benchmark_bars is not None:
        common_index = (
            benchmark_bars.index
            if common_index is None
            else common_index.intersection(benchmark_bars.index)
        )
    if common_index is None or common_index.empty:
        raise ValueError(
            "portfolio construction requires at least one shared timestamp."
        )
    return common_index


def _crash_overlay_mask(
    benchmark_bars: pd.DataFrame | None,
    *,
    config: PortfolioConstructionConfig,
    reference_index: pd.Index,
) -> pd.Series:
    mask = pd.Series(False, index=reference_index, dtype=bool)
    if benchmark_bars is None or "close" not in benchmark_bars:
        return mask

    benchmark_returns = benchmark_bars["close"].astype(float).pct_change()
    trailing_vol = realized_vol(
        benchmark_returns,
        lookback_days=config.crash_overlay_vol_window_days,
    )
    threshold = trailing_vol.shift(1).rolling(
        config.crash_overlay_lookback_days,
        min_periods=config.crash_overlay_lookback_days,
    ).quantile(config.crash_overlay_quantile)
    overlay_active = (trailing_vol > threshold).reindex(reference_index).fillna(False)
    return overlay_active.astype(bool)


def _candidate_sleeve_signals(
    candidate: StrategyCandidate,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    if candidate.family == "trend_following":
        return {
            candidate.family: _trend_sleeve_frame(
                candidate,
                bars_by_symbol=bars_by_symbol,
            )
        }
    if candidate.family == "vol_target":
        return {
            candidate.family: _vol_target_sleeve_frame(
                candidate,
                bars_by_symbol=bars_by_symbol,
            )
        }
    if candidate.family == "mean_reversion":
        return {
            candidate.family: _mean_reversion_sleeve_frame(
                candidate,
                bars_by_symbol=bars_by_symbol,
            )
        }
    raise ValueError(f"Unsupported candidate family: {candidate.family}")


def _trend_sleeve_frame(
    candidate: StrategyCandidate,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    sleeve_weights = {}
    for symbol in candidate.universe:
        bars = bars_by_symbol[symbol]
        signal = generate_trend_signal(
            bars,
            lookback_days=int(candidate.parameter_set["lookback_days"]),
            sma_window_days=int(candidate.parameter_set["sma_window_days"]),
            skip_recent_days=int(candidate.parameter_set.get("skip_recent_days", 1)),
        )
        sleeve_weights[symbol] = apply_position_sizing(
            bars,
            signal=signal,
            pre_sized=False,
            forecast_method=str(
                candidate.parameter_set.get("forecast_method", "realized")
            ),
        )
    reference_index = next(iter(sleeve_weights.values())).index
    return pd.DataFrame(sleeve_weights, index=reference_index, dtype=float)


def _vol_target_sleeve_frame(
    candidate: StrategyCandidate,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    benchmark_symbol = candidate.benchmark_symbol
    bars = bars_by_symbol[benchmark_symbol]
    signal = generate_vol_target_spy_signal(
        bars,
        target_volatility=float(candidate.parameter_set["target_volatility"]),
        realized_vol_window_days=int(candidate.parameter_set["realized_vol_window_days"]),
        max_gross_leverage=float(candidate.parameter_set["max_gross_leverage"]),
        forecast_method=str(candidate.parameter_set.get("forecast_method", "realized")),
    )
    return pd.DataFrame({benchmark_symbol: signal}, index=bars.index, dtype=float)


def _mean_reversion_sleeve_frame(
    candidate: StrategyCandidate,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    relevant_bars = {
        symbol: bars_by_symbol[symbol]
        for symbol in (candidate.benchmark_symbol, *candidate.universe)
    }
    signal_frame = generate_mean_revert_signal(
        _wide_ohlcv_frame(relevant_bars),
        benchmark_symbol=candidate.benchmark_symbol,
        tradable_symbols=candidate.universe,
        beta_window_days=int(candidate.parameter_set["beta_window_days"]),
        residual_sum_days=int(candidate.parameter_set["residual_sum_days"]),
        zscore_window_days=int(candidate.parameter_set["zscore_window_days"]),
        zscore_threshold=float(candidate.parameter_set["zscore_threshold"]),
    )
    sized_weights = {
        symbol: apply_position_sizing(
            bars_by_symbol[symbol],
            signal=signal_frame[symbol],
            pre_sized=False,
            forecast_method=str(
                candidate.parameter_set.get("forecast_method", "realized")
            ),
        )
        for symbol in candidate.universe
    }
    return pd.DataFrame(sized_weights, index=signal_frame.index, dtype=float)


def _wide_ohlcv_frame(
    bars_by_symbol: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    payload: dict[tuple[str, str], pd.Series] = {}
    reference_index = next(iter(bars_by_symbol.values())).index
    for symbol, bars in bars_by_symbol.items():
        for field in ("open", "high", "low", "close", "volume"):
            payload[(symbol, field)] = bars[field].astype(float).reindex(
                reference_index
            )
    return pd.DataFrame(payload, index=reference_index)


def _to_decimal_weight(value: float) -> Decimal:
    if value == 0.0:
        return Decimal("0")
    return Decimal(f"{float(value):.12f}").normalize()


__all__ = (
    "CandidateRuntimeWeights",
    "PortfolioConstructionConfig",
    "build_candidate_runtime_weights",
    "build_candidate_target_weight_history",
    "build_target_weight_history",
    "build_target_weights",
)
