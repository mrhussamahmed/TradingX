from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from tradingx.portfolio.sleeve_runtime import (
    RollingWindowSource,
    SleeveRuntimeConfig,
    SleeveRuntimeController,
)
from tradingx.types import (
    RegimeSnapshot,
    SleeveContext,
    SleeveFailureReason,
    SleeveTrade,
    TrialRecord,
)


class _FakeSleeve:
    sleeve_id = "trend-following-v1"
    family = "trend_following"
    allowed_instruments = ("SPY",)

    def __init__(self, response: tuple[SleeveTrade, ...]) -> None:
        self._response = response

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        return self._response


class _CustomIdSleeve(_FakeSleeve):
    sleeve_id = "custom-trend"


class _FakeHaltStore:
    def __init__(self, halted_ids: set[str]) -> None:
        self._halted = halted_ids

    def is_halted(self, *, sleeve_id: str) -> bool:
        return sleeve_id in self._halted


class _FakeDriftGateway:
    def __init__(self, alarmed: set[str]) -> None:
        self._alarmed = alarmed

    def has_alarm(self, *, sleeve_id: str) -> bool:
        return sleeve_id in self._alarmed


class _FakeTrialsLedger:
    def __init__(self, trials: tuple[TrialRecord, ...]) -> None:
        self._trials = trials

    def records_for_candidate(self, candidate_id: str) -> tuple[TrialRecord, ...]:
        return tuple(
            trial for trial in self._trials if trial.candidate_id == candidate_id
        )


def _regime(state: str = "risk_on") -> RegimeSnapshot:
    return RegimeSnapshot(
        observation_date=date(2026, 4, 21),
        regime=state,
        above_sma_200=True,
        vix_elevated=False,
        vix_stressed=False,
        yield_curve_inverted=False,
        spy_close=Decimal("500"),
        spy_sma_200=Decimal("480"),
        vix_close=Decimal("15"),
        yield_curve_spread_bps=Decimal("35"),
    )


def _context(weight: Decimal = Decimal("0.4")) -> SleeveContext:
    return SleeveContext(
        observation_date=date(2026, 4, 21),
        bars_by_symbol={"SPY": pd.DataFrame()},
        regime=_regime(),
        current_weights_by_symbol={"SPY": weight},
        sleeve_budget_equity=Decimal("100000"),
    )


def _trial(
    *,
    candidate_id: str,
    sharpe: str,
    window_days: int = 63,
    days_ago: int = 1,
) -> TrialRecord:
    end = datetime.now(UTC) - timedelta(days=days_ago)
    start = end - timedelta(days=window_days)
    return TrialRecord(
        trial_id=f"trial-{candidate_id}-{days_ago}",
        candidate_id=candidate_id,
        family="trend_following",
        window_start_utc=start,
        window_end_utc=end,
        observed_sharpe_net_of_costs=Decimal(sharpe),
        observed_cagr_net_of_costs=Decimal("0.05"),
        observed_max_drawdown=Decimal("0.10"),
        observed_cdar_95=Decimal("0.05"),
        annualized_cost_drag_bps=Decimal("20"),
        passed=False,
        recorded_at_utc=end,
        git_sha="test",
        config_fingerprint="test",
    )


def _sleeve_trade(side: str = "buy") -> tuple[SleeveTrade, ...]:
    return (
        SleeveTrade(
            sleeve_id="trend-following-v1",
            symbol="SPY",
            side=side,
            target_weight_of_sleeve_budget=Decimal("0.6"),
            rationale="tsmom_long_vol_targeted",
            regime="risk_on",
        ),
    )


def _config() -> SleeveRuntimeConfig:
    return SleeveRuntimeConfig(
        three_month_sharpe_floor=Decimal("0.0"),
        three_month_window_days=63,
        trial_lookback=3,
        rolling_window_source=RollingWindowSource.TRIAL_SUMMARY,
    )


def test_controller_delegates_when_no_termination_fires() -> None:
    controller = SleeveRuntimeController(
        wrapped_sleeve=_FakeSleeve(_sleeve_trade()),
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=_config(),
    )

    out = controller.plan_for_bar(_context())

    assert len(out) == 1
    assert out[0].rationale == "tsmom_long_vol_targeted"


