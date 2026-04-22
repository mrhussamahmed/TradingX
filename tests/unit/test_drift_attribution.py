from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.drift.attribution import (
    SleeveAttributionRecorder,
    build_sleeve_daily_attribution_record,
)
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    BlueprintActivationRecord,
    BlueprintSleeveBinding,
    ExecutionLifecycleRecord,
    PortfolioState,
    PositionSnapshot,
    SleeveDecompositionRecord,
    SleeveTargetWeights,
    StrategyCandidate,
)


def _state(
    *,
    equity: Decimal,
    spy_quantity: Decimal = Decimal("0"),
    spy_price: Decimal = Decimal("100"),
) -> PortfolioState:
    positions = ()
    if spy_quantity > 0:
        positions = (
            PositionSnapshot(
                symbol="SPY",
                quantity=spy_quantity,
                average_entry_price=spy_price,
                market_value=spy_quantity * spy_price,
            ),
        )
    return PortfolioState(
        as_of_utc=datetime(2026, 4, 21, 14, 30, tzinfo=UTC),
        cash=equity - (spy_quantity * spy_price),
        equity=equity,
        buying_power=equity,
        positions=positions,
        open_orders=(),
    )


def _write_blueprint(path: Path) -> None:
    path.write_text(
        "\n".join(
            (
                "blueprint_id: bp-test-v1",
                "sleeve_budgets:",
                "  - sleeve_id: trend-following-v1",
                "    budget_fraction_of_equity: 1.0",
                "    max_correlation_with_other_sleeves: 0.85",
            )
        ),
        encoding="utf-8",
    )


def test_build_record_captures_daily_return() -> None:
    record = build_sleeve_daily_attribution_record(
        attribution_id="attr-1",
        trading_day="2026-04-21",
        active_sleeve_id="trend-following-v1",
        open_portfolio_state=_state(
            equity=Decimal("100000"),
            spy_quantity=Decimal("400"),
        ),
        close_portfolio_state=_state(
            equity=Decimal("101000"),
            spy_quantity=Decimal("400"),
            spy_price=Decimal("102.5"),
        ),
        recorded_at_utc=datetime(2026, 4, 21, 20, 0, tzinfo=UTC),
    )
    assert record.sleeve_id == "trend-following-v1"
    assert record.trading_day == "2026-04-21"
    assert record.starting_equity == Decimal("100000")
    assert record.ending_equity == Decimal("101000")
    assert record.daily_return == Decimal("0.01")


def test_build_record_raises_on_zero_open_equity() -> None:
    with pytest.raises(ValueError, match="starting_equity"):
        build_sleeve_daily_attribution_record(
            attribution_id="attr-x",
            trading_day="2026-04-21",
            active_sleeve_id="x-v1",
            open_portfolio_state=_state(equity=Decimal("0")),
            close_portfolio_state=_state(equity=Decimal("0")),
            recorded_at_utc=datetime(2026, 4, 21, 20, 0, tzinfo=UTC),
        )


class _FakeActivationGateway:
    def __init__(
        self,
        *,
        candidate: StrategyCandidate | None,
        blueprint_activation: BlueprintActivationRecord | None = None,
    ) -> None:
        self._candidate = candidate
        self._blueprint_activation = blueprint_activation

    def get_latest_activation(self):
        return None

    def get_active_candidate(self) -> StrategyCandidate | None:
        return self._candidate

    def get_active_blueprint_activation(self) -> BlueprintActivationRecord | None:
        return self._blueprint_activation


class _FakeStore:
    def __init__(self) -> None:
        self.written = []

    def write_sleeve_daily_attribution_record(self, record):
        self.written.append(record)


class _FakeDecompositionStore:
    def __init__(self, records: tuple[SleeveDecompositionRecord, ...]) -> None:
        self._records = records

    def list_sleeve_decomposition_records(
        self,
        *,
        trading_day: str,
    ) -> tuple[SleeveDecompositionRecord, ...]:
        return tuple(
            record for record in self._records if record.trading_day == trading_day
        )


