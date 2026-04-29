from __future__ import annotations

import threading
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from tradingx import automation as automation_module
from tradingx.automation import MarketDayAutomationRunner
from tradingx.config import TradingConfig
from tradingx.live_enablement import BrokerModeDecision
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    Gate3PromotionPackage,
    Gate3ReadinessReport,
    PortfolioState,
    PositionSnapshot,
    ReplaySlippageGenerationResult,
    ReplaySlippageSummary,
    ServiceCycleSnapshot,
    ServiceRunResult,
)


class FakePaperService:
    def __init__(self) -> None:
        self.calls = 0

    def run(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None = None,
    ) -> ServiceRunResult:
        self.calls += 1
        timestamp = datetime(2026, 4, 18, 13, self.calls, tzinfo=UTC)
        return ServiceRunResult(
            cycles_completed=1,
            last_cycle=ServiceCycleSnapshot(
                cycle_id=f"cycle-{self.calls}",
                started_at_utc=timestamp,
                completed_at_utc=timestamp,
                cycle_status="executed",
                symbols=symbols,
                symbol_results=(),
                blocked_trade_count=0,
                reconciliation_failure_count=0,
                open_position_symbols=("SPY",),
                cash=Decimal("10025.00"),
                equity=Decimal("10030.00"),
                buying_power=Decimal("20030.00"),
            ),
            artifact_paths=(
                Path(f"artifacts/paper_loop/service_cycles/cycle-{self.calls}.json"),
            ),
        )


class _PortfolioGatewayStub:
    def __init__(self, states: list[PortfolioState]) -> None:
        self._states = states
        self._index = 0

    def get_portfolio_state(self) -> PortfolioState:
        state = self._states[min(self._index, len(self._states) - 1)]
        self._index += 1
        return state


class _SpyDriftAlarmGateway:
    def __init__(self) -> None:
        self.refresh_call_count = 0

    def refresh(self):
        self.refresh_call_count += 1
        return ()


class _SpyAttributionRecorder:
    def __init__(self) -> None:
        self.record_session_call_count = 0

    def record_session(
        self,
        *,
        trading_day: str,
        open_portfolio_state: PortfolioState,
        close_portfolio_state: PortfolioState,
    ) -> None:
        del trading_day, open_portfolio_state, close_portfolio_state
        self.record_session_call_count += 1


class _PlainOhlcvMarketDataStub:
    def __init__(self) -> None:
        index = pd.date_range("2025-01-01", periods=430, freq="B", tz="UTC")
        closes = [100.0 + index_ * 0.1 for index_ in range(len(index))]
        self._frame = pd.DataFrame(
            {
                "open": closes,
                "high": [close * 1.005 for close in closes],
                "low": [close * 0.995 for close in closes],
                "close": closes,
                "volume": [1_000_000.0 for _ in closes],
            },
            index=index,
        )

    def get_daily_bar_history(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
    ) -> pd.DataFrame:
        del symbol
        return self._frame.loc[
            (self._frame.index >= start_utc) & (self._frame.index <= end_utc)
        ].copy()


def _portfolio_state(*, equity: str) -> PortfolioState:
    equity_decimal = Decimal(equity)
    return PortfolioState(
        as_of_utc=datetime(2026, 4, 18, 13, 0, tzinfo=UTC),
        cash=equity_decimal,
        equity=equity_decimal,
        buying_power=equity_decimal,
        positions=(
            PositionSnapshot(
                symbol="SPY",
                quantity=Decimal("1"),
                average_entry_price=Decimal("500"),
                market_value=Decimal("500"),
            ),
        ),
        open_orders=(),
    )


