# Tranche 1.3 Sleeves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute [DESIGN-0014](../specs/2026-04-21-tranche-1-3-sleeves-design.md) — turn the existing signal functions into full sleeves per BRIEF-0002's atomic-unit definition, with a `SleeveProtocol`, regime → exposure-floor gating, trend + vol-managed beta implementations, a target-weight-history bridge that reuses `run_daily_bar_backtest`, and a sleeve loader that makes `StrategyCandidate.parameter_set` the single source of truth.

**Architecture:** New `src/tradingx/sleeves/` package containing the protocol, shared types, regime gate, two concrete sleeves, an evaluation bridge, and a candidate-registry loader. **No new execution model** — sleeves produce target-weight DataFrames that `run_daily_bar_backtest` executes. Failure rules emit explicit `hold`/`sell` trades (never silent skips for in-universe symbols).

**Tech Stack:** Python 3.11, `Decimal` for money/weights at module boundaries, `pandas` for target-weight DataFrames and signal series, `pytest` for tests, existing `uv run` invocations.

---

## Scope

Implements DESIGN-0014 §W1–§W7 in this order:

1. **W1** — `SleeveContext`, `SleeveTrade`, `SleeveFailureReason`, `SleeveProtocol` (types before protocol).
2. **W2** — `apply_regime_exposure_floor` (shared helper for both sleeves).
3. **W3** — `TrendSleeve` (trend-following, long-only, vol-targeted).
4. **W4** — `VolManagedBetaSleeve` (Moreira-Muir, SPY only, intrinsic sizing).
5. **W5** — `build_sleeve_target_weight_history` + `simulate_sleeve_returns` (bridge to `run_daily_bar_backtest`).
6. **W6** — `StrategyCandidate.sleeve_class_path` + `build_sleeve_from_candidate` + `_candidate_returns` routing.
7. **W7** — Full regression + lint + typecheck + index + validate.

Gate 1 pass/fail outcomes must remain unchanged on existing fixtures (no sleeve candidate is in a legacy fixture today, so this is a "don't break the legacy path" constraint).

## File structure

### New files

- `src/tradingx/sleeves/__init__.py`
- `src/tradingx/sleeves/base.py` — `SleeveProtocol`, `SleeveFailureReason`, `build_sleeve_from_candidate`
- `src/tradingx/sleeves/regime_gate.py` — `apply_regime_exposure_floor`
- `src/tradingx/sleeves/trend.py` — `TrendSleeve`
- `src/tradingx/sleeves/vol_managed_beta.py` — `VolManagedBetaSleeve`
- `src/tradingx/sleeves/evaluation.py` — `build_sleeve_target_weight_history`, `simulate_sleeve_returns`
- `tests/unit/test_sleeve_base.py`
- `tests/unit/test_regime_gate.py`
- `tests/unit/test_trend_sleeve.py`
- `tests/unit/test_vol_managed_beta_sleeve.py`
- `tests/unit/test_sleeve_evaluation.py`
- `tests/unit/test_sleeve_loader.py`
- `tests/integration/test_sleeves_end_to_end.py`

### Modified files

- `src/tradingx/types.py` — add `SleeveContext`, `SleeveTrade`
- `src/tradingx/strategy.py` — add `sleeve_class_path` field; wire into registry
- `src/tradingx/validation.py` — route sleeve-path candidates through the new bridge in `_candidate_returns`
- `tests/unit/test_types.py` — assertions on new types
- `tests/unit/test_strategy.py` — registry now carries sleeve paths on trend + vol-target
- `tests/unit/test_validation.py` — routing regression

---

## W1 — Protocol + shared types

### Task 1: Add `SleeveTrade`, `SleeveContext`, `SleeveFailureReason`

**Files:**
- Modify: `src/tradingx/types.py`
- Modify: `tests/unit/test_types.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_types.py`:

```python
from datetime import UTC, date
from decimal import Decimal

import pandas as pd
import pytest

from tradingx.types import RegimeSnapshot, SleeveContext, SleeveTrade


def test_sleeve_trade_is_frozen_dataclass():
    import dataclasses
    trade = SleeveTrade(
        sleeve_id="trend-following-v1",
        symbol="SPY",
        side="buy",
        target_weight_of_sleeve_budget=Decimal("0.6"),
        rationale="tsmom_long_vol_targeted",
        regime="risk_on",
    )
    assert dataclasses.is_dataclass(trade)
    with pytest.raises(dataclasses.FrozenInstanceError):
        trade.side = "sell"  # type: ignore[misc]


def test_sleeve_context_is_frozen_dataclass():
    import dataclasses
    regime_snapshot = RegimeSnapshot(
        observation_date=date(2026, 4, 21),
        regime="risk_on",
        above_sma_200=True,
        vix_elevated=False,
        vix_stressed=False,
        yield_curve_inverted=False,
        spy_close=Decimal("500"),
        spy_sma_200=Decimal("480"),
        vix_close=Decimal("15"),
        yield_curve_spread_bps=Decimal("35"),
    )
    ctx = SleeveContext(
        observation_date=date(2026, 4, 21),
        bars_by_symbol={"SPY": pd.DataFrame()},
        regime=regime_snapshot,
        current_positions={"SPY": Decimal("10")},
        sleeve_budget_equity=Decimal("100000"),
    )
    assert dataclasses.is_dataclass(ctx)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.sleeve_budget_equity = Decimal("0")  # type: ignore[misc]


def test_sleeve_failure_reason_exposes_expected_constants():
    from tradingx.types import SleeveFailureReason
    assert SleeveFailureReason.HALT_BY_OPERATOR == "halt_by_operator"
    assert SleeveFailureReason.DRIFT_ALARM_LIVE == "drift_alarm_live"
    assert SleeveFailureReason.SLEEVE_SHARPE_BELOW_THRESHOLD_6M == (
        "sleeve_sharpe_below_threshold_6m"
    )
    assert SleeveFailureReason.REGIME_STRESSED == "regime_stressed"
    assert SleeveFailureReason.INSUFFICIENT_HISTORY == "insufficient_history"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_types.py -k "sleeve_trade or sleeve_context or sleeve_failure_reason" -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

Add to `src/tradingx/types.py`:

```python
from typing import Final


class SleeveFailureReason:
    """String constant set for sleeve failure diagnostics.

    Used in SleeveTrade.rationale when a failure rule suppresses
    or liquidates the sleeve's normal action for an in-universe
    symbol.
    """

    HALT_BY_OPERATOR: Final[str] = "halt_by_operator"
    DRIFT_ALARM_LIVE: Final[str] = "drift_alarm_live"
    SLEEVE_SHARPE_BELOW_THRESHOLD_6M: Final[str] = (
        "sleeve_sharpe_below_threshold_6m"
    )
    REGIME_STRESSED: Final[str] = "regime_stressed"
    INSUFFICIENT_HISTORY: Final[str] = "insufficient_history"


@dataclass(frozen=True)
class SleeveTrade:
    sleeve_id: str
    symbol: str
    side: str  # "buy" | "sell" | "reduce" | "hold"
    target_weight_of_sleeve_budget: Decimal
    rationale: str
    regime: str


@dataclass(frozen=True)
class SleeveContext:
    observation_date: date
    bars_by_symbol: dict[str, pd.DataFrame]
    regime: RegimeSnapshot
    current_positions: dict[str, Decimal]
    sleeve_budget_equity: Decimal