class _FakeExecutionStore:
    def __init__(
        self,
        *,
        historical_records: tuple[ExecutionLifecycleRecord, ...],
        by_trading_day: dict[str, tuple[ExecutionLifecycleRecord, ...]],
    ) -> None:
        self._historical_records = historical_records
        self._by_trading_day = by_trading_day

    def list_execution_lifecycle_records(
        self,
        *,
        trading_day: str | None = None,
    ) -> tuple[ExecutionLifecycleRecord, ...]:
        if trading_day is None:
            return self._historical_records
        return self._by_trading_day.get(trading_day, ())


def test_recorder_skips_non_sleeve_active_strategy() -> None:
    candidate = StrategyCandidate(
        candidate_id="baseline-long-only-v1",
        family="baseline",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={},
        status="active",
        sleeve_class_path=None,
    )
    recorder = SleeveAttributionRecorder(
        activation_gateway=_FakeActivationGateway(candidate=candidate),
        attribution_store=_FakeStore(),
        now_provider=lambda: datetime(2026, 4, 21, tzinfo=UTC),
    )

    result = recorder.record_session(
        trading_day="2026-04-21",
        open_portfolio_state=_state(equity=Decimal("100000")),
        close_portfolio_state=_state(equity=Decimal("101000")),
    )

    assert result == ()


def test_recorder_writes_record_for_sleeve_backed_active_strategy() -> None:
    candidate = StrategyCandidate(
        candidate_id="trend-following-v1",
        family="trend_following",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={},
        status="active",
        sleeve_class_path="tradingx.sleeves.trend.TrendSleeve",
    )
    store = _FakeStore()
    recorder = SleeveAttributionRecorder(
        activation_gateway=_FakeActivationGateway(candidate=candidate),
        attribution_store=store,
        now_provider=lambda: datetime(2026, 4, 21, tzinfo=UTC),
    )

    result = recorder.record_session(
        trading_day="2026-04-21",
        open_portfolio_state=_state(equity=Decimal("100000")),
        close_portfolio_state=_state(equity=Decimal("101000")),
    )

    assert result == tuple(store.written)
    assert result[0].sleeve_id == "trend-following-v1"
    assert len(store.written) == 1


def test_recorder_prefers_decomposition_records_when_present() -> None:
    store = _FakeStore()
    recorder = SleeveAttributionRecorder(
        activation_gateway=_FakeActivationGateway(candidate=None),
        attribution_store=store,
        now_provider=lambda: datetime(2026, 4, 21, 20, 0, tzinfo=UTC),
        decomposition_store=_FakeDecompositionStore(
            (
                SleeveDecompositionRecord(
                    decomposition_id="decomp-open",
                    cycle_id="cycle-open",
                    trading_day="2026-04-21",
                    recorded_at_utc=datetime(2026, 4, 21, 9, 30, tzinfo=UTC),
                    blueprint_activation_id="bp-1",
                    per_sleeve_target_weights=(
                        SleeveTargetWeights(
                            sleeve_id="trend-following-v1",
                            target_weights_by_symbol=(("SPY", Decimal("0.4")),),
                        ),
                        SleeveTargetWeights(
                            sleeve_id="vol-target-v1",
                            target_weights_by_symbol=(("SPY", Decimal("0.2")),),
                        ),
                    ),
                ),
                SleeveDecompositionRecord(
                    decomposition_id="decomp-close",
                    cycle_id="cycle-close",
                    trading_day="2026-04-21",
                    recorded_at_utc=datetime(2026, 4, 21, 16, 0, tzinfo=UTC),
                    blueprint_activation_id="bp-1",
                    per_sleeve_target_weights=(
                        SleeveTargetWeights(
                            sleeve_id="trend-following-v1",
                            target_weights_by_symbol=(("SPY", Decimal("0.5")),),
                        ),
                        SleeveTargetWeights(
                            sleeve_id="vol-target-v1",
                            target_weights_by_symbol=(("SPY", Decimal("0.1")),),
                        ),
                    ),
                ),
            )
        ),
    )

    result = recorder.record_session(
        trading_day="2026-04-21",
        open_portfolio_state=_state(equity=Decimal("100000")),
        close_portfolio_state=_state(equity=Decimal("102000")),
    )

    assert {record.sleeve_id for record in result} == {
        "trend-following-v1",
        "vol-target-v1",
    }
    by_sleeve = {record.sleeve_id: record for record in result}
    assert by_sleeve["trend-following-v1"].starting_equity == Decimal("40000.0")
    assert by_sleeve["trend-following-v1"].ending_equity == Decimal("40800.000")
    assert by_sleeve["trend-following-v1"].daily_return == Decimal("0.02")
    assert by_sleeve["vol-target-v1"].starting_equity == Decimal("20000.0")
    assert by_sleeve["vol-target-v1"].ending_equity == Decimal("20400.000")
    assert by_sleeve["vol-target-v1"].daily_return == Decimal("0.02")


