"""Live drift monitoring package."""

from __future__ import annotations

from tradingx.drift.attribution import (
    ActivationGatewayProtocol,
    AttributionStoreProtocol,
    SleeveAttributionRecorder,
    build_sleeve_daily_attribution_record,
)
from tradingx.drift.backtest_reference import (
    artifact_path as backtest_reference_artifact_path,
)
from tradingx.drift.backtest_reference import (
    load_backtest_reference_returns,
    write_backtest_reference_returns,
)
from tradingx.drift.blueprint import DriftMonitorBlueprint, DriftThresholds
from tradingx.drift.execution import compute_execution_drift_ratio
from tradingx.drift.gateway import (
    DRIFT_ALARM_CONTROL_TYPE,
    DriftAlarmGateway,
    DriftMonitorVerdict,
    FeatureSampleReaderProtocol,
    SignalSampleReaderProtocol,
)
from tradingx.drift.ks import KSResult, compute_kolmogorov_smirnov
from tradingx.drift.live_returns_source import SleeveDailyReturnsReader
from tradingx.drift.pnl_divergence import (
    PnlDivergenceVerdict,
    compute_live_vs_backtest_pnl_divergence,
)
from tradingx.drift.psi import compute_population_stability_index
from tradingx.drift.reference import (
    FeatureDistribution,
    ReferenceDistributionSnapshot,
    SignalDistribution,
    build_reference_distribution_snapshot,
    load_reference_distribution_snapshot,
    write_reference_distribution_snapshot,
)

__all__ = (
    "ActivationGatewayProtocol",
    "AttributionStoreProtocol",
    "DRIFT_ALARM_CONTROL_TYPE",
    "DriftAlarmGateway",
    "DriftMonitorBlueprint",
    "DriftMonitorVerdict",
    "DriftThresholds",
    "FeatureDistribution",
    "FeatureSampleReaderProtocol",
    "KSResult",
    "PnlDivergenceVerdict",
    "ReferenceDistributionSnapshot",
    "SignalDistribution",
    "SignalSampleReaderProtocol",
    "SleeveAttributionRecorder",
    "SleeveDailyReturnsReader",
    "backtest_reference_artifact_path",
    "build_reference_distribution_snapshot",
    "build_sleeve_daily_attribution_record",
    "compute_execution_drift_ratio",
    "compute_kolmogorov_smirnov",
    "compute_live_vs_backtest_pnl_divergence",
    "compute_population_stability_index",
    "load_backtest_reference_returns",
    "load_reference_distribution_snapshot",
    "write_backtest_reference_returns",
    "write_reference_distribution_snapshot",
)