```

Add `import pandas as pd` to the imports if not present. Add all three to `__all__`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_types.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/types.py tests/unit/test_types.py
git commit -m "feat(types): add SleeveContext, SleeveTrade, SleeveFailureReason"
```

### Task 2: Add `SleeveProtocol` and package init

**Files:**
- Create: `src/tradingx/sleeves/__init__.py`
- Create: `src/tradingx/sleeves/base.py`
- Create: `tests/unit/test_sleeve_base.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_sleeve_base.py`:

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

import pandas as pd

from tradingx.sleeves.base import SleeveProtocol
from tradingx.types import RegimeSnapshot, SleeveContext, SleeveTrade


class _DummySleeve:
    sleeve_id = "dummy-v1"
    family = "dummy"
    allowed_instruments = ("SPY",)

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        return ()


def test_sleeve_protocol_is_structural():
    sleeve = _DummySleeve()
    # SleeveProtocol is declared as a Protocol; _DummySleeve does not
    # inherit from it but must still satisfy isinstance when the
    # protocol is runtime-checkable.
    assert isinstance(sleeve, SleeveProtocol)


def test_sleeve_protocol_rejects_objects_missing_plan_for_bar():
    class _Incomplete:
        sleeve_id = "x"
        family = "y"
        allowed_instruments = ()

    assert not isinstance(_Incomplete(), SleeveProtocol)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_sleeve_base.py -v`

Expected: FAIL on `ModuleNotFoundError: No module named 'tradingx.sleeves'`.

- [ ] **Step 3: Implement**

Create `src/tradingx/sleeves/__init__.py`:

```python
"""Sleeve abstraction package.

A sleeve is an atomic trading unit per BRIEF-0002: it owns signal,
sizing, regime filter, allowed instruments, and failure rules.
"""

from __future__ import annotations
```

Create `src/tradingx/sleeves/base.py`:

```python
"""Sleeve protocol and shared construction helpers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from tradingx.types import SleeveContext, SleeveTrade


@runtime_checkable
class SleeveProtocol(Protocol):
    """An atomic trading unit.

    Responsibilities per BRIEF-0002:
    - signal generation
    - sizing within the sleeve's budget
    - regime filter (see sleeves.regime_gate)
    - allowed_instruments declaration
    - failure-rule emission (SleeveTrade with failure rationale)
    """

    sleeve_id: str
    family: str
    allowed_instruments: tuple[str, ...]

    def plan_for_bar(
        self,
        context: SleeveContext,
    ) -> tuple[SleeveTrade, ...]: ...


__all__ = ("SleeveProtocol",)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_sleeve_base.py -v`

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/sleeves/ tests/unit/test_sleeve_base.py
git commit -m "feat(sleeves): add SleeveProtocol and package scaffold"
```

---

## W2 — Regime gate

### Task 3: `apply_regime_exposure_floor`

**Files:**
- Create: `src/tradingx/sleeves/regime_gate.py`
- Create: `tests/unit/test_regime_gate.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_regime_gate.py`:

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tradingx.sleeves.regime_gate import apply_regime_exposure_floor
from tradingx.types import RegimeSnapshot


def _regime(state: str) -> RegimeSnapshot:
    return RegimeSnapshot(
        observation_date=date(2026, 4, 21),
        regime=state,
        above_sma_200=None,
        vix_elevated=None,
        vix_stressed=None,
        yield_curve_inverted=None,
        spy_close=Decimal("500"),
        spy_sma_200=Decimal("480"),
        vix_close=None,
        yield_curve_spread_bps=None,
    )


@pytest.mark.parametrize("state", ["risk_on", "neutral"])
@pytest.mark.parametrize("family", ["trend_following", "vol_target"])
def test_regime_gate_passes_through_in_risk_on_and_neutral(state, family):
    adjusted, rationale = apply_regime_exposure_floor(
        sleeve_id="s-1",
        proposed_target_weight=Decimal("0.65"),
        current_position_weight=Decimal("0.40"),
        regime=_regime(state),
        sleeve_family=family,
    )
    assert adjusted == Decimal("0.65")
    assert rationale == ""


def test_regime_gate_suppresses_trend_entry_in_risk_off_when_no_position():
    adjusted, rationale = apply_regime_exposure_floor(
        sleeve_id="trend-following-v1",
        proposed_target_weight=Decimal("0.8"),
        current_position_weight=Decimal("0"),
        regime=_regime("risk_off"),
        sleeve_family="trend_following",
    )
    assert adjusted == Decimal("0")
    assert rationale == "regime_risk_off_suppress_entry"


def test_regime_gate_passes_through_trend_in_risk_off_when_holding():
    adjusted, rationale = apply_regime_exposure_floor(
        sleeve_id="trend-following-v1",
        proposed_target_weight=Decimal("0.5"),
        current_position_weight=Decimal("0.4"),
        regime=_regime("risk_off"),
        sleeve_family="trend_following",
    )
    assert adjusted == Decimal("0.5")
    assert rationale == ""


def test_regime_gate_passes_through_vol_target_in_risk_off():
    adjusted, rationale = apply_regime_exposure_floor(
        sleeve_id="vol-target-v1",
        proposed_target_weight=Decimal("0.7"),
        current_position_weight=Decimal("0"),
        regime=_regime("risk_off"),
        sleeve_family="vol_target",
    )
    assert adjusted == Decimal("0.7")
    assert rationale == ""


@pytest.mark.parametrize("family", ["trend_following", "vol_target"])
@pytest.mark.parametrize("current", ["0", "0.5"])
def test_regime_gate_zeros_both_families_in_stressed(family, current):
    adjusted, rationale = apply_regime_exposure_floor(
        sleeve_id="s-1",
        proposed_target_weight=Decimal("0.9"),
        current_position_weight=Decimal(current),
        regime=_regime("stressed"),
        sleeve_family=family,
    )
    assert adjusted == Decimal("0")
    assert rationale == "regime_stressed_liquidate"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_regime_gate.py -v`

Expected: FAIL on `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/tradingx/sleeves/regime_gate.py`:

```python
"""Regime → exposure-floor mapping shared by all sleeves.

