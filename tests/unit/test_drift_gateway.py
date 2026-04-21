from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import pytest

from tradingx.drift.blueprint import DriftMonitorBlueprint
from tradingx.drift.gateway import (
    DRIFT_ALARM_CONTROL_TYPE,
    DriftAlarmGateway,
)
from tradingx.drift.reference import (
    FeatureDistribution,
    ReferenceDistributionSnapshot,
    SignalDistribution,
)
from tradingx.types import (
    OperatorAlert,
    ReplaySlippageRecord,
    RiskControlEvent,
    SleeveDailyAttributionRecord,
)


def _uniform_feature_distribution(name: str) -> FeatureDistribution:
    return FeatureDistribution(
        feature_name=name,
        bin_edges=tuple(Decimal(str(index / 10)) for index in range(11)),
        bin_proportions=tuple(Decimal("0.1") for _ in range(10)),
        observation_count=1000,
    )


def _signal_distribution(sleeve_id: str) -> SignalDistribution:
    return SignalDistribution(
        sleeve_id=sleeve_id,
        observed_samples=tuple(Decimal(str(value / 100)) for value in range(100)),
        observation_count=100,
    )


@pytest.fixture
def base_snapshot() -> ReferenceDistributionSnapshot:
    return ReferenceDistributionSnapshot(
        reference_snapshot_id="ref-1",
        generated_at_utc=datetime(2024, 1, 1, tzinfo=UTC),
        blueprint_id="bp",
        feature_distributions=(
            _uniform_feature_distribution("spy_close_over_sma_200"),
        ),
        signal_distributions=(
            _signal_distribution("trend-following-v1"),
            _signal_distribution("vol-target-v1"),
        ),
        reference_window_start_utc=datetime(2023, 1, 1, tzinfo=UTC),
        reference_window_end_utc=datetime(2024, 1, 1, tzinfo=UTC),
    )


class _FeatureReader:
    def __init__(self, samples: dict[str, pd.Series]) -> None:
        self._samples = samples

    def live_samples(self, feature_name: str, *, window_days: int) -> pd.Series:
        del window_days
        return self._samples.get(feature_name, pd.Series([], dtype=float))


class _SignalReader:
    def __init__(self, samples: dict[str, pd.Series]) -> None:
        self._samples = samples

    def live_samples(self, sleeve_id: str, *, window_days: int) -> pd.Series:
        del window_days
        if sleeve_id not in self._samples:
            raise LookupError(sleeve_id)
        return self._samples[sleeve_id]


class _ReplayReader:
    def __init__(self, records: tuple[ReplaySlippageRecord, ...]) -> None:
        self._records = records

    def recent_records(self, *, window_days: int) -> tuple[ReplaySlippageRecord, ...]:
        del window_days
        return self._records


class _AttributionReader:
    def __init__(self, records: tuple[SleeveDailyAttributionRecord, ...]) -> None:
        self._records = records

    def records_for_sleeve(
        self,
        sleeve_id: str,
        *,
        window_days: int,
    ) -> tuple[SleeveDailyAttributionRecord, ...]:
        del window_days
        return tuple(
            record for record in self._records if record.sleeve_id == sleeve_id
        )


class _ReferenceReturnsReader:
    def __init__(self, returns: dict[str, tuple[Decimal, ...]]) -> None:
        self._returns = returns

    def returns_for_sleeve(self, sleeve_id: str) -> tuple[Decimal, ...]:
        return self._returns.get(sleeve_id, ())


class _RiskEventSink:
    def __init__(self) -> None:
        self.events: list[RiskControlEvent] = []

    def write_risk_control_event(self, event: RiskControlEvent) -> object:
        self.events.append(event)
        return event


class _AlertGateway:
    def __init__(self) -> None:
        self.alerts: list[OperatorAlert] = []

    def publish(self, alert: OperatorAlert) -> None:
        self.alerts.append(alert)


