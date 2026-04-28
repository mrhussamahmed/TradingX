from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from tradingx.drift.blueprint import DriftMonitorBlueprint
from tradingx.drift.gateway import (
    DRIFT_ALARM_CONTROL_TYPE,
    ArtifactBackedDriftAlarmStateReader,
    DriftAlarmGateway,
    MarketDataFeatureSampleReader,
)
from tradingx.drift.reference import (
    FeatureDistribution,
    ReferenceDistributionSnapshot,
    SignalDistribution,
)
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    DriftMonitorVerdictRecord,
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
    def __init__(
        self,
        records: tuple[SleeveDailyAttributionRecord, ...],
        *,
        gap_sleeve_ids: frozenset[str] = frozenset(),
        activation_blocker: str | None = None,
    ) -> None:
        self._records = records
        self._gap_sleeve_ids = gap_sleeve_ids
        self._activation_blocker = activation_blocker

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

    def has_gap_for_sleeve(self, sleeve_id: str, *, window_days: int) -> bool:
        del window_days
        return sleeve_id in self._gap_sleeve_ids

    def pnl_activation_blocker(self, *, window_days: int) -> str | None:
        del window_days
        return self._activation_blocker


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


class _MarketDataHistory:
    def __init__(self, bars: pd.DataFrame) -> None:
        self._bars = bars

    def get_daily_bar_history(self, symbol: str, *, start_utc, end_utc):
        del symbol, start_utc, end_utc
        return self._bars


def _daily_record(
    *,
    sleeve_id: str,
    trading_day: date,
    daily_return: str = "0.01",
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
        daily_return=Decimal(daily_return),
        per_symbol_open_weight=(("SPY", Decimal("1")),),
        per_symbol_close_weight=(("SPY", Decimal("1")),),
    )


def _rolling_records(
    sleeve_id: str,
    *,
    days: int = 35,
) -> tuple[SleeveDailyAttributionRecord, ...]:
    start = date(2026, 3, 1)
    return tuple(
        _daily_record(
            sleeve_id=sleeve_id,
            trading_day=start + timedelta(days=offset),
        )
        for offset in range(days)
    )


def test_market_data_feature_reader_spy_sma_uses_200_prior_observations() -> None:
    index = pd.date_range("2025-01-02", periods=201, freq="B", tz="UTC")
    closes = [float(100 + index_value) for index_value in range(201)]
    bars = pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1_000_000.0] * len(closes),
        },
        index=index,
    )
    reader = MarketDataFeatureSampleReader(
        market_data_gateway=_MarketDataHistory(bars),
        now_provider=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )

    samples = reader.live_samples("spy_close_over_sma_200", window_days=10)

    assert samples.index.tolist() == [index[200]]
    assert samples.iloc[0] == closes[200] / (sum(closes[:200]) / 200)


def test_market_data_feature_reader_returns_vix_level_when_vixcls_cache_exists(
    tmp_path,
) -> None:
    index = pd.date_range("2026-04-20", periods=5, freq="B", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": [100.0] * len(index),
            "high": [100.0] * len(index),
            "low": [100.0] * len(index),
            "close": [100.0] * len(index),
            "volume": [1_000_000.0] * len(index),
        },
        index=index,
    )
    vix_path = tmp_path / "vix_daily.csv"
    pd.DataFrame(
        {
            "date": ["2026-04-20", "2026-04-21", "2026-04-22"],
            "vix_close": [25.5, 26.5, 27.5],
        }
    ).to_csv(vix_path, index=False)
    reader = MarketDataFeatureSampleReader(
        market_data_gateway=_MarketDataHistory(bars),
        vix_cache_path=vix_path,
        now_provider=lambda: datetime(2026, 4, 24, tzinfo=UTC),
    )

    samples = reader.live_samples("vix_level", window_days=2)

    assert samples.tolist() == [26.5, 27.5]


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


def test_artifact_backed_alarm_reader_uses_latest_persisted_verdict_batch(
    base_snapshot,
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
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
        alert_gateway=_AlertGateway(),
        verdict_sink=store,
        now_provider=lambda: datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
    )

    gateway.refresh()

    reader = ArtifactBackedDriftAlarmStateReader(store=store)
    assert reader.has_alarm(sleeve_id="trend-following-v1") is True
    assert reader.has_alarm(sleeve_id="vol-target-v1") is False

    # A later all-info batch clears the previously persisted critical signal.
    info_gateway = DriftAlarmGateway(
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
        verdict_sink=store,
        now_provider=lambda: datetime(2026, 4, 24, 20, 0, tzinfo=UTC),
    )
    info_gateway.refresh()

    assert reader.has_alarm(sleeve_id="trend-following-v1") is False