The mapping table is authoritative; DESIGN-0014 §D4 codifies it.
No sleeve may reinterpret the four regime states.
"""

from __future__ import annotations

from decimal import Decimal

from tradingx.types import RegimeSnapshot


def apply_regime_exposure_floor(
    *,
    sleeve_id: str,
    proposed_target_weight: Decimal,
    current_position_weight: Decimal,
    regime: RegimeSnapshot,
    sleeve_family: str,
) -> tuple[Decimal, str]:
    """Apply the DESIGN-0014 regime mapping to a proposed weight.

    Returns (adjusted_target_weight, rationale_string). Empty
    rationale means pass-through; non-empty rationale names the
    failure-rule string.
    """
    del sleeve_id  # not needed for the mapping; reserved for logging
    state = regime.regime

    if state == "stressed":
        return Decimal("0"), "regime_stressed_liquidate"

    if state == "risk_off":
        if sleeve_family == "trend_following":
            if (
                current_position_weight == Decimal("0")
                and proposed_target_weight > Decimal("0")
            ):
                return Decimal("0"), "regime_risk_off_suppress_entry"
            return proposed_target_weight, ""
        # vol_target and any other family pass through in risk_off
        return proposed_target_weight, ""

    # risk_on and neutral: pass through
    return proposed_target_weight, ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_regime_gate.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/sleeves/regime_gate.py tests/unit/test_regime_gate.py
git commit -m "feat(sleeves): add apply_regime_exposure_floor per DESIGN-0014 §D4"
```

---

## W3 — TrendSleeve

### Task 4: `TrendSleeve` with signal + vol-targeted sizing

**Files:**
- Create: `src/tradingx/sleeves/trend.py`
- Create: `tests/unit/test_trend_sleeve.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_trend_sleeve.py`:

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from tradingx.sleeves.trend import TrendSleeve
from tradingx.types import RegimeSnapshot, SleeveContext


def _build_uptrend_bars(n: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(seed=11)
    noise = rng.normal(scale=0.01, size=n)
    drift = 0.0008  # ~20% annualized drift
    returns = noise + drift
    closes = 100.0 * np.cumprod(1.0 + returns)
    dates = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "volume": [1e7] * n,
        },
        index=dates,
    )


def _risk_on_regime(observation_date: date) -> RegimeSnapshot:
    return RegimeSnapshot(
        observation_date=observation_date,
        regime="risk_on",
        above_sma_200=True,
        vix_elevated=False,
        vix_stressed=False,
        yield_curve_inverted=False,
        spy_close=Decimal("500"),
        spy_sma_200=Decimal("480"),
        vix_close=Decimal("15"),
        yield_curve_spread_bps=Decimal("35"),
    )


def test_trend_sleeve_emits_long_on_uptrend_in_risk_on():
    bars = _build_uptrend_bars()
    sleeve = TrendSleeve(allowed_instruments=("SPY",))
    ctx = SleeveContext(
        observation_date=bars.index[-1].date(),
        bars_by_symbol={"SPY": bars},
        regime=_risk_on_regime(bars.index[-1].date()),
        current_positions={"SPY": Decimal("0")},
        sleeve_budget_equity=Decimal("100000"),
    )
    trades = sleeve.plan_for_bar(ctx)
    spy_trade = next(t for t in trades if t.symbol == "SPY")
    assert spy_trade.side == "buy"
    assert spy_trade.target_weight_of_sleeve_budget > Decimal("0")
    assert spy_trade.rationale in {
        "tsmom_long_vol_targeted",
        "tsmom_long_regime_suppressed",
        "tsmom_no_signal",
    }


def test_trend_sleeve_emits_hold_with_insufficient_history_rationale_on_short_bars():
    bars = _build_uptrend_bars(n=50)  # < 252 lookback
    sleeve = TrendSleeve(allowed_instruments=("SPY",))
    ctx = SleeveContext(
        observation_date=bars.index[-1].date(),
        bars_by_symbol={"SPY": bars},
        regime=_risk_on_regime(bars.index[-1].date()),
        current_positions={"SPY": Decimal("0")},
        sleeve_budget_equity=Decimal("100000"),
    )
    trades = sleeve.plan_for_bar(ctx)
    spy_trade = next(t for t in trades if t.symbol == "SPY")
    assert spy_trade.side == "hold"
    assert spy_trade.rationale == "insufficient_history"
    assert spy_trade.target_weight_of_sleeve_budget == Decimal("0")


def test_trend_sleeve_liquidates_in_stressed_regime():
    bars = _build_uptrend_bars()
    sleeve = TrendSleeve(allowed_instruments=("SPY",))
    stressed_regime = RegimeSnapshot(
        observation_date=bars.index[-1].date(),
        regime="stressed",
        above_sma_200=False,
        vix_elevated=True,
        vix_stressed=True,
        yield_curve_inverted=True,
        spy_close=Decimal("400"),
        spy_sma_200=Decimal("500"),
        vix_close=Decimal("45"),
        yield_curve_spread_bps=Decimal("-25"),
    )
    ctx = SleeveContext(
        observation_date=bars.index[-1].date(),
        bars_by_symbol={"SPY": bars},
        regime=stressed_regime,
        current_positions={"SPY": Decimal("100")},  # holding
        sleeve_budget_equity=Decimal("100000"),
    )
    trades = sleeve.plan_for_bar(ctx)
    spy_trade = next(t for t in trades if t.symbol == "SPY")
    assert spy_trade.side == "sell"
    assert spy_trade.target_weight_of_sleeve_budget == Decimal("0")
    assert spy_trade.rationale == "regime_stressed_liquidate"


def test_trend_sleeve_suppresses_new_entry_in_risk_off():
    bars = _build_uptrend_bars()
    sleeve = TrendSleeve(allowed_instruments=("SPY",))
    risk_off = RegimeSnapshot(
        observation_date=bars.index[-1].date(),
        regime="risk_off",
        above_sma_200=False,
        vix_elevated=False,
        vix_stressed=False,
        yield_curve_inverted=False,
        spy_close=Decimal("470"),
        spy_sma_200=Decimal("490"),
        vix_close=Decimal("18"),
        yield_curve_spread_bps=Decimal("20"),
    )
    ctx = SleeveContext(
        observation_date=bars.index[-1].date(),
        bars_by_symbol={"SPY": bars},
        regime=risk_off,
        current_positions={"SPY": Decimal("0")},  # not holding
        sleeve_budget_equity=Decimal("100000"),
    )
    trades = sleeve.plan_for_bar(ctx)
    spy_trade = next(t for t in trades if t.symbol == "SPY")
    assert spy_trade.target_weight_of_sleeve_budget == Decimal("0")
    assert spy_trade.rationale == "regime_risk_off_suppress_entry"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_trend_sleeve.py -v`

Expected: FAIL on `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/tradingx/sleeves/trend.py`:

```python
"""TrendSleeve — time-series momentum with vol-targeted sizing."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from tradingx.features.volatility import forecast_volatility
from tradingx.signals.trend import generate_trend_signal
from tradingx.sleeves.regime_gate import apply_regime_exposure_floor
from tradingx.strategy import CANONICAL_STAGE1_UNIVERSE
from tradingx.types import SleeveContext, SleeveTrade


