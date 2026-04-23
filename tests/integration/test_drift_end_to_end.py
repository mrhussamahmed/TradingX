from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pandas as pd

from tradingx.drift.blueprint import DriftMonitorBlueprint
from tradingx.drift.gateway import DRIFT_ALARM_CONTROL_TYPE, DriftAlarmGateway
from tradingx.drift.reference import build_reference_distribution_snapshot
from tradingx.types import OperatorAlert, RiskControlEvent, SleeveDailyAttributionRecord


def _daily_attribution_record(
    *,
    sleeve_id: str,
    trading_day: date,
) -> SleeveDailyAttributionRecord:
    return SleeveDailyAttributionRecord(
        attribution_id=f"{sleeve_id}__{trading_day.isoformat()}",
        sleeve_id=sleeve_id,
        trading_day=trading_day.isoformat(),
        recorded_at_utc=datetime.combine(
            trading_day,
            datetime.min.time(),
            tzinfo=UTC,
        )
        + timedelta(hours=20),
        starting_equity=Decimal("100"),
        ending_equity=Decimal("101"),
        daily_return=Decimal("0.01"),
        per_symbol_open_weight=(("SPY", Decimal("1")),),
        per_symbol_close_weight=(("SPY", Decimal("1")),),
    )


def test_drift_alarm_gateway_end_to_end_produces_expected_verdicts() -> None:
    snapshot = build_reference_distribution_snapshot(
        reference_snapshot_id="ref-it",
        blueprint_id="bp-it",
        feature_samples_by_name={
            "spy_close_over_sma_200": pd.Series([index / 1000 for index in range(1000)])
        },
        signal_samples_by_sleeve_id={
            "trend-following-v1": pd.Series([value / 100 for value in range(100)]),
            "vol-target-v1": pd.Series([value / 100 for value in range(100)]),
        },
        reference_window_start_utc=datetime(2023, 1, 1, tzinfo=UTC),
        reference_window_end_utc=datetime(2024, 1, 1, tzinfo=UTC),
        generated_at_utc=datetime(2024, 1, 1, tzinfo=UTC),
    )

    class _FeatureReader:
        def live_samples(self, feature_name, *, window_days):
            del feature_name, window_days
            return pd.Series([0.55] * 2000)

    class _SignalReader:
        def live_samples(self, sleeve_id, *, window_days):
            del window_days
            if sleeve_id == "trend-following-v1":
                return pd.Series([value / 100 for value in range(100)])
            return pd.Series([5.0] * 100)

    class _ReplayReader:
        def recent_records(self, *, window_days):
            del window_days
            return ()

    class _AttributionReader:
        def records_for_sleeve(self, sleeve_id, *, window_days):
            del window_days
            start = date(2026, 3, 1)
            return tuple(
                _daily_attribution_record(
                    sleeve_id=sleeve_id,
                    trading_day=start + timedelta(days=offset),
                )
                for offset in range(35)
            )

        def has_gap_for_sleeve(self, sleeve_id, *, window_days):
            del sleeve_id, window_days
            return False

    class _ReferenceReturnsReader:
        def returns_for_sleeve(self, sleeve_id):
            del sleeve_id
            return tuple(Decimal("0.01") for _ in range(35))

    risk_events: list[RiskControlEvent] = []
    alerts: list[OperatorAlert] = []

    class _Sink:
        def write_risk_control_event(self, event):
            risk_events.append(event)
            return event

    class _Alerts:
        def publish(self, alert):
            alerts.append(alert)

    gateway = DriftAlarmGateway(
        blueprint=DriftMonitorBlueprint(blueprint_id="bp-it"),
        reference_snapshot=snapshot,
        feature_sample_reader=_FeatureReader(),
        signal_sample_reader=_SignalReader(),
        replay_records_reader=_ReplayReader(),
        attribution_records_reader=_AttributionReader(),
        backtest_reference_returns_reader=_ReferenceReturnsReader(),
        risk_control_event_sink=_Sink(),
        alert_gateway=_Alerts(),
    )
    verdicts = gateway.refresh()

    psi_verdicts = tuple(
        verdict for verdict in verdicts if verdict.monitor_id.startswith("psi::")
    )
    assert any(verdict.severity == "critical" for verdict in psi_verdicts)
    assert (
        next(
            verdict
            for verdict in verdicts
            if verdict.monitor_id == "ks::trend-following-v1"
        ).severity
        == "info"
    )
    assert (
        next(
            verdict for verdict in verdicts if verdict.monitor_id == "ks::vol-target-v1"
        ).severity
        == "critical"
    )
    assert (
        next(
            verdict
            for verdict in verdicts
            if verdict.monitor_id == "pnl::trend-following-v1"
        ).severity
        == "info"
    )
    assert (
        next(
            verdict
            for verdict in verdicts
            if verdict.monitor_id == "pnl::vol-target-v1"
        ).severity
        == "info"
    )
    assert gateway.has_alarm(sleeve_id="trend-following-v1") is True
    assert gateway.has_alarm(sleeve_id="vol-target-v1") is True
    assert len(risk_events) == len(verdicts)
    assert all(event.control_type == DRIFT_ALARM_CONTROL_TYPE for event in risk_events)
    assert all(
        alert.severity in {"warning", "critical"}
        and alert.category == DRIFT_ALARM_CONTROL_TYPE
        for alert in alerts
    )