def test_operator_halt_precedes_sleeve() -> None:
    controller = SleeveRuntimeController(
        wrapped_sleeve=_FakeSleeve(_sleeve_trade()),
        operator_halt_store=_FakeHaltStore({"trend-following-v1"}),
        drift_alarm_gateway=_FakeDriftGateway({"trend-following-v1"}),
        trials_ledger=_FakeTrialsLedger(()),
        config=_config(),
    )

    out = controller.plan_for_bar(_context())

    assert out[0].rationale == SleeveFailureReason.HALT_BY_OPERATOR


def test_drift_alarm_precedes_sharpe_gate() -> None:
    failing = tuple(
        _trial(candidate_id="trend-following-v1", sharpe="-0.5", days_ago=days_ago)
        for days_ago in (1, 2, 3)
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=_FakeSleeve(_sleeve_trade()),
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway({"trend-following-v1"}),
        trials_ledger=_FakeTrialsLedger(failing),
        config=_config(),
    )

    out = controller.plan_for_bar(_context())

    assert out[0].rationale == SleeveFailureReason.DRIFT_ALARM_LIVE


def test_sharpe_gate_fires_when_lookback_consecutive_trials_below_floor() -> None:
    failing = tuple(
        _trial(candidate_id="trend-following-v1", sharpe="-0.5", days_ago=days_ago)
        for days_ago in (1, 2, 3)
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=_FakeSleeve(_sleeve_trade()),
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(failing),
        config=_config(),
    )

    out = controller.plan_for_bar(_context())

    assert out[0].rationale == SleeveFailureReason.SLEEVE_SHARPE_BELOW_THRESHOLD_6M


def test_sharpe_gate_uses_trial_candidate_override() -> None:
    failing = tuple(
        _trial(candidate_id="trend-following-v1", sharpe="-0.5", days_ago=days_ago)
        for days_ago in (1, 2, 3)
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=_CustomIdSleeve(_sleeve_trade()),
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(failing),
        config=_config(),
        trial_candidate_id="trend-following-v1",
    )

    out = controller.plan_for_bar(_context())

    assert out[0].rationale == SleeveFailureReason.SLEEVE_SHARPE_BELOW_THRESHOLD_6M


def test_sharpe_gate_does_not_fire_when_one_recent_trial_passes() -> None:
    mixed = (
        _trial(candidate_id="trend-following-v1", sharpe="0.5", days_ago=1),
        _trial(candidate_id="trend-following-v1", sharpe="-0.5", days_ago=2),
        _trial(candidate_id="trend-following-v1", sharpe="-0.5", days_ago=3),
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=_FakeSleeve(_sleeve_trade()),
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(mixed),
        config=_config(),
    )

    out = controller.plan_for_bar(_context())

    assert out[0].rationale == "tsmom_long_vol_targeted"


def test_sharpe_gate_skips_when_fewer_than_lookback_qualifying_trials() -> None:
    short = tuple(
        _trial(candidate_id="trend-following-v1", sharpe="-0.5", days_ago=days_ago)
        for days_ago in (1, 2)
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=_FakeSleeve(_sleeve_trade()),
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(short),
        config=_config(),
    )

    out = controller.plan_for_bar(_context())

    assert out[0].rationale == "tsmom_long_vol_targeted"


def test_sharpe_gate_ignores_short_window_trials() -> None:
    short_windows = tuple(
        _trial(
            candidate_id="trend-following-v1",
            sharpe="-0.5",
            window_days=30,
            days_ago=days_ago,
        )
        for days_ago in (1, 2, 3)
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=_FakeSleeve(_sleeve_trade()),
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(short_windows),
        config=_config(),
    )

    out = controller.plan_for_bar(_context())

    assert out[0].rationale == "tsmom_long_vol_targeted"


def test_live_daily_returns_above_floor_does_not_fire_gate() -> None:
    import numpy as np

    positive = np.random.default_rng(seed=1337).normal(
        loc=0.002,
        scale=0.005,
        size=63,
    )

    class _Source:
        def live_daily_returns(self, *, sleeve_id, window_days):
            del sleeve_id, window_days
            return tuple(Decimal(str(value)) for value in positive)

    controller = SleeveRuntimeController(
        wrapped_sleeve=_FakeSleeve(_sleeve_trade()),
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=SleeveRuntimeConfig(
            three_month_sharpe_floor=Decimal("0.0"),
            three_month_window_days=63,
            trial_lookback=3,
            rolling_window_source=RollingWindowSource.LIVE_DAILY_RETURNS,
        ),
        live_daily_returns_source=_Source(),
    )

    out = controller.plan_for_bar(_context())

    assert out[0].rationale == "tsmom_long_vol_targeted"