def _fake_replay_generator(
    *,
    paper_store: FilesystemArtifactStore,
    validation_store: FilesystemArtifactStore,
) -> ReplaySlippageGenerationResult:
    del paper_store
    summary = ReplaySlippageSummary(
        summary_id="replay-summary-1",
        matched_execution_count=1,
        paper_mean_absolute_slippage_bps=Decimal("5.0"),
        replay_mean_absolute_slippage_bps=Decimal("7.5"),
        divergence_ratio=Decimal("1.5"),
        status="pass",
        details="Replay divergence is within the allowed bound.",
        generated_at_utc=datetime(2026, 4, 18, 13, 10, tzinfo=UTC),
    )
    path = validation_store.write_replay_slippage_summary(summary)
    return ReplaySlippageGenerationResult(
        summary=summary,
        record_paths=(),
        summary_path=path,
    )


def _fake_gate3_report_builder(
    *,
    paper_store: FilesystemArtifactStore,
    validation_store: FilesystemArtifactStore,
) -> Gate3ReadinessReport:
    del paper_store, validation_store
    return Gate3ReadinessReport(
        report_id="gate3-1",
        generated_at_utc=datetime(2026, 4, 18, 13, 11, tzinfo=UTC),
        status="pending",
        closed_trade_count=2,
        calendar_days_observed=12,
        criteria=(),
        summary="Gate 3 remains pending.",
        required_operator_action="Keep collecting evidence.",
        evidence_refs=(),
    )


def _fake_gate3_package_builder(
    report: Gate3ReadinessReport,
) -> Gate3PromotionPackage:
    return Gate3PromotionPackage(
        package_id="gate3-package-1",
        generated_at_utc=report.generated_at_utc,
        status=report.status,
        headline="Gate 3 still pending.",
        decision_summary=report.summary,
        criteria_statuses={},
        evidence_refs=(),
    )


