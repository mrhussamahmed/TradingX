"""Concrete live drift alarm gateway and default readers."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Protocol

import pandas as pd  # type: ignore[import-untyped]

from tradingx.drift.backtest_reference import load_backtest_reference_returns
from tradingx.drift.blueprint import DriftMonitorBlueprint
from tradingx.drift.execution import compute_execution_drift_ratio
from tradingx.drift.ks import compute_kolmogorov_smirnov
from tradingx.drift.pnl_divergence import compute_live_vs_backtest_pnl_divergence
from tradingx.drift.psi import compute_population_stability_index
from tradingx.drift.reference import ReferenceDistributionSnapshot
from tradingx.features.volatility import forecast_volatility
from tradingx.persistence import FilesystemArtifactStore
from tradingx.risk_free import load_treasury_yield_cache
from tradingx.signals.trend import generate_trend_signal
from tradingx.signals.vol_target_spy import generate_vol_target_spy_signal
from tradingx.strategy import build_mandatory_candidate_registry
from tradingx.types import (
    DriftMonitorVerdictRecord,
    OperatorAlert,
    ReplaySlippageRecord,
    RiskControlEvent,
    SleeveDailyAttributionRecord,
    StrategyCandidate,
)

DRIFT_ALARM_CONTROL_TYPE: Final[str] = "portfolio_drift_alarm"


@dataclass(frozen=True)
class DriftMonitorVerdict:
    monitor_id: str
    sleeve_id: str | None
    severity: str
    metric_value: Decimal | None
    threshold_value: Decimal | None
    details: str


class FeatureSampleReaderProtocol(Protocol):
    def live_samples(self, feature_name: str, *, window_days: int) -> pd.Series: ...


class SignalSampleReaderProtocol(Protocol):
    def live_samples(self, sleeve_id: str, *, window_days: int) -> pd.Series: ...


class ReplayRecordsReaderProtocol(Protocol):
    def recent_records(
        self,
        *,
        window_days: int,
    ) -> tuple[ReplaySlippageRecord, ...]: ...


class AttributionRecordsReaderProtocol(Protocol):
    def records_for_sleeve(
        self,
        sleeve_id: str,
        *,
        window_days: int,
    ) -> tuple[SleeveDailyAttributionRecord, ...]: ...

    def has_gap_for_sleeve(self, sleeve_id: str, *, window_days: int) -> bool: ...


class BacktestReferenceReturnsReaderProtocol(Protocol):
    def returns_for_sleeve(self, sleeve_id: str) -> tuple[Decimal, ...]: ...


class RiskControlEventSinkProtocol(Protocol):
    def write_risk_control_event(self, event: RiskControlEvent) -> object: ...


class OperatorAlertGatewayProtocol(Protocol):
    def publish(self, alert: OperatorAlert) -> None: ...


class DriftMonitorVerdictSinkProtocol(Protocol):
    def write_drift_monitor_verdict_record(
        self,
        record: DriftMonitorVerdictRecord,
    ) -> object: ...


class MarketDataHistoryProtocol(Protocol):
    def get_daily_bar_history(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
    ) -> Any: ...


class MarketDataFeatureSampleReader:
    def __init__(
        self,
        *,
        market_data_gateway: MarketDataHistoryProtocol,
        treasury_cache_path: Path | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._market_data = market_data_gateway
        self._treasury_cache_path = treasury_cache_path
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def live_samples(self, feature_name: str, *, window_days: int) -> pd.Series:
        if feature_name == "vix_level":
            return pd.Series([], dtype=float)

        end_utc = self._now_provider()
        start_utc = end_utc - timedelta(days=max(window_days + 260, 400))
        spy_bars = self._market_data.get_daily_bar_history(
            "SPY",
            start_utc=start_utc,
            end_utc=end_utc,
        )
        closes = spy_bars["close"].astype(float)

        if feature_name == "spy_close_over_sma_200":
            sma_200 = closes.rolling(200, min_periods=1).mean()
            return (closes / sma_200).dropna().tail(window_days)

        if feature_name == "yield_curve_spread_bps":
            if (
                self._treasury_cache_path is None
                or not self._treasury_cache_path.exists()
            ):
                return pd.Series([], dtype=float)
            frame = load_treasury_yield_cache(self._treasury_cache_path)
            return frame["spread_2s10s_bps"].astype(float).tail(window_days)

        if feature_name == "trend_signal_strength":
            return (
                generate_trend_signal(spy_bars).astype(float).dropna().tail(window_days)
            )

        if feature_name == "vol_forecast_ewma":
            returns = closes.pct_change()
            return (
                forecast_volatility(
                    returns,
                    lookback_days=20,
                    forecast_method="ewma",
                )
                .astype(float)
                .dropna()
                .tail(window_days)
            )

        raise LookupError(feature_name)


class MarketDataSignalSampleReader:
    def __init__(
        self,
        *,
        market_data_gateway: MarketDataHistoryProtocol,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._market_data = market_data_gateway
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def live_samples(self, sleeve_id: str, *, window_days: int) -> pd.Series:
        candidate = _candidate_for_sleeve(sleeve_id)
        if candidate is None or candidate.sleeve_class_path is None:
            raise LookupError(sleeve_id)
        end_utc = self._now_provider()
        start_utc = end_utc - timedelta(days=max(window_days + 260, 400))
        symbol = candidate.benchmark_symbol
        bars = self._market_data.get_daily_bar_history(
            symbol,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        if sleeve_id == "trend-following-v1":
            return (
                generate_trend_signal(
                    bars,
                    lookback_days=int(
                        candidate.parameter_set.get("lookback_days", 252)
                    ),
                    sma_window_days=int(
                        candidate.parameter_set.get("sma_window_days", 200)
                    ),
                    skip_recent_days=int(
                        candidate.parameter_set.get("skip_recent_days", 1)
                    ),
                )
                .astype(float)
                .dropna()
                .tail(window_days)
            )
        if sleeve_id == "vol-target-v1":
            return (
                generate_vol_target_spy_signal(
                    bars,
                    target_volatility=float(
                        candidate.parameter_set.get(
                            "target_volatility",
                            Decimal("0.12"),
                        )
                    ),
                    realized_vol_window_days=int(
                        candidate.parameter_set.get("realized_vol_window_days", 60)
                    ),
                    max_gross_leverage=float(
                        candidate.parameter_set.get(
                            "max_gross_leverage", Decimal("1.0")
                        )
                    ),
                    forecast_method=str(
                        candidate.parameter_set.get("forecast_method", "garch")
                    ),
                )
                .astype(float)
                .dropna()
                .tail(window_days)
            )
        raise LookupError(sleeve_id)


class StoreBackedReplayRecordsReader:
    def __init__(
        self,
        *,
        validation_store: FilesystemArtifactStore,
    ) -> None:
        self._store = validation_store

    def recent_records(self, *, window_days: int) -> tuple[ReplaySlippageRecord, ...]:
        window_start = datetime.now(UTC) - timedelta(days=window_days)
        payloads = self._store.list_artifact_payloads("replay_slippage_records")
        records: list[ReplaySlippageRecord] = []
        for payload in payloads:
            record = ReplaySlippageRecord(
                replay_id=str(payload["replay_id"]),
                execution_id=str(payload["execution_id"]),
                intent_id=str(payload["intent_id"]),
                symbol=str(payload["symbol"]),
                side=str(payload["side"]),
                filled_qty=Decimal(str(payload["filled_qty"])),
                reference_price=Decimal(str(payload["reference_price"])),
                paper_fill_price=Decimal(str(payload["paper_fill_price"])),
                paper_slippage_bps=Decimal(str(payload["paper_slippage_bps"])),
                simulated_fill_price=Decimal(str(payload["simulated_fill_price"])),
                simulated_slippage_bps=Decimal(str(payload["simulated_slippage_bps"])),
                divergence_ratio=Decimal(str(payload["divergence_ratio"])),
                quoted_spread_bps=Decimal(str(payload["quoted_spread_bps"])),
                participation_rate=Decimal(str(payload["participation_rate"])),
                generated_at_utc=datetime.fromisoformat(
                    str(payload["generated_at_utc"])
                ),
            )
            if record.generated_at_utc >= window_start:
                records.append(record)
        return tuple(records)


class StoreBackedAttributionRecordsReader:
    def __init__(
        self,
        *,
        operator_store: FilesystemArtifactStore,
    ) -> None:
        self._store = operator_store

    def records_for_sleeve(
        self,
        sleeve_id: str,
        *,
        window_days: int,
    ) -> tuple[SleeveDailyAttributionRecord, ...]:
        records = self._store.list_sleeve_daily_attribution_records(sleeve_id=sleeve_id)
        window_start = (datetime.now(UTC) - timedelta(days=window_days)).date()
        return tuple(
            record
            for record in records
            if date.fromisoformat(record.trading_day) >= window_start
        )

    def has_gap_for_sleeve(self, sleeve_id: str, *, window_days: int) -> bool:
        window_start = (datetime.now(UTC) - timedelta(days=window_days)).date()
        return any(
            date.fromisoformat(record.trading_day) >= window_start
            for record in self._store.list_sleeve_attribution_gap_records(
                sleeve_id=sleeve_id
            )
        )


class ArtifactBacktestReferenceReturnsReader:
    def __init__(self, *, artifact_root: Path) -> None:
        self._artifact_root = artifact_root

    def returns_for_sleeve(self, sleeve_id: str) -> tuple[Decimal, ...]:
        return load_backtest_reference_returns(
            artifact_root=self._artifact_root,
            sleeve_id=sleeve_id,
        )


class DriftAlarmGateway:
    def __init__(
        self,
        *,
        blueprint: DriftMonitorBlueprint,
        reference_snapshot: ReferenceDistributionSnapshot,
        feature_sample_reader: FeatureSampleReaderProtocol,
        signal_sample_reader: SignalSampleReaderProtocol,
        replay_records_reader: ReplayRecordsReaderProtocol,
        attribution_records_reader: AttributionRecordsReaderProtocol,
        backtest_reference_returns_reader: BacktestReferenceReturnsReaderProtocol,
        risk_control_event_sink: RiskControlEventSinkProtocol,
        alert_gateway: OperatorAlertGatewayProtocol,
        verdict_sink: DriftMonitorVerdictSinkProtocol | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._blueprint = blueprint
        self._reference_snapshot = reference_snapshot
        self._feature_reader = feature_sample_reader
        self._signal_reader = signal_sample_reader
        self._replay_reader = replay_records_reader
        self._attribution_reader = attribution_records_reader
        self._backtest_reference_reader = backtest_reference_returns_reader
        self._risk_sink = risk_control_event_sink
        self._alert_gateway = alert_gateway
        self._verdict_sink = verdict_sink
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._latest_verdicts: tuple[DriftMonitorVerdict, ...] = ()

    def has_alarm(self, *, sleeve_id: str) -> bool:
        for verdict in self._latest_verdicts:
            if verdict.severity != "critical":
                continue
            if verdict.sleeve_id is None or verdict.sleeve_id == sleeve_id:
                return True
        return False

    def refresh(self) -> tuple[DriftMonitorVerdict, ...]:
        recorded_at_utc = self._now_provider().astimezone(UTC)
        verdicts = (
            *self._psi_verdicts(),
            *self._ks_verdicts(),
            *self._execution_verdicts(),
            *self._pnl_verdicts(),
        )
        for verdict in verdicts:
            self._risk_sink.write_risk_control_event(self._to_risk_event(verdict))
            if verdict.severity in {"warning", "critical"}:
                self._alert_gateway.publish(self._to_alert(verdict))
            if self._verdict_sink is not None:
                self._verdict_sink.write_drift_monitor_verdict_record(
                    build_drift_monitor_verdict_record(
                        verdict=verdict,
                        recorded_at_utc=recorded_at_utc,
                    )
                )
        self._latest_verdicts = tuple(verdicts)
        return self._latest_verdicts

    def latest_verdicts(self) -> tuple[DriftMonitorVerdict, ...]:
        return self._latest_verdicts

    def _psi_verdicts(self) -> tuple[DriftMonitorVerdict, ...]:
        distributions = {
            distribution.feature_name: distribution
            for distribution in self._reference_snapshot.feature_distributions
        }
        verdicts: list[DriftMonitorVerdict] = []
        for feature_name in self._blueprint.feature_monitor_names:
            reference = distributions.get(feature_name)
            if reference is None:
                verdicts.append(
                    _pending_verdict(
                        monitor_id=f"psi::{feature_name}",
                        sleeve_id=None,
                        details="no reference distribution",
                    )
                )
                continue
            try:
                live_samples = self._feature_reader.live_samples(
                    feature_name,
                    window_days=self._blueprint.minimum_live_days_for_alarm,
                )
            except LookupError:
                verdicts.append(
                    _pending_verdict(
                        monitor_id=f"psi::{feature_name}",
                        sleeve_id=None,
                        details="feature reader cannot compute requested feature",
                    )
                )
                continue
            if len(live_samples) < self._blueprint.minimum_live_days_for_alarm:
                verdicts.append(
                    _pending_verdict(
                        monitor_id=f"psi::{feature_name}",
                        sleeve_id=None,
                        details=(
                            f"insufficient live samples: {len(live_samples)}"
                            f" < {self._blueprint.minimum_live_days_for_alarm}"
                        ),
                    )
                )
                continue
            psi_value = compute_population_stability_index(
                reference_distribution=reference,
                live_samples=live_samples,
            )
            if psi_value >= self._blueprint.thresholds.psi_critical:
                severity = "critical"
            elif psi_value >= self._blueprint.thresholds.psi_warning:
                severity = "warning"
            else:
                severity = "info"
            verdicts.append(
                DriftMonitorVerdict(
                    monitor_id=f"psi::{feature_name}",
                    sleeve_id=None,
                    severity=severity,
                    metric_value=psi_value,
                    threshold_value=self._blueprint.thresholds.psi_critical,
                    details=f"PSI={psi_value}",
                )
            )
        return tuple(verdicts)

    def _ks_verdicts(self) -> tuple[DriftMonitorVerdict, ...]:
        distributions = {
            distribution.sleeve_id: distribution
            for distribution in self._reference_snapshot.signal_distributions
        }
        verdicts: list[DriftMonitorVerdict] = []
        for sleeve_id in self._blueprint.signal_monitor_sleeve_ids:
            reference = distributions.get(sleeve_id)
            if reference is None:
                verdicts.append(
                    _pending_verdict(
                        monitor_id=f"ks::{sleeve_id}",
                        sleeve_id=sleeve_id,
                        details="no reference distribution",
                    )
                )
                continue
            try:
                live_samples = self._signal_reader.live_samples(
                    sleeve_id,
                    window_days=self._blueprint.minimum_live_days_for_alarm,
                )
            except LookupError:
                verdicts.append(
                    _pending_verdict(
                        monitor_id=f"ks::{sleeve_id}",
                        sleeve_id=sleeve_id,
                        details=(
                            "sleeve not in mandatory registry or sleeve_class_path=None"
                        ),
                    )
                )
                continue
            if len(live_samples) < self._blueprint.minimum_live_days_for_alarm:
                verdicts.append(
                    _pending_verdict(
                        monitor_id=f"ks::{sleeve_id}",
                        sleeve_id=sleeve_id,
                        details=f"insufficient live samples: {len(live_samples)}",
                    )
                )
                continue
            ks_result = compute_kolmogorov_smirnov(
                reference_samples=reference.observed_samples,
                live_samples=live_samples,
            )
            severity = (
                "critical"
                if ks_result.p_value < self._blueprint.thresholds.ks_p_value_critical
                else "info"
            )
            verdicts.append(
                DriftMonitorVerdict(
                    monitor_id=f"ks::{sleeve_id}",
                    sleeve_id=sleeve_id,
                    severity=severity,
                    metric_value=ks_result.p_value,
                    threshold_value=self._blueprint.thresholds.ks_p_value_critical,
                    details=f"KS stat={ks_result.statistic} p={ks_result.p_value}",
                )
            )
        return tuple(verdicts)

    def _execution_verdicts(self) -> tuple[DriftMonitorVerdict, ...]:
        records = self._replay_reader.recent_records(
            window_days=self._blueprint.execution_drift_rolling_window_days,
        )
        if not records:
            return (
                _pending_verdict(
                    monitor_id="execution::portfolio",
                    sleeve_id=None,
                    details="no replay records in window",
                ),
            )
        ratio = compute_execution_drift_ratio(
            replay_records=records,
            rolling_window_days=self._blueprint.execution_drift_rolling_window_days,
        )
        if ratio >= self._blueprint.thresholds.execution_drift_critical:
            severity = "critical"
        elif ratio >= self._blueprint.thresholds.execution_drift_warning:
            severity = "warning"
        else:
            severity = "info"
        return (
            DriftMonitorVerdict(
                monitor_id="execution::portfolio",
                sleeve_id=None,
                severity=severity,
                metric_value=ratio,
                threshold_value=self._blueprint.thresholds.execution_drift_critical,
                details=f"mean |divergence_ratio|={ratio}",
            ),
        )

    def _pnl_verdicts(self) -> tuple[DriftMonitorVerdict, ...]:
        verdicts: list[DriftMonitorVerdict] = []
        has_gap_for_sleeve = getattr(
            self._attribution_reader,
            "has_gap_for_sleeve",
            lambda sleeve_id, *, window_days: False,
        )
        for sleeve_id in self._blueprint.signal_monitor_sleeve_ids:
            has_gap = has_gap_for_sleeve(
                sleeve_id,
                window_days=self._blueprint.pnl_divergence_rolling_window_days,
            )
            verdict = compute_live_vs_backtest_pnl_divergence(
                sleeve_id=sleeve_id,
                live_attribution_records=self._attribution_reader.records_for_sleeve(
                    sleeve_id,
                    window_days=self._blueprint.pnl_divergence_rolling_window_days,
                ),
                backtest_returns_series=self._backtest_reference_reader.returns_for_sleeve(
                    sleeve_id
                ),
                thresholds=self._blueprint.thresholds,
                rolling_window_days=self._blueprint.pnl_divergence_rolling_window_days,
                minimum_live_days=self._blueprint.minimum_live_days_for_alarm,
                has_gap=has_gap,
            )
            verdicts.append(
                DriftMonitorVerdict(
                    monitor_id=f"pnl::{sleeve_id}",
                    sleeve_id=sleeve_id,
                    severity=verdict.severity,
                    metric_value=verdict.absolute_delta,
                    threshold_value=self._blueprint.thresholds.pnl_absolute_critical,
                    details=(
                        f"abs_delta={verdict.absolute_delta} "
                        f"sharpe_delta_ratio={verdict.sharpe_delta_ratio}"
                    ),
                )
            )
        return tuple(verdicts)

    def _to_risk_event(self, verdict: DriftMonitorVerdict) -> RiskControlEvent:
        return RiskControlEvent(
            event_id=f"drift-{uuid.uuid4()}",
            intent_id=None,
            severity="info" if verdict.severity == "pending" else verdict.severity,
            control_type=DRIFT_ALARM_CONTROL_TYPE,
            blocked=False,
            recorded_at_utc=datetime.now(UTC),
            operator_visible=verdict.severity in {"warning", "critical"},
        )

    def _to_alert(self, verdict: DriftMonitorVerdict) -> OperatorAlert:
        return OperatorAlert(
            alert_id=f"drift-alert-{uuid.uuid4()}",
            severity=verdict.severity,
            category=DRIFT_ALARM_CONTROL_TYPE,
            summary=(
                f"{verdict.monitor_id} {verdict.severity.upper()}: {verdict.details}"
            ),
            evidence_refs=(),
            delivery_targets=("operator_dashboard",),
            sent_at_utc=datetime.now(UTC),
        )


class ArtifactBackedDriftAlarmStateReader:
    def __init__(self, *, store: FilesystemArtifactStore) -> None:
        self._store = store

    def has_alarm(self, *, sleeve_id: str) -> bool:
        records = self._store.list_drift_monitor_verdict_records()
        if not records:
            return False
        latest_recorded_at = max(record.recorded_at_utc for record in records)
        latest_batch = tuple(
            record for record in records if record.recorded_at_utc == latest_recorded_at
        )
        return any(
            record.severity == "critical" and record.sleeve_id == sleeve_id
            for record in latest_batch
        )


def build_drift_monitor_verdict_record(
    *,
    verdict: DriftMonitorVerdict,
    recorded_at_utc: datetime,
) -> DriftMonitorVerdictRecord:
    return DriftMonitorVerdictRecord(
        verdict_id=f"drift-verdict-{uuid.uuid4()}",
        monitor_id=verdict.monitor_id,
        sleeve_id=verdict.sleeve_id,
        severity=verdict.severity,
        metric_value=verdict.metric_value,
        threshold_value=verdict.threshold_value,
        details=verdict.details,
        recorded_at_utc=recorded_at_utc.astimezone(UTC),
    )


def _candidate_for_sleeve(sleeve_id: str) -> StrategyCandidate | None:
    for candidate in build_mandatory_candidate_registry():
        if candidate.candidate_id == sleeve_id:
            return candidate
    return None


def _pending_verdict(
    *,
    monitor_id: str,
    sleeve_id: str | None,
    details: str,
) -> DriftMonitorVerdict:
    return DriftMonitorVerdict(
        monitor_id=monitor_id,
        sleeve_id=sleeve_id,
        severity="pending",
        metric_value=None,
        threshold_value=None,
        details=details,
    )


__all__ = (
    "ArtifactBackedDriftAlarmStateReader",
    "ArtifactBacktestReferenceReturnsReader",
    "AttributionRecordsReaderProtocol",
    "BacktestReferenceReturnsReaderProtocol",
    "build_drift_monitor_verdict_record",
    "DRIFT_ALARM_CONTROL_TYPE",
    "DriftAlarmGateway",
    "DriftMonitorVerdict",
    "FeatureSampleReaderProtocol",
    "MarketDataFeatureSampleReader",
    "MarketDataHistoryProtocol",
    "MarketDataSignalSampleReader",
    "OperatorAlertGatewayProtocol",
    "ReplayRecordsReaderProtocol",
    "RiskControlEventSinkProtocol",
    "SignalSampleReaderProtocol",
    "StoreBackedAttributionRecordsReader",
    "StoreBackedReplayRecordsReader",
)