def test_has_alarm_false_when_all_monitors_info(base_snapshot) -> None:
    gateway = DriftAlarmGateway(
        blueprint=DriftMonitorBlueprint(blueprint_id="bp"),
        reference_snapshot=base_snapshot,
        feature_sample_reader=_FeatureReader(
            {
                "spy_close_over_sma_200": pd.Series(
                    [index / 1000 for index in range(1000)]
                ),
            }
        ),
        signal_sample_reader=_SignalReader(
            {
                "trend-following-v1": pd.Series([value / 100 for value in range(100)]),
                "vol-target-v1": pd.Series([value / 100 for value in range(100)]),
            }
        ),
        replay_records_reader=_ReplayReader(records=()),
        attribution_records_reader=_AttributionReader(records=()),
        backtest_reference_returns_reader=_ReferenceReturnsReader(returns={}),
        risk_control_event_sink=_RiskEventSink(),
        alert_gateway=_AlertGateway(),
    )
    verdicts = gateway.refresh()
    assert all(verdict.severity in {"info", "pending"} for verdict in verdicts)
    assert gateway.has_alarm(sleeve_id="trend-following-v1") is False
    assert gateway.has_alarm(sleeve_id="vol-target-v1") is False


def test_has_alarm_true_on_critical_ks_only_for_affected_sleeve(base_snapshot) -> None:
    alerts = _AlertGateway()
    gateway = DriftAlarmGateway(
        blueprint=DriftMonitorBlueprint(blueprint_id="bp"),
        reference_snapshot=base_snapshot,
        feature_sample_reader=_FeatureReader(
            {
                "spy_close_over_sma_200": pd.Series(
                    [index / 1000 for index in range(1000)]
                ),
            }
        ),
        signal_sample_reader=_SignalReader(
            {
                "trend-following-v1": pd.Series([5.0] * 100),
                "vol-target-v1": pd.Series([value / 100 for value in range(100)]),
            }
        ),
        replay_records_reader=_ReplayReader(records=()),
        attribution_records_reader=_AttributionReader(records=()),
        backtest_reference_returns_reader=_ReferenceReturnsReader(returns={}),
        risk_control_event_sink=_RiskEventSink(),
        alert_gateway=alerts,
    )
    gateway.refresh()
    assert gateway.has_alarm(sleeve_id="trend-following-v1") is True
    assert gateway.has_alarm(sleeve_id="vol-target-v1") is False
    assert len(alerts.alerts) == 1
    assert alerts.alerts[0].category == DRIFT_ALARM_CONTROL_TYPE


def test_refresh_emits_one_risk_control_event_per_verdict(base_snapshot) -> None:
    risk_sink = _RiskEventSink()
    gateway = DriftAlarmGateway(
        blueprint=DriftMonitorBlueprint(
            blueprint_id="bp",
            feature_monitor_names=("spy_close_over_sma_200",),
            signal_monitor_sleeve_ids=("trend-following-v1", "vol-target-v1"),
        ),
        reference_snapshot=base_snapshot,
        feature_sample_reader=_FeatureReader(samples={}),
        signal_sample_reader=_SignalReader(samples={}),
        replay_records_reader=_ReplayReader(records=()),
        attribution_records_reader=_AttributionReader(records=()),
        backtest_reference_returns_reader=_ReferenceReturnsReader(returns={}),
        risk_control_event_sink=risk_sink,
        alert_gateway=_AlertGateway(),
    )
    verdicts = gateway.refresh()
    assert len(risk_sink.events) == len(verdicts)
    assert all(
        event.control_type == DRIFT_ALARM_CONTROL_TYPE for event in risk_sink.events
    )


def test_ks_sleeve_without_registry_candidate_records_pending(base_snapshot) -> None:
    class _FailingSignalReader:
        def live_samples(self, sleeve_id: str, *, window_days: int):
            del window_days
            raise LookupError(sleeve_id)

    gateway = DriftAlarmGateway(
        blueprint=DriftMonitorBlueprint(
            blueprint_id="bp",
            signal_monitor_sleeve_ids=("trend-following-v1",),
        ),
        reference_snapshot=base_snapshot,
        feature_sample_reader=_FeatureReader(samples={}),
        signal_sample_reader=_FailingSignalReader(),
        replay_records_reader=_ReplayReader(records=()),
        attribution_records_reader=_AttributionReader(records=()),
        backtest_reference_returns_reader=_ReferenceReturnsReader(returns={}),
        risk_control_event_sink=_RiskEventSink(),
        alert_gateway=_AlertGateway(),
    )
    verdicts = gateway.refresh()
    ks_verdicts = tuple(
        verdict for verdict in verdicts if verdict.monitor_id.startswith("ks::")
    )
    assert len(ks_verdicts) == 1
    assert ks_verdicts[0].severity == "pending"