def test_market_day_automation_runner_writes_run_record_and_refreshes_gate3(
    tmp_path,
) -> None:
    validation_store = FilesystemArtifactStore(tmp_path / "artifacts" / "validation")
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    fake_service = FakePaperService()
    sleep_calls: list[int] = []

    def fake_replay_generator(
        *,
        paper_store: FilesystemArtifactStore,
        validation_store: FilesystemArtifactStore,
    ) -> ReplaySlippageGenerationResult:
        summary = ReplaySlippageSummary(
            summary_id="replay-summary-1",
            matched_execution_count=1,
            paper_mean_absolute_slippage_bps=Decimal("5.0"),
            replay_mean_absolute_slippage_bps=Decimal("7.5"),
            divergence_ratio=Decimal("1.5"),
            status="pass",
            details="Replay divergence is within the allowed bound.",
            generated_at_utc=datetime(2026, 4, 18, 13, 10, tzinfo=UTC),
        )
        path = validation_store.write_replay_slippage_summary(summary)
        return ReplaySlippageGenerationResult(
            summary=summary,
            record_paths=(),
            summary_path=path,
        )

    def fake_gate3_report_builder(
        *,
        paper_store: FilesystemArtifactStore,
        validation_store: FilesystemArtifactStore,
    ) -> Gate3ReadinessReport:
        return Gate3ReadinessReport(
            report_id="gate3-1",
            generated_at_utc=datetime(2026, 4, 18, 13, 11, tzinfo=UTC),
            status="pending",
            closed_trade_count=2,
            calendar_days_observed=12,
            criteria=(),
            summary="Gate 3 remains pending.",
            required_operator_action="Keep collecting evidence.",
            evidence_refs=(),
        )

    def fake_gate3_package_builder(
        report: Gate3ReadinessReport,
    ) -> Gate3PromotionPackage:
        return Gate3PromotionPackage(
            package_id="gate3-package-1",
            generated_at_utc=report.generated_at_utc,
            status=report.status,
            headline="Gate 3 still pending.",
            decision_summary=report.summary,
            criteria_statuses={},
            evidence_refs=(),
        )

    runner = MarketDayAutomationRunner(
        paper_store=paper_store,
        validation_store=validation_store,
        operator_store=operator_store,
        service_builder=lambda: fake_service,
        replay_generator=fake_replay_generator,
        gate3_report_builder=fake_gate3_report_builder,
        gate3_package_builder=fake_gate3_package_builder,
        now_provider=lambda: datetime(2026, 4, 18, 13, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
    )

    result = runner.run_market_day(
        symbols=("SPY", "QQQ"),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_heartbeats=2,
    )

    assert fake_service.calls == 2
    assert sleep_calls == [300]
    assert result.run_record.status == "completed"
    assert result.run_record.heartbeat_count == 2
    assert result.run_record_path.exists()
    assert result.replay_summary_path is not None
    assert result.gate3_report_path is not None
    assert result.gate3_package_path is not None
    assert len(result.session_paths) == 4
    assert len({path.name for path in result.session_paths}) == 4
    assert len({path.name for path in result.daily_digest_paths}) == 4
    market_sessions = list(
        (tmp_path / "artifacts" / "operator_platform" / "market_sessions").glob(
            "*.json"
        )
    )
    assert len(market_sessions) == 4


def test_market_day_automation_runner_stops_before_next_heartbeat_when_requested(
    tmp_path,
) -> None:
    validation_store = FilesystemArtifactStore(tmp_path / "artifacts" / "validation")
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    fake_service = FakePaperService()
    stop_event = threading.Event()
    sleep_calls: list[int] = []

    runner = MarketDayAutomationRunner(
        paper_store=paper_store,
        validation_store=validation_store,
        operator_store=operator_store,
        service_builder=lambda: fake_service,
        now_provider=lambda: datetime(2026, 4, 18, 13, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
    )

    stop_event.set()
    result = runner.run_market_day(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_heartbeats=2,
        stop_event=stop_event,
    )

    assert fake_service.calls == 0
    assert sleep_calls == []
    assert result.run_record.status == "stopped"
    assert result.run_record.heartbeat_count == 0


def test_market_day_automation_runner_records_exception_context_in_summary(
    tmp_path,
) -> None:
    validation_store = FilesystemArtifactStore(tmp_path / "artifacts" / "validation")
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )

    class FailingService(FakePaperService):
        def run(
            self,
            *,
            symbols: tuple[str, ...],
            quantity: Decimal,
            interval_seconds: int,
            max_cycles: int | None = None,
        ) -> ServiceRunResult:
            del symbols, quantity, interval_seconds, max_cycles
            raise RuntimeError("heartbeat exploded")

    runner = MarketDayAutomationRunner(
        paper_store=paper_store,
        validation_store=validation_store,
        operator_store=operator_store,
        service_builder=lambda: FailingService(),
        now_provider=lambda: datetime(2026, 4, 18, 13, 0, tzinfo=UTC),
    )

    result = runner.run_market_day(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_heartbeats=1,
    )

    assert result.run_record.status == "failed"
    assert "heartbeat exploded" in result.run_record.summary


def test_automation_calls_drift_gateway_refresh_at_end_of_session(tmp_path) -> None:
    validation_store = FilesystemArtifactStore(tmp_path / "artifacts" / "validation")
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    drift_gateway = _SpyDriftAlarmGateway()
    attribution_recorder = _SpyAttributionRecorder()
    portfolio_gateway = _PortfolioGatewayStub(
        [_portfolio_state(equity="100000"), _portfolio_state(equity="101000")]
    )
    runner = MarketDayAutomationRunner(
        paper_store=paper_store,
        validation_store=validation_store,
        operator_store=operator_store,
        service_builder=lambda: FakePaperService(),
        portfolio_gateway=portfolio_gateway,
        drift_alarm_gateway=drift_gateway,
        attribution_recorder=attribution_recorder,
        replay_generator=_fake_replay_generator,
        gate3_report_builder=_fake_gate3_report_builder,
        gate3_package_builder=_fake_gate3_package_builder,
        now_provider=lambda: datetime(2026, 4, 18, 20, 0, tzinfo=UTC),
    )

    runner.run_preopen()
    runner.run_close()

    assert drift_gateway.refresh_call_count == 1
    assert attribution_recorder.record_session_call_count == 1


def test_automation_close_without_preopen_refreshes_drift_but_skips_attribution(
    tmp_path,
) -> None:
    validation_store = FilesystemArtifactStore(tmp_path / "artifacts" / "validation")
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    drift_gateway = _SpyDriftAlarmGateway()
    attribution_recorder = _SpyAttributionRecorder()
    runner = MarketDayAutomationRunner(
        paper_store=paper_store,
        validation_store=validation_store,
        operator_store=operator_store,
        service_builder=lambda: FakePaperService(),
        portfolio_gateway=_PortfolioGatewayStub(
            [_portfolio_state(equity="100000"), _portfolio_state(equity="101000")]
        ),
        drift_alarm_gateway=drift_gateway,
        attribution_recorder=attribution_recorder,
        replay_generator=_fake_replay_generator,
        gate3_report_builder=_fake_gate3_report_builder,
        gate3_package_builder=_fake_gate3_package_builder,
        now_provider=lambda: datetime(2026, 4, 18, 20, 0, tzinfo=UTC),
    )

    runner.run_close()

    assert drift_gateway.refresh_call_count == 1
    assert attribution_recorder.record_session_call_count == 0


def test_backtest_reference_generation_accepts_plain_ohlcv_bars(tmp_path) -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
            "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
            "TRADINGX_SYMBOL_UNIVERSE": "SPY",
        }
    )

    automation_module._ensure_backtest_reference_returns(
        config=config,
        market_data_gateway=_PlainOhlcvMarketDataStub(),
        now_provider=lambda: datetime(2026, 4, 18, 13, 0, tzinfo=UTC),
        force_rebuild=True,
    )

    for sleeve_id in ("trend-following-v1", "vol-target-v1"):
        assert automation_module.backtest_reference_artifact_path(
            artifact_root=config.runtime.artifact_root,
            sleeve_id=sleeve_id,
        ).exists()