def test_artifact_backed_alarm_reader_ignores_portfolio_level_critical_verdicts(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    store.write_drift_monitor_verdict_record(
        DriftMonitorVerdictRecord(
            verdict_id="verdict-1",
            monitor_id="psi::spy_close_over_sma_200",
            sleeve_id=None,
            severity="critical",
            metric_value=Decimal("0.41"),
            threshold_value=Decimal("0.35"),
            details="psi critical",
            recorded_at_utc=datetime(2026, 4, 25, 20, 0, tzinfo=UTC),
        )
    )

    reader = ArtifactBackedDriftAlarmStateReader(store=store)

    assert reader.has_alarm(sleeve_id="trend-following-v1") is False
    assert reader.has_alarm(sleeve_id="vol-target-v1") is False


def test_artifact_backed_alarm_reader_reports_latest_batch_severity_by_sleeve(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    recorded_at = datetime(2026, 4, 25, 20, 0, tzinfo=UTC)
    store.write_drift_monitor_verdict_record(
        DriftMonitorVerdictRecord(
            verdict_id="verdict-1",
            monitor_id="ks::trend-following-v1",
            sleeve_id="trend-following-v1",
            severity="info",
            metric_value=Decimal("0.5"),
            threshold_value=Decimal("0.05"),
            details="healthy",
            recorded_at_utc=recorded_at,
        )
    )
    store.write_drift_monitor_verdict_record(
        DriftMonitorVerdictRecord(
            verdict_id="verdict-2",
            monitor_id="pnl::trend-following-v1",
            sleeve_id="trend-following-v1",
            severity="pending",
            metric_value=None,
            threshold_value=None,
            details="blocked",
            recorded_at_utc=recorded_at,
        )
    )
    store.write_drift_monitor_verdict_record(
        DriftMonitorVerdictRecord(
            verdict_id="verdict-3",
            monitor_id="pnl::vol-target-v1",
            sleeve_id="vol-target-v1",
            severity="warning",
            metric_value=Decimal("0.03"),
            threshold_value=Decimal("0.02"),
            details="warning",
            recorded_at_utc=recorded_at,
        )
    )

    reader = ArtifactBackedDriftAlarmStateReader(store=store)

    assert reader.latest_severity_by_sleeve() == {
        "trend-following-v1": "pending",
        "vol-target-v1": "warning",
    }


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


def test_pnl_verdicts_are_active_for_both_sleeves_when_window_is_clean(
    base_snapshot,
) -> None:
    records = _rolling_records("trend-following-v1") + _rolling_records("vol-target-v1")
    backtest_returns = tuple(Decimal("0.01") for _ in range(35))
    gateway = DriftAlarmGateway(
        blueprint=DriftMonitorBlueprint(blueprint_id="bp"),
        reference_snapshot=base_snapshot,
        feature_sample_reader=_FeatureReader(samples={}),
        signal_sample_reader=_SignalReader(samples={}),
        replay_records_reader=_ReplayReader(records=()),
        attribution_records_reader=_AttributionReader(records=records),
        backtest_reference_returns_reader=_ReferenceReturnsReader(
            returns={
                "trend-following-v1": backtest_returns,
                "vol-target-v1": backtest_returns,
            }
        ),
        risk_control_event_sink=_RiskEventSink(),
        alert_gateway=_AlertGateway(),
    )

    verdicts = {
        verdict.monitor_id: verdict
        for verdict in gateway.refresh()
        if verdict.monitor_id.startswith("pnl::")
    }

    assert verdicts["pnl::trend-following-v1"].severity == "info"
    assert verdicts["pnl::vol-target-v1"].severity == "info"


def test_pnl_verdicts_stay_pending_for_both_sleeves_when_activation_blocked(
    base_snapshot,
) -> None:
    records = _rolling_records("trend-following-v1") + _rolling_records("vol-target-v1")
    backtest_returns = tuple(Decimal("0.01") for _ in range(35))
    gateway = DriftAlarmGateway(
        blueprint=DriftMonitorBlueprint(blueprint_id="bp"),
        reference_snapshot=base_snapshot,
        feature_sample_reader=_FeatureReader(samples={}),
        signal_sample_reader=_SignalReader(samples={}),
        replay_records_reader=_ReplayReader(records=()),
        attribution_records_reader=_AttributionReader(
            records=records,
            activation_blocker=(
                "pending: reserve cash above activation threshold on " "2026-04-22"
            ),
        ),
        backtest_reference_returns_reader=_ReferenceReturnsReader(
            returns={
                "trend-following-v1": backtest_returns,
                "vol-target-v1": backtest_returns,
            }
        ),
        risk_control_event_sink=_RiskEventSink(),
        alert_gateway=_AlertGateway(),
    )

    pnl_verdicts = tuple(
        verdict
        for verdict in gateway.refresh()
        if verdict.monitor_id.startswith("pnl::")
    )

    assert len(pnl_verdicts) == 2
    assert all(verdict.severity == "pending" for verdict in pnl_verdicts)
    assert all(
        "reserve cash above activation threshold" in verdict.details
        for verdict in pnl_verdicts
    )