@dataclass(frozen=True)
class TrendSleeve:
    sleeve_id: str = "trend-following-v1"
    family: str = "trend_following"
    target_sleeve_vol: Decimal = Decimal("0.12")
    lookback_days: int = 252
    sma_window_days: int = 200
    skip_recent_days: int = 1
    vol_forecast_lookback: int = 20
    forecast_method: str = "ewma"
    allowed_instruments: tuple[str, ...] = CANONICAL_STAGE1_UNIVERSE

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        trades: list[SleeveTrade] = []
        for symbol in self.allowed_instruments:
            bars = context.bars_by_symbol.get(symbol)
            if bars is None or len(bars) < self.lookback_days:
                current_qty = context.current_positions.get(
                    symbol, Decimal("0")
                )
                current_weight = _compute_current_weight(
                    current_qty=current_qty,
                    bars=bars,
                    sleeve_budget_equity=context.sleeve_budget_equity,
                )
                trades.append(
                    SleeveTrade(
                        sleeve_id=self.sleeve_id,
                        symbol=symbol,
                        side="hold",
                        target_weight_of_sleeve_budget=current_weight,
                        rationale="insufficient_history",
                        regime=context.regime.regime,
                    )
                )
                continue

            signal_series = generate_trend_signal(
                bars,
                lookback_days=self.lookback_days,
                sma_window_days=self.sma_window_days,
                skip_recent_days=self.skip_recent_days,
            )
            signal_value = float(signal_series.iloc[-1])

            returns = bars["close"].astype(float).pct_change()
            vol_forecast_series = forecast_volatility(
                returns,
                lookback_days=self.vol_forecast_lookback,
                forecast_method=self.forecast_method,
            )
            vol_forecast = float(vol_forecast_series.iloc[-1])
            if pd.isna(vol_forecast) or vol_forecast <= 0:
                current_qty = context.current_positions.get(
                    symbol, Decimal("0")
                )
                current_weight = _compute_current_weight(
                    current_qty=current_qty,
                    bars=bars,
                    sleeve_budget_equity=context.sleeve_budget_equity,
                )
                trades.append(
                    SleeveTrade(
                        sleeve_id=self.sleeve_id,
                        symbol=symbol,
                        side="hold",
                        target_weight_of_sleeve_budget=current_weight,
                        rationale="insufficient_history",
                        regime=context.regime.regime,
                    )
                )
                continue

            raw_weight = Decimal("0")
            if signal_value > 0:
                leverage = float(self.target_sleeve_vol) / vol_forecast
                raw_weight = Decimal(str(min(leverage, 1.0)))

            current_qty = context.current_positions.get(symbol, Decimal("0"))
            current_weight = _compute_current_weight(
                current_qty=current_qty,
                bars=bars,
                sleeve_budget_equity=context.sleeve_budget_equity,
            )

            adjusted_weight, regime_rationale = apply_regime_exposure_floor(
                sleeve_id=self.sleeve_id,
                proposed_target_weight=raw_weight,
                current_position_weight=current_weight,
                regime=context.regime,
                sleeve_family=self.family,
            )

            side = _derive_side(current_weight, adjusted_weight)
            rationale = regime_rationale or _signal_rationale(
                signal_value, adjusted_weight
            )
            trades.append(
                SleeveTrade(
                    sleeve_id=self.sleeve_id,
                    symbol=symbol,
                    side=side,
                    target_weight_of_sleeve_budget=adjusted_weight,
                    rationale=rationale,
                    regime=context.regime.regime,
                )
            )
        return tuple(trades)


def _compute_current_weight(
    *,
    current_qty: Decimal,
    bars: pd.DataFrame | None,
    sleeve_budget_equity: Decimal,
) -> Decimal:
    if (
        current_qty == Decimal("0")
        or bars is None
        or len(bars) == 0
        or sleeve_budget_equity <= Decimal("0")
    ):
        return Decimal("0")
    last_close = Decimal(str(bars["close"].iloc[-1]))
    return (current_qty * last_close) / sleeve_budget_equity


def _derive_side(current: Decimal, target: Decimal) -> str:
    if target > current:
        return "buy"
    if target < current and target == Decimal("0"):
        return "sell"
    if target < current:
        return "reduce"
    return "hold"


def _signal_rationale(signal_value: float, adjusted_weight: Decimal) -> str:
    if signal_value > 0 and adjusted_weight > Decimal("0"):
        return "tsmom_long_vol_targeted"
    if signal_value <= 0:
        return "tsmom_no_signal"
    return "tsmom_long_regime_suppressed"


__all__ = ("TrendSleeve",)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_trend_sleeve.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/sleeves/trend.py tests/unit/test_trend_sleeve.py
git commit -m "feat(sleeves): add TrendSleeve with vol-targeted sizing and regime gating"
```

---

## W4 — VolManagedBetaSleeve

### Task 5: `VolManagedBetaSleeve` with Moreira-Muir intrinsic sizing

**Files:**
- Create: `src/tradingx/sleeves/vol_managed_beta.py`
- Create: `tests/unit/test_vol_managed_beta_sleeve.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_vol_managed_beta_sleeve.py`:

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from tradingx.sleeves.vol_managed_beta import VolManagedBetaSleeve
from tradingx.types import RegimeSnapshot, SleeveContext


def _bars(n: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(seed=13)
    returns = rng.normal(scale=0.01, size=n)
    closes = 100.0 * np.cumprod(1.0 + returns)
    dates = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "volume": [1e7] * n,
        },
        index=dates,
    )


def _regime(state: str, observation_date: date) -> RegimeSnapshot:
    return RegimeSnapshot(
        observation_date=observation_date,
        regime=state,
        above_sma_200=(state in {"risk_on", "neutral"}),
        vix_elevated=(state in {"risk_off", "stressed"}),
        vix_stressed=(state == "stressed"),
        yield_curve_inverted=False,
        spy_close=Decimal("500"),
        spy_sma_200=Decimal("480"),
        vix_close=Decimal("15"),
        yield_curve_spread_bps=Decimal("35"),
    )


def test_vol_managed_beta_only_emits_for_spy():
    bars = _bars()
    sleeve = VolManagedBetaSleeve()
    ctx = SleeveContext(
        observation_date=bars.index[-1].date(),
        bars_by_symbol={"SPY": bars, "QQQ": bars},
        regime=_regime("risk_on", bars.index[-1].date()),
        current_positions={"SPY": Decimal("0"), "QQQ": Decimal("0")},
        sleeve_budget_equity=Decimal("100000"),
    )
    trades = sleeve.plan_for_bar(ctx)
    assert len(trades) == 1
    assert trades[0].symbol == "SPY"


def test_vol_managed_beta_emits_non_zero_weight_in_calm_regime():
    bars = _bars()
    sleeve = VolManagedBetaSleeve()
    ctx = SleeveContext(
        observation_date=bars.index[-1].date(),
        bars_by_symbol={"SPY": bars},
        regime=_regime("risk_on", bars.index[-1].date()),
        current_positions={"SPY": Decimal("0")},
        sleeve_budget_equity=Decimal("100000"),
    )
    trades = sleeve.plan_for_bar(ctx)
    assert trades[0].target_weight_of_sleeve_budget > Decimal("0")


def test_vol_managed_beta_emits_hold_with_insufficient_history():
    bars = _bars(n=30)
    sleeve = VolManagedBetaSleeve()
    ctx = SleeveContext(
        observation_date=bars.index[-1].date(),
        bars_by_symbol={"SPY": bars},
        regime=_regime("risk_on", bars.index[-1].date()),
        current_positions={"SPY": Decimal("0")},
        sleeve_budget_equity=Decimal("100000"),
    )
    trades = sleeve.plan_for_bar(ctx)
    assert len(trades) == 1
    assert trades[0].side == "hold"
    assert trades[0].rationale == "insufficient_history"


def test_vol_managed_beta_liquidates_in_stressed():
    bars = _bars()
    sleeve = VolManagedBetaSleeve()
    ctx = SleeveContext(
        observation_date=bars.index[-1].date(),
        bars_by_symbol={"SPY": bars},
        regime=_regime("stressed", bars.index[-1].date()),
        current_positions={"SPY": Decimal("100")},
        sleeve_budget_equity=Decimal("100000"),
    )
    trades = sleeve.plan_for_bar(ctx)
    assert trades[0].side == "sell"
    assert trades[0].target_weight_of_sleeve_budget == Decimal("0")
    assert trades[0].rationale == "regime_stressed_liquidate"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_vol_managed_beta_sleeve.py -v`

Expected: FAIL on `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/tradingx/sleeves/vol_managed_beta.py`:

```python
"""VolManagedBetaSleeve — Moreira-Muir vol-managed SPY exposure."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from tradingx.signals.vol_target_spy import generate_vol_target_spy_signal
from tradingx.sleeves.regime_gate import apply_regime_exposure_floor
from tradingx.sleeves.trend import (  # reuse helpers
    _compute_current_weight,
    _derive_side,
)
from tradingx.types import SleeveContext, SleeveTrade


@dataclass(frozen=True)
class VolManagedBetaSleeve:
    sleeve_id: str = "vol-target-v1"
    family: str = "vol_target"
    target_volatility: float = 0.12
    realized_vol_window_days: int = 60
    max_gross_leverage: float = 1.0
    forecast_method: str = "garch"
    allowed_instruments: tuple[str, ...] = ("SPY",)

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        spy_bars = context.bars_by_symbol.get("SPY")
        min_required = self.realized_vol_window_days + 20

        if spy_bars is None or len(spy_bars) < min_required:
            current_qty = context.current_positions.get("SPY", Decimal("0"))
            current_weight = _compute_current_weight(
                current_qty=current_qty,
                bars=spy_bars,
                sleeve_budget_equity=context.sleeve_budget_equity,
            )
            return (
                SleeveTrade(
                    sleeve_id=self.sleeve_id,
                    symbol="SPY",
                    side="hold",
                    target_weight_of_sleeve_budget=current_weight,
                    rationale="insufficient_history",
                    regime=context.regime.regime,
                ),
            )

        signal_series = generate_vol_target_spy_signal(
            spy_bars,
            target_volatility=self.target_volatility,
            realized_vol_window_days=self.realized_vol_window_days,
            max_gross_leverage=self.max_gross_leverage,
            forecast_method=self.forecast_method,
        )
        raw_scalar = signal_series.iloc[-1]
        if pd.isna(raw_scalar):
            current_qty = context.current_positions.get("SPY", Decimal("0"))
            current_weight = _compute_current_weight(
                current_qty=current_qty,
                bars=spy_bars,
                sleeve_budget_equity=context.sleeve_budget_equity,
            )
            return (
                SleeveTrade(
                    sleeve_id=self.sleeve_id,
                    symbol="SPY",
                    side="hold",
                    target_weight_of_sleeve_budget=current_weight,
                    rationale="insufficient_history",
                    regime=context.regime.regime,
                ),
            )

        raw_weight = Decimal(str(float(raw_scalar)))

        current_qty = context.current_positions.get("SPY", Decimal("0"))
        current_weight = _compute_current_weight(
            current_qty=current_qty,
            bars=spy_bars,
            sleeve_budget_equity=context.sleeve_budget_equity,
        )

        adjusted_weight, regime_rationale = apply_regime_exposure_floor(
            sleeve_id=self.sleeve_id,
            proposed_target_weight=raw_weight,
            current_position_weight=current_weight,
            regime=context.regime,
            sleeve_family=self.family,
        )

        side = _derive_side(current_weight, adjusted_weight)
        rationale = regime_rationale or "moreira_muir_vol_managed"
        return (
            SleeveTrade(
                sleeve_id=self.sleeve_id,
                symbol="SPY",
                side=side,
                target_weight_of_sleeve_budget=adjusted_weight,
                rationale=rationale,
                regime=context.regime.regime,
            ),
        )


__all__ = ("VolManagedBetaSleeve",)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_vol_managed_beta_sleeve.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/sleeves/vol_managed_beta.py tests/unit/test_vol_managed_beta_sleeve.py
git commit -m "feat(sleeves): add VolManagedBetaSleeve for SPY with regime gating"
```

---

## W5 — Evaluation bridge

### Task 6: `build_sleeve_target_weight_history` (pure translation)

**Files:**
- Create: `src/tradingx/sleeves/evaluation.py`
- Create: `tests/unit/test_sleeve_evaluation.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_sleeve_evaluation.py`:

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from tradingx.sleeves.evaluation import build_sleeve_target_weight_history
from tradingx.sleeves.trend import TrendSleeve
from tradingx.types import RegimeSnapshot


def _bars(n: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(seed=17)
    returns = rng.normal(scale=0.01, size=n)
    closes = 100.0 * np.cumprod(1.0 + returns)
    dates = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "volume": [1e7] * n,
        },
        index=dates,
    )


def _risk_on(observation_date: date) -> RegimeSnapshot:
    return RegimeSnapshot(
        observation_date=observation_date,
        regime="risk_on",
        above_sma_200=True,
        vix_elevated=False,
        vix_stressed=False,
        yield_curve_inverted=False,
        spy_close=Decimal("500"),
        spy_sma_200=Decimal("480"),
        vix_close=Decimal("15"),
        yield_curve_spread_bps=Decimal("35"),
    )


def test_build_sleeve_target_weight_history_is_pure_dataframe():
    bars = _bars()
    sleeve = TrendSleeve(allowed_instruments=("SPY",))
    regimes = {d.date(): _risk_on(d.date()) for d in bars.index}
    df = build_sleeve_target_weight_history(
        sleeve,
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=regimes,
        sleeve_budget_equity=Decimal("100000"),
    )
    assert isinstance(df, pd.DataFrame)
    assert "SPY" in df.columns
    # weights are in [0, 1]
    assert (df["SPY"].dropna() >= 0.0).all()
    assert (df["SPY"].dropna() <= 1.0).all()