def test_recorder_rerun_for_same_day_reuses_opening_ledger_state(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    blueprint_path = tmp_path / "bp.yaml"
    _write_blueprint(blueprint_path)
    blueprint_activation = BlueprintActivationRecord(
        activation_id="activation-1",
        blueprint_id="bp-1",
        sleeve_activation_bindings=(
            BlueprintSleeveBinding(
                sleeve_id="trend-following-v1",
                strategy_id="trend-following-v1",
                captured_snapshot_id="snap-trend",
            ),
        ),
        status="active",
        approved_at_utc=datetime(2026, 4, 21, 13, 0, tzinfo=UTC),
        approved_by="operator",
        source_blueprint_path=blueprint_path,
    )
    execution_store = _FakeExecutionStore(
        historical_records=(
            ExecutionLifecycleRecord(
                execution_id="exec-open",
                intent_id="intent-open",
                symbol="SPY",
                side="buy",
                reason_code="entry",
                reference_price=Decimal("100"),
                fill_price=Decimal("100"),
                filled_qty=Decimal("10"),
                slippage_bps=Decimal("0"),
                submitted_at_utc=datetime(2026, 4, 20, 13, 30, tzinfo=UTC),
                filled_at_utc=datetime(2026, 4, 20, 13, 31, tzinfo=UTC),
                recovered=False,
                sleeve_attributions=(("trend-following-v1", Decimal("1")),),
            ),
        ),
        by_trading_day={
            "2026-04-21": (
                ExecutionLifecycleRecord(
                    execution_id="exec-close",
                    intent_id="intent-close",
                    symbol="SPY",
                    side="sell",
                    reason_code="exit",
                    reference_price=Decimal("105"),
                    fill_price=Decimal("105"),
                    filled_qty=Decimal("10"),
                    slippage_bps=Decimal("0"),
                    submitted_at_utc=datetime(2026, 4, 21, 19, 0, tzinfo=UTC),
                    filled_at_utc=datetime(2026, 4, 21, 19, 1, tzinfo=UTC),
                    recovered=False,
                    sleeve_attributions=(("trend-following-v1", Decimal("1")),),
                ),
            )
        },
    )
    recorder = SleeveAttributionRecorder(
        activation_gateway=_FakeActivationGateway(
            candidate=None,
            blueprint_activation=blueprint_activation,
        ),
        attribution_store=store,
        now_provider=lambda: datetime(2026, 4, 21, 20, 0, tzinfo=UTC),
        decomposition_store=_FakeDecompositionStore(
            (
                SleeveDecompositionRecord(
                    decomposition_id="decomp-1",
                    cycle_id="cycle-1",
                    trading_day="2026-04-21",
                    recorded_at_utc=datetime(2026, 4, 21, 9, 30, tzinfo=UTC),
                    blueprint_activation_id="activation-1",
                    per_sleeve_target_weights=(
                        SleeveTargetWeights(
                            sleeve_id="trend-following-v1",
                            target_weights_by_symbol=(("SPY", Decimal("1")),),
                        ),
                    ),
                ),
            )
        ),
        execution_store=execution_store,
    )
    open_state = _state(
        equity=Decimal("1000"),
        spy_quantity=Decimal("10"),
        spy_price=Decimal("100"),
    )
    close_state = _state(equity=Decimal("1050"))

    first_result = recorder.record_session(
        trading_day="2026-04-21",
        open_portfolio_state=open_state,
        close_portfolio_state=close_state,
    )
    second_result = recorder.record_session(
        trading_day="2026-04-21",
        open_portfolio_state=open_state,
        close_portfolio_state=close_state,
    )

    assert first_result == second_result
    assert {record.sleeve_id for record in second_result} == {"trend-following-v1"}
    assert (
        store.list_sleeve_attribution_gap_records(sleeve_id="trend-following-v1") == ()
    )