def test_build_default_market_day_automation_runner_uses_generic_service_builder(
    monkeypatch, tmp_path
) -> None:
    helper_calls: dict[str, object] = {}
    fake_service = FakePaperService()

    monkeypatch.setattr(
        automation_module,
        "resolve_broker_mode",
        lambda config: BrokerModeDecision(
            requested_mode="live",
            effective_mode="live",
            live_requested=True,
            live_allowed=True,
            disable_reasons=(),
        ),
    )

    def fake_build_trading_client(config, decision):
        del config
        helper_calls["client_mode"] = decision.requested_mode
        return object()

    def fake_build_market_data(config, *, broker_mode=None):
        del config
        helper_calls["market_data_mode"] = broker_mode
        return object()

    class FakeRuntimeRegistry:
        def can_resolve(self, strategy_id: str) -> bool:
            del strategy_id
            return True

    monkeypatch.setattr(
        automation_module,
        "build_trading_client_for_mode",
        fake_build_trading_client,
    )
    monkeypatch.setattr(
        automation_module,
        "build_market_data_gateway_for_mode",
        fake_build_market_data,
    )
    monkeypatch.setattr(
        automation_module,
        "build_default_runtime_registry",
        lambda **kwargs: FakeRuntimeRegistry(),
    )
    monkeypatch.setattr(
        automation_module,
        "LocalActivationGateway",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        automation_module,
        "_resolve_drift_reference_snapshot",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        automation_module,
        "DriftAlarmGateway",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        automation_module,
        "SleeveAttributionRecorder",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        automation_module,
        "AlpacaPortfolioGateway",
        lambda trading_client: object(),
    )
    monkeypatch.setattr(
        automation_module,
        "build_default_trading_service",
        lambda config: fake_service,
    )

    runner = automation_module.build_default_market_day_automation_runner(
        TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
                "ALPACA_LIVE_API_KEY": "pk-live",
                "ALPACA_LIVE_API_SECRET": "sk-live",
                "TRADINGX_BROKER_MODE": "live",
            }
        )
    )

    assert runner._service_builder() is fake_service
    assert helper_calls == {
        "client_mode": "live",
        "market_data_mode": "live",
    }