def test_build_sleeve_target_weight_history_deterministic():
    bars = _bars()
    sleeve = TrendSleeve(allowed_instruments=("SPY",))
    regimes = {d.date(): _risk_on(d.date()) for d in bars.index}
    a = build_sleeve_target_weight_history(
        sleeve,
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=regimes,
        sleeve_budget_equity=Decimal("100000"),
    )
    b = build_sleeve_target_weight_history(
        sleeve,
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=regimes,
        sleeve_budget_equity=Decimal("100000"),
    )
    pd.testing.assert_frame_equal(a, b)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_sleeve_evaluation.py -k build_sleeve_target -v`

Expected: FAIL on `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/tradingx/sleeves/evaluation.py`:

```python
"""Sleeve-to-evaluation bridge.

Translates sleeve plan_for_bar outputs into a target-weight
DataFrame, then hands the DataFrame to run_daily_bar_backtest to
execute. This preserves the single-source execution model — no
sleeve-specific execution logic.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from tradingx.backtest import run_daily_bar_backtest
from tradingx.costs import CostModelConfig
from tradingx.sleeves.base import SleeveProtocol
from tradingx.types import RegimeSnapshot, SleeveContext


def build_sleeve_target_weight_history(
    sleeve: SleeveProtocol,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    regime_snapshots_by_date: dict[date, RegimeSnapshot],
    sleeve_budget_equity: Decimal,
) -> pd.DataFrame:
    """Walk the sleeve bar-by-bar; collect target weights per symbol.

    Returns DataFrame indexed by the observation dates for which the
    sleeve produced at least one trade, with columns = union of
    symbols the sleeve ever touched. Cells are floats in [0, 1]
    representing target_weight_of_sleeve_budget.
    """
    index_symbol = next(iter(bars_by_symbol))
    observation_dates = [ts.date() for ts in bars_by_symbol[index_symbol].index]

    rows: dict[date, dict[str, float]] = {}
    touched_symbols: set[str] = set()

    current_positions: dict[str, Decimal] = {
        symbol: Decimal("0") for symbol in bars_by_symbol
    }

    for position, obs_date in enumerate(observation_dates):
        regime = regime_snapshots_by_date.get(obs_date)
        if regime is None:
            continue
        # Slice bars up to and including obs_date
        sliced = {
            symbol: bars.iloc[: position + 1]
            for symbol, bars in bars_by_symbol.items()
        }
        context = SleeveContext(
            observation_date=obs_date,
            bars_by_symbol=sliced,
            regime=regime,
            current_positions=dict(current_positions),
            sleeve_budget_equity=sleeve_budget_equity,
        )
        trades = sleeve.plan_for_bar(context)
        if not trades:
            continue
        row = rows.setdefault(obs_date, {})
        for trade in trades:
            touched_symbols.add(trade.symbol)
            row[trade.symbol] = float(trade.target_weight_of_sleeve_budget)
            # Track simulated current_positions by proxy:
            # one-day-lag — at next bar, "current" is what we just
            # emitted here.
            current_positions[trade.symbol] = (
                trade.target_weight_of_sleeve_budget
                * sleeve_budget_equity
                / Decimal(str(bars_by_symbol[trade.symbol]["close"].iloc[position]))
                if bars_by_symbol[trade.symbol]["close"].iloc[position] > 0
                else Decimal("0")
            )

    if not rows:
        return pd.DataFrame(columns=sorted(touched_symbols))

    sorted_dates = sorted(rows.keys())
    sorted_symbols = sorted(touched_symbols)
    data = {
        symbol: [rows[d].get(symbol, 0.0) for d in sorted_dates]
        for symbol in sorted_symbols
    }
    frame = pd.DataFrame(
        data,
        index=pd.DatetimeIndex(
            [pd.Timestamp(d, tz="UTC") for d in sorted_dates]
        ),
    )
    return frame


__all__ = ("build_sleeve_target_weight_history",)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_sleeve_evaluation.py -v`

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/sleeves/evaluation.py tests/unit/test_sleeve_evaluation.py
git commit -m "feat(sleeves): add build_sleeve_target_weight_history pure translator"
```

### Task 7: `simulate_sleeve_returns` (thin wrapper over `run_daily_bar_backtest`)

**Files:**
- Modify: `src/tradingx/sleeves/evaluation.py`
- Modify: `tests/unit/test_sleeve_evaluation.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_sleeve_evaluation.py`:

```python
from tradingx.backtest import run_daily_bar_backtest
from tradingx.sleeves.evaluation import simulate_sleeve_returns


def test_simulate_sleeve_returns_matches_direct_backtest_on_same_weights():
    bars = _bars()
    sleeve = TrendSleeve(allowed_instruments=("SPY",))
    regimes = {d.date(): _risk_on(d.date()) for d in bars.index}
    sleeve_returns, sleeve_drag = simulate_sleeve_returns(
        sleeve,
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=regimes,
        sleeve_budget_equity=Decimal("100000"),
    )
    # Must match the 2-tuple shape of _candidate_returns()
    assert isinstance(sleeve_returns, tuple)
    assert isinstance(sleeve_drag, Decimal)

    # Re-run run_daily_bar_backtest on the same weight history;
    # costs and returns must match exactly.
    target_weights = build_sleeve_target_weight_history(
        sleeve,
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=regimes,
        sleeve_budget_equity=Decimal("100000"),
    )
    direct_result = run_daily_bar_backtest(
        {"SPY": bars},
        target_weights=target_weights,
        cost_model_config=None,  # default
    )
    direct_returns = tuple(
        Decimal(str(v)) for v in direct_result.portfolio_returns.tolist()
    )
    assert sleeve_returns == direct_returns
    assert sleeve_drag == direct_result.annualized_cost_drag_bps
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sleeve_evaluation.py -k simulate_sleeve_returns_matches -v`

Expected: FAIL — `simulate_sleeve_returns` not defined.

- [ ] **Step 3: Implement**

Append to `src/tradingx/sleeves/evaluation.py`:

```python
def simulate_sleeve_returns(
    sleeve: SleeveProtocol,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    regime_snapshots_by_date: dict[date, RegimeSnapshot],
    sleeve_budget_equity: Decimal,
    cost_model_config: CostModelConfig | None = None,
) -> tuple[tuple[Decimal, ...], Decimal]:
    """Build target weights, run them through run_daily_bar_backtest,
    return the (returns, annualized_cost_drag_bps) tuple that matches
    _candidate_returns().
    """
    target_weights = build_sleeve_target_weight_history(
        sleeve,
        bars_by_symbol=bars_by_symbol,
        regime_snapshots_by_date=regime_snapshots_by_date,
        sleeve_budget_equity=sleeve_budget_equity,
    )
    traded_symbols = tuple(str(symbol) for symbol in target_weights.columns)
    resolved_cost_config = cost_model_config or CostModelConfig()
    result = run_daily_bar_backtest(
        {symbol: bars_by_symbol[symbol] for symbol in traded_symbols},
        target_weights=target_weights,
        cost_model_config=resolved_cost_config,
    )
    returns = tuple(
        Decimal(str(value)) for value in result.portfolio_returns.tolist()
    )
    return returns, result.annualized_cost_drag_bps


__all__ = (
    "build_sleeve_target_weight_history",
    "simulate_sleeve_returns",
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_sleeve_evaluation.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/sleeves/evaluation.py tests/unit/test_sleeve_evaluation.py
git commit -m "feat(sleeves): add simulate_sleeve_returns thin wrapper over run_daily_bar_backtest"
```

---

## W6 — Strategy registry + loader + routing

### Task 8: `StrategyCandidate.sleeve_class_path` field

**Files:**
- Modify: `src/tradingx/strategy.py`
- Modify: `tests/unit/test_strategy.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_strategy.py`:

```python
def test_strategy_candidate_accepts_sleeve_class_path():
    candidate = StrategyCandidate(
        candidate_id="x-v1",
        family="x",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={"forecast_method": "ewma"},
        status="under_evaluation",
        sleeve_class_path="tradingx.sleeves.trend.TrendSleeve",
    )
    assert candidate.sleeve_class_path == "tradingx.sleeves.trend.TrendSleeve"


def test_strategy_candidate_sleeve_class_path_defaults_to_none():
    candidate = StrategyCandidate(
        candidate_id="x-v1",
        family="x",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={},
        status="under_evaluation",
    )
    assert candidate.sleeve_class_path is None


def test_registry_sets_sleeve_class_path_for_trend_and_vol_target():
    candidates = build_mandatory_candidate_registry(("SPY", "QQQ"))
    by_id = {c.candidate_id: c for c in candidates}
    assert by_id["trend-following-v1"].sleeve_class_path == (
        "tradingx.sleeves.trend.TrendSleeve"
    )
    assert by_id["vol-target-v1"].sleeve_class_path == (
        "tradingx.sleeves.vol_managed_beta.VolManagedBetaSleeve"
    )
    # Mean-reversion deferred per FFL-0001-03
    assert by_id["mean-reversion-v1"].sleeve_class_path is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_strategy.py -k "sleeve_class_path or registry_sets_sleeve" -v`

Expected: FAIL on `TypeError` or on missing field.

- [ ] **Step 3: Implement**

In `src/tradingx/types.py` (where `StrategyCandidate` is defined — confirm via `grep -n "class StrategyCandidate" src/tradingx/types.py`), add the field with a default:

```python
@dataclass(frozen=True)
class StrategyCandidate:
    # ...existing fields unchanged...
    sleeve_class_path: str | None = None
```

In `src/tradingx/strategy.py`, update `build_mandatory_candidate_registry`:

```python
# In the trend-following-v1 StrategyCandidate(...):
sleeve_class_path="tradingx.sleeves.trend.TrendSleeve",

# In the vol-target-v1 StrategyCandidate(...):
sleeve_class_path="tradingx.sleeves.vol_managed_beta.VolManagedBetaSleeve",

# mean-reversion-v1 leaves the field default (None).
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_strategy.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/types.py src/tradingx/strategy.py tests/unit/test_strategy.py
git commit -m "feat(strategy): add sleeve_class_path to registry for trend and vol-target"
```

### Task 9: `build_sleeve_from_candidate` loader

**Files:**
- Modify: `src/tradingx/sleeves/base.py`
- Create: `tests/unit/test_sleeve_loader.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_sleeve_loader.py`:

```python
from __future__ import annotations

from decimal import Decimal

import pytest

from tradingx.sleeves.base import build_sleeve_from_candidate
from tradingx.sleeves.trend import TrendSleeve
from tradingx.types import StrategyCandidate


def _trend_candidate() -> StrategyCandidate:
    return StrategyCandidate(
        candidate_id="trend-test-v1",
        family="trend_following",
        benchmark_symbol="SPY",
        universe=("SPY", "QQQ"),
        parameter_set={
            "lookback_days": 100,
            "sma_window_days": 50,
            "signal": "long_only",  # extra key that should be dropped
            "forecast_method": "ewma",
        },
        status="under_evaluation",
        sleeve_class_path="tradingx.sleeves.trend.TrendSleeve",
    )


def test_build_sleeve_from_candidate_imports_class():
    sleeve = build_sleeve_from_candidate(_trend_candidate())
    assert isinstance(sleeve, TrendSleeve)


def test_build_sleeve_from_candidate_overrides_defaults_from_parameter_set():
    sleeve = build_sleeve_from_candidate(_trend_candidate())
    assert sleeve.lookback_days == 100
    assert sleeve.sma_window_days == 50
    assert sleeve.forecast_method == "ewma"


def test_build_sleeve_from_candidate_uses_candidate_universe():
    sleeve = build_sleeve_from_candidate(_trend_candidate())
    assert sleeve.allowed_instruments == ("SPY", "QQQ")


def test_build_sleeve_from_candidate_uses_candidate_id():
    sleeve = build_sleeve_from_candidate(_trend_candidate())
    assert sleeve.sleeve_id == "trend-test-v1"


def test_build_sleeve_from_candidate_silently_drops_unknown_keys():
    # "signal" is not a TrendSleeve dataclass field. Loader must
    # silently drop it; constructor must succeed.
    sleeve = build_sleeve_from_candidate(_trend_candidate())
    assert sleeve is not None  # no TypeError raised


def test_build_sleeve_from_candidate_raises_on_null_path():
    candidate = StrategyCandidate(
        candidate_id="mean-reversion-v1",
        family="mean_reversion",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={},
        status="under_evaluation",
        sleeve_class_path=None,
    )
    with pytest.raises(ValueError, match="sleeve_class_path"):
        build_sleeve_from_candidate(candidate)


def test_build_sleeve_from_candidate_raises_on_bad_import():
    candidate = StrategyCandidate(
        candidate_id="x",
        family="x",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={},
        status="under_evaluation",
        sleeve_class_path="tradingx.sleeves.nonexistent.Nothing",
    )
    with pytest.raises((ValueError, ImportError, AttributeError)):
        build_sleeve_from_candidate(candidate)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_sleeve_loader.py -v`

Expected: FAIL on `ImportError`.

- [ ] **Step 3: Implement**

Append to `src/tradingx/sleeves/base.py`:

```python
import dataclasses
import importlib

from tradingx.types import StrategyCandidate


def build_sleeve_from_candidate(candidate: StrategyCandidate) -> SleeveProtocol:
    """Instantiate a sleeve from a candidate per DESIGN-0014 W6 rules.

    Rules:
    - allowed_instruments <- candidate.universe (always)
    - sleeve_id <- candidate.candidate_id (always)
    - parameter_set keys matching dataclass field names override
      defaults
    - parameter_set keys NOT matching dataclass field names are
      silently DROPPED (never passed to the constructor)
    """
    if candidate.sleeve_class_path is None:
        raise ValueError(
            f"Candidate {candidate.candidate_id!r} has no "
            "sleeve_class_path; cannot build sleeve."
        )

    module_path, _, class_name = candidate.sleeve_class_path.rpartition(".")
    if not module_path:
        raise ValueError(
            f"Invalid sleeve_class_path: {candidate.sleeve_class_path!r}"
        )
    module = importlib.import_module(module_path)
    sleeve_class = getattr(module, class_name)

    # Determine sleeve dataclass field names (frozen dataclasses
    # declared via @dataclass).
    sleeve_fields = {f.name for f in dataclasses.fields(sleeve_class)}

    # Filter parameter_set to sleeve-field keys only.
    filtered = {
        k: v for k, v in candidate.parameter_set.items() if k in sleeve_fields
    }
    # Mandatory overrides.
    filtered["allowed_instruments"] = candidate.universe
    filtered["sleeve_id"] = candidate.candidate_id

    return sleeve_class(**filtered)
```

Update `__all__` in `sleeves/base.py` to include `build_sleeve_from_candidate`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_sleeve_loader.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/sleeves/base.py tests/unit/test_sleeve_loader.py
git commit -m "feat(sleeves): add build_sleeve_from_candidate loader"
```

### Task 10: Route sleeve candidates through `simulate_sleeve_returns` in `_candidate_returns`

**Files:**
- Modify: `src/tradingx/validation.py`
- Modify: `tests/unit/test_validation.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_validation.py`:

```python
def test_candidate_returns_routes_through_sleeve_when_path_present(
    sample_bars_by_symbol_fixture,
    sample_regime_snapshots_by_date_fixture,
):
    """Candidates with sleeve_class_path flow through simulate_sleeve_returns;
    candidates without fall through to run_daily_bar_backtest."""
    from tradingx.types import StrategyCandidate
    candidate = StrategyCandidate(
        candidate_id="trend-test-v1",
        family="trend_following",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={"lookback_days": 100, "forecast_method": "ewma"},
        status="under_evaluation",
        sleeve_class_path="tradingx.sleeves.trend.TrendSleeve",
    )
    returns, drag = _candidate_returns(
        candidate,
        bars_by_symbol=sample_bars_by_symbol_fixture,
        regime_snapshots_by_date=sample_regime_snapshots_by_date_fixture,
        sleeve_budget_equity=Decimal("100000"),
    )
    assert isinstance(returns, tuple)
    assert isinstance(drag, Decimal)
```

Fixtures `sample_regime_snapshots_by_date_fixture` and `sample_bars_by_symbol_fixture` will be needed. Reuse whatever fixture pattern exists in `test_validation.py`; create the regime-snapshots fixture as a simple date → `risk_on` mapping over the bar index.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_validation.py -k routes_through_sleeve -v`

Expected: FAIL — `_candidate_returns` doesn't accept `regime_snapshots_by_date` or `sleeve_budget_equity`.

- [ ] **Step 3: Implement**

In `src/tradingx/validation.py`, update `_candidate_returns`:

```python
def _candidate_returns(
    candidate: StrategyCandidate,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    parameter_overrides: dict[str, ScalarValue] | None = None,
    cost_model_config: CostModelConfig | None = None,
    regime_snapshots_by_date: dict[date, RegimeSnapshot] | None = None,
    sleeve_budget_equity: Decimal | None = None,
) -> tuple[tuple[Decimal, ...], Decimal]:
    # NEW: sleeve-path routing
    if candidate.sleeve_class_path is not None:
        from tradingx.sleeves.base import build_sleeve_from_candidate
        from tradingx.sleeves.evaluation import simulate_sleeve_returns

        if regime_snapshots_by_date is None:
            raise ValueError(
                "regime_snapshots_by_date is required for sleeve-path "
                f"candidates; got None for {candidate.candidate_id!r}"
            )
        if sleeve_budget_equity is None:
            sleeve_budget_equity = Decimal("100000")  # sensible default
        sleeve = build_sleeve_from_candidate(candidate)
        return simulate_sleeve_returns(
            sleeve,
            bars_by_symbol=bars_by_symbol,
            regime_snapshots_by_date=regime_snapshots_by_date,
            sleeve_budget_equity=sleeve_budget_equity,
            cost_model_config=cost_model_config,
        )

    # Existing legacy path (baseline candidates via mandatory
    # registry with sleeve_class_path=None)
    configured_candidate = _candidate_with_parameter_overrides(
        candidate,
        parameter_overrides=parameter_overrides,
    )
    # ...rest of existing implementation unchanged...
```

Update callers of `_candidate_returns` in `validation.py` to pass `regime_snapshots_by_date` when the candidate is sleeve-path. Use `AlpacaRegularHoursCalendar.session_dates_between` + `classify_regime` per-session to build the dict.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validation.py -v`

Expected: all pass; legacy tests still green.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/validation.py tests/unit/test_validation.py
git commit -m "feat(validation): route sleeve-path candidates through simulate_sleeve_returns"
```

---

## W7 — Integration + regression

### Task 11: End-to-end integration test

**Files:**
- Create: `tests/integration/test_sleeves_end_to_end.py`

- [ ] **Step 1: Write the integration test**

Create `tests/integration/test_sleeves_end_to_end.py`:

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from tradingx.features.regime import classify_regime
from tradingx.sleeves.evaluation import simulate_sleeve_returns
from tradingx.sleeves.trend import TrendSleeve
from tradingx.sleeves.vol_managed_beta import VolManagedBetaSleeve
from tradingx.types import RegimeSnapshot


def _build_bars(n: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(seed=19)
    returns = rng.normal(scale=0.01, size=n)
    closes = 100.0 * np.cumprod(1.0 + returns)
    dates = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "volume": [1e7] * n,
        },
        index=dates,
    )


def _build_regimes(bars: pd.DataFrame) -> dict[date, RegimeSnapshot]:
    # Build minimal regime snapshots from SPY-only inputs; vix and
    # yield-curve optional.
    closes = bars["close"].astype(float)
    sma = closes.rolling(200).mean()
    regimes: dict[date, RegimeSnapshot] = {}
    for ts in bars.index:
        obs_date = ts.date()
        spy_close = closes.loc[ts]
        spy_sma = sma.loc[ts]
        if pd.isna(spy_sma):
            continue
        regimes[obs_date] = classify_regime(
            observation_date=obs_date,
            spy_close=Decimal(str(float(spy_close))),
            spy_sma_200=Decimal(str(float(spy_sma))),
            vix_close=None,
            yield_curve_spread_bps=None,
        )
    return regimes


def test_trend_sleeve_end_to_end_produces_return_series():
    bars = _build_bars()
    regimes = _build_regimes(bars)
    sleeve = TrendSleeve(allowed_instruments=("SPY",))
    returns, drag = simulate_sleeve_returns(
        sleeve,
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=regimes,
        sleeve_budget_equity=Decimal("100000"),
    )
    assert len(returns) > 0
    assert all(isinstance(r, Decimal) for r in returns)
    assert drag >= Decimal("0")


def test_vol_managed_beta_sleeve_end_to_end_produces_return_series():
    bars = _build_bars()
    regimes = _build_regimes(bars)
    sleeve = VolManagedBetaSleeve()
    returns, drag = simulate_sleeve_returns(
        sleeve,
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=regimes,
        sleeve_budget_equity=Decimal("100000"),
    )
    assert len(returns) > 0
    assert drag >= Decimal("0")
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/integration/test_sleeves_end_to_end.py -v`

Expected: both pass.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_sleeves_end_to_end.py
git commit -m "test(sleeves): add end-to-end integration for trend and vol-managed sleeves"
```

### Task 12: Full regression + lint + typecheck + index + validate

- [ ] **Step 1: pytest**

Run: `uv run pytest -q --deselect tests/contract/test_weight_snapshot_origin.py`

Expected: all pass.

- [ ] **Step 2: mypy**

Run: `uv run mypy src/tradingx`

Expected: no issues.

- [ ] **Step 3: ruff**

Run: `uv run ruff check src/tradingx tests`

Expected: clean.

- [ ] **Step 4: check_index**

Run: `python3 scripts/check_index.py`

Expected: `INDEX validation passed.`

- [ ] **Step 5: validate**

Run: `./scripts/validate`

Expected: clean.

- [ ] **Step 6: Commit formatting fixups if any**

```bash
git status
# if auto-format diffs appear:
git add -u
git commit -m "chore: formatting fixups after tranche 1.3 sleeves"
```

Skip if no fixups needed.

---

## Self-review

### Spec coverage

- DESIGN-0014 W1 (protocol + types + failure-emission contract): Tasks 1–2.
- DESIGN-0014 W2 (regime gate): Task 3.
- DESIGN-0014 W3 (TrendSleeve): Task 4.
- DESIGN-0014 W4 (VolManagedBetaSleeve): Task 5.
- DESIGN-0014 W5 (evaluation bridge — target-weight history + thin wrapper): Tasks 6–7.
- DESIGN-0014 W6 (strategy registry + loader + routing): Tasks 8–10.
- DESIGN-0014 W7 (regression): Tasks 11–12.

### Placeholder scan

No TBD / TODO / "implement later". Every code block is concrete.

### Type consistency

- `SleeveFailureReason` constants defined in Task 1 used consistently in Tasks 4, 5, 6.
- `SleeveContext` / `SleeveTrade` shape defined in Task 1 used consistently in Tasks 2–6.
- `apply_regime_exposure_floor` return shape `(Decimal, str)` from Task 3 consumed by Tasks 4, 5.
- `_compute_current_weight` and `_derive_side` helpers defined in Task 4's `trend.py` imported by Task 5's `vol_managed_beta.py` — same module scope preserved.
- `simulate_sleeve_returns` return `(tuple[Decimal, ...], Decimal)` from Task 7 matches `_candidate_returns()` contract consumed by Task 10.

### Open judgment calls left to the implementer

1. **`_compute_current_weight` / `_derive_side` duplication.** Currently defined in `trend.py` and imported by `vol_managed_beta.py` as a pragmatic shortcut. If this import shape feels wrong, Codex may move the helpers to `sleeves/base.py`. Tests would still pass.
2. **Regime snapshot source for `_candidate_returns` callers.** Task 10 assumes callers build `regime_snapshots_by_date` via `AlpacaRegularHoursCalendar.session_dates_between` + `classify_regime`. If the call sites in `validation.py` expose a different entry point, adapt the construction without rewriting the contract.
3. **Fixture names** — tests use placeholders like `sample_bars_by_symbol_fixture`. Match whatever already exists in each target test file.

### Execution handoff

Plan is for Codex to execute. No subagent-driven or inline execution invocation from this session. Same pattern as tranche 1.1 and 1.2.