def test_live_daily_returns_below_floor_fires_sharpe_gate() -> None:
    import numpy as np

    negative = np.random.default_rng(seed=2026).normal(
        loc=-0.002,
        scale=0.005,
        size=63,
    )

    class _Source:
        def live_daily_returns(self, *, sleeve_id, window_days):
            del sleeve_id, window_days
            return tuple(Decimal(str(value)) for value in negative)

    controller = SleeveRuntimeController(
        wrapped_sleeve=_FakeSleeve(_sleeve_trade()),
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=SleeveRuntimeConfig(
            three_month_sharpe_floor=Decimal("0.0"),
            three_month_window_days=63,
            trial_lookback=3,
            rolling_window_source=RollingWindowSource.LIVE_DAILY_RETURNS,
        ),
        live_daily_returns_source=_Source(),
    )

    out = controller.plan_for_bar(_context())

    assert out[0].rationale == SleeveFailureReason.SLEEVE_SHARPE_BELOW_THRESHOLD_6M


def test_live_daily_returns_zero_variance_returns_pending() -> None:
    class _Source:
        def live_daily_returns(self, *, sleeve_id, window_days):
            del sleeve_id, window_days
            return tuple(Decimal("0.001") for _ in range(63))

    controller = SleeveRuntimeController(
        wrapped_sleeve=_FakeSleeve(_sleeve_trade()),
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=SleeveRuntimeConfig(
            three_month_sharpe_floor=Decimal("0.0"),
            three_month_window_days=63,
            trial_lookback=3,
            rolling_window_source=RollingWindowSource.LIVE_DAILY_RETURNS,
        ),
        live_daily_returns_source=_Source(),
    )

    out = controller.plan_for_bar(_context())

    assert out[0].rationale == "tsmom_long_vol_targeted"


def test_live_daily_returns_insufficient_records_skips_gate() -> None:
    class _Source:
        def live_daily_returns(self, *, sleeve_id, window_days):
            del sleeve_id, window_days
            return tuple(Decimal("-0.1") for _ in range(10))

    controller = SleeveRuntimeController(
        wrapped_sleeve=_FakeSleeve(_sleeve_trade()),
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=SleeveRuntimeConfig(
            three_month_sharpe_floor=Decimal("0.0"),
            three_month_window_days=63,
            trial_lookback=3,
            rolling_window_source=RollingWindowSource.LIVE_DAILY_RETURNS,
        ),
        live_daily_returns_source=_Source(),
    )

    out = controller.plan_for_bar(_context())

    assert out[0].rationale == "tsmom_long_vol_targeted"


def test_live_daily_returns_source_missing_raises_value_error() -> None:
    controller = SleeveRuntimeController(
        wrapped_sleeve=_FakeSleeve(_sleeve_trade()),
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=SleeveRuntimeConfig(
            three_month_sharpe_floor=Decimal("0.0"),
            three_month_window_days=63,
            trial_lookback=3,
            rolling_window_source=RollingWindowSource.LIVE_DAILY_RETURNS,
        ),
        live_daily_returns_source=None,
    )

    with pytest.raises(ValueError, match="live_daily_returns_source"):
        controller.plan_for_bar(_context())


def test_termination_emits_side_sell_when_currently_holding() -> None:
    controller = SleeveRuntimeController(
        wrapped_sleeve=_FakeSleeve(_sleeve_trade()),
        operator_halt_store=_FakeHaltStore({"trend-following-v1"}),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=_config(),
    )

    out = controller.plan_for_bar(_context())

    assert out[0].side == "sell"
    assert out[0].target_weight_of_sleeve_budget == Decimal("0")


def test_termination_emits_side_hold_when_not_holding() -> None:
    controller = SleeveRuntimeController(
        wrapped_sleeve=_FakeSleeve(_sleeve_trade()),
        operator_halt_store=_FakeHaltStore({"trend-following-v1"}),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=_config(),
    )

    out = controller.plan_for_bar(_context(weight=Decimal("0")))

    assert out[0].side == "hold"
    assert out[0].target_weight_of_sleeve_budget == Decimal("0")
