# Tranche 1.5 Live Drift Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute [DESIGN-0016](../specs/2026-04-21-tranche-1-5-live-drift-monitoring-design.md) — wire the live drift diagnostics that close BRIEF-0002 v1.2.0's narrowed criterion 5: PSI on features, KS on signal outputs, execution-quality drift, and P&L divergence for the currently-active sleeve-backed strategy. Turn the `DriftAlarmGatewayProtocol` stub shipped in 1.4 into a concrete gateway backed by four monitors, add the active-sleeve attribution record, and replace the `RollingWindowSource.LIVE_DAILY_RETURNS` `NotImplementedError` guardrail with a real reader.

**Architecture:** New `src/tradingx/drift/` package containing blueprint, reference-distribution snapshot, four monitor computations, attribution, P&L divergence, concrete gateway, and live-daily-returns source. No changes to `TradeIntent` / `ExecutionLifecycleRecord` / `ClosedTradeRecord` contracts — attribution derives from portfolio-state equity snapshots. Features and signals are **recomputed** from persisted bars at monitor-refresh time; no new live-observation streams. Backtest-reference returns live under `{config.runtime.artifact_root}/drift/backtest_reference_returns/<sleeve_id>.json` (runtime tree, not `config/strategy/*`).

**Tech Stack:** Python 3.11, `Decimal` at module boundaries, `pandas` for bar windows + feature/signal series, `scipy.stats.ks_2samp` for KS, `pytest` for tests, existing `uv run` invocations. No new runtime dependencies.

---

## Scope

Implements DESIGN-0016 §W1–§W10 in this order:

1. **W1** — `DriftMonitorBlueprint` + `DriftThresholds` (config).
2. **W2** — `ReferenceDistributionSnapshot` + build/load/write helpers.
3. **W3** — `compute_population_stability_index`.
4. **W4** — `compute_kolmogorov_smirnov`.
5. **W5** — `compute_execution_drift_ratio`.
6. **W6** — `SleeveDailyAttributionRecord` + `SleeveAttributionRecorder` (active-sleeve only).
7. **W7** — `compute_live_vs_backtest_pnl_divergence` + backtest-reference artifact writer.
8. **W8** — `DriftAlarmGateway` concrete implementation + reader protocols.
9. **W9** — `RollingWindowSource.LIVE_DAILY_RETURNS` reader + live-Sharpe gate: replaces the 1.4 `NotImplementedError`, branches `_should_trigger_sharpe_gate` on source, and computes annualized Lo-adjusted Sharpe (same definition as TRIAL_SUMMARY) on the live series to gate against `three_month_sharpe_floor`.
10. **W10** — `recalibrate_drift_reference` operator action + automation hook + closing pass (GATES-0001 1.2.0 → 1.2.1, INDEX bump).

Gate 1 pass/fail outcomes remain unchanged; drift monitoring is paper-evidence, not a gate criterion.

## File structure

### New files

- `src/tradingx/drift/__init__.py`
- `src/tradingx/drift/blueprint.py` — `DriftMonitorBlueprint`, `DriftThresholds`
- `src/tradingx/drift/reference.py` — `ReferenceDistributionSnapshot`, `FeatureDistribution`, `SignalDistribution`, build/load/write
- `src/tradingx/drift/psi.py` — `compute_population_stability_index`
- `src/tradingx/drift/ks.py` — `KSResult`, `compute_kolmogorov_smirnov`
- `src/tradingx/drift/execution.py` — `compute_execution_drift_ratio`
- `src/tradingx/drift/attribution.py` — `SleeveAttributionRecorder`, `build_sleeve_daily_attribution_record`
- `src/tradingx/drift/pnl_divergence.py` — `PnlDivergenceVerdict`, `compute_live_vs_backtest_pnl_divergence`
- `src/tradingx/drift/gateway.py` — `DriftAlarmGateway`, `DriftMonitorVerdict`, reader protocols, `DRIFT_ALARM_CONTROL_TYPE`
- `src/tradingx/drift/live_returns_source.py` — `SleeveDailyReturnsReader` for the `LIVE_DAILY_RETURNS` path
- `src/tradingx/drift/backtest_reference.py` — backtest-reference returns read/write (runtime-tree path)
- `tests/unit/test_drift_blueprint.py`
- `tests/unit/test_drift_reference_snapshot.py`
- `tests/unit/test_drift_psi.py`
- `tests/unit/test_drift_ks.py`
- `tests/unit/test_drift_execution.py`
- `tests/unit/test_drift_attribution.py`
- `tests/unit/test_drift_pnl_divergence.py`
- `tests/unit/test_drift_gateway.py`
- `tests/unit/test_drift_live_returns_source.py`
- `tests/unit/test_drift_backtest_reference.py`
- `tests/integration/test_drift_end_to_end.py`

### Modified files

- `src/tradingx/types.py` — add `SleeveDailyAttributionRecord`.
- `src/tradingx/persistence.py` — add `write_sleeve_daily_attribution_record` + `list_sleeve_daily_attribution_records` on `FilesystemArtifactStore`; add writer/reader for the backtest-reference artifact.
- `src/tradingx/portfolio/sleeve_runtime.py` — replace the `NotImplementedError` in the `LIVE_DAILY_RETURNS` branch; add `LiveDailyReturnsSourceProtocol` and optional `live_daily_returns_source` constructor parameter; branch `_should_trigger_sharpe_gate` on `rolling_window_source` and add `_should_trigger_sharpe_gate_via_live_returns` that computes annualized Lo-adjusted Sharpe on the live series via `tradingx.stats.lo_adjusted_sharpe_ratio` (same definition the TRIAL_SUMMARY path consumes) and compares to `three_month_sharpe_floor`.
- `src/tradingx/operator_control.py` — add `recalibrate_drift_reference(snapshot_id)` action.
- `src/tradingx/automation.py` — add `portfolio_gateway`, `drift_alarm_gateway`, and `attribution_recorder` constructor parameters (all defaulting to `None`); capture `_session_open_portfolio_state` in the preopen step; invoke `SleeveAttributionRecorder.record_session` + `DriftAlarmGateway.refresh()` at the session-close step.
- `docs/validation/acceptance_gates.md` — add note to Gate 3 primary evidence that `ExecutionQualityDriftMonitor` surfaces slippage-drift alarms on the dashboard; patch bump 1.2.0 → 1.2.1.
- `docs/INDEX.md` — bump GATES-0001 row + INDEX version.
- `tests/unit/test_types.py` — assertions on `SleeveDailyAttributionRecord`.
- `tests/unit/test_sleeve_runtime_controller.py` — regression: `LIVE_DAILY_RETURNS` path with an injected source computes annualized Lo-adjusted Sharpe and gates on the floor (above-floor → no fire; below-floor → fire with `SLEEVE_SHARPE_BELOW_THRESHOLD_6M`; zero-variance → pending; insufficient → pending; source=None → `ValueError`).
- `tests/unit/test_operator_control.py` — `recalibrate_drift_reference` action regression.
- `tests/unit/test_automation.py` — automation wiring regression.

### Untouched (intentional)

- `src/tradingx/replay_slippage.py` — per-execution slippage comparison unchanged; `drift/execution.py` aggregates over its output.
- `src/tradingx/validation.py` — Gate 1 / Gate 2 unchanged; drift is paper-evidence, not gate criteria.
- `src/tradingx/runtime_host.py` — hard-halt path unchanged; drift alarms do not trigger runtime transitions in 1.5.
- `src/tradingx/portfolio_construction.py` and `src/tradingx/portfolio/construction.py` — unchanged.

---

## W1 — `DriftMonitorBlueprint` + `DriftThresholds`

### Task 1: Blueprint + thresholds + package init

**Files:**
- Create: `src/tradingx/drift/__init__.py`
- Create: `src/tradingx/drift/blueprint.py`
- Create: `tests/unit/test_drift_blueprint.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_drift_blueprint.py`:

```python
from __future__ import annotations

from decimal import Decimal

import pytest

from tradingx.drift.blueprint import DriftMonitorBlueprint, DriftThresholds


def test_defaults_match_design_0016():
    thresholds = DriftThresholds()
    assert thresholds.psi_warning == Decimal("0.10")
    assert thresholds.psi_critical == Decimal("0.25")
    assert thresholds.ks_p_value_critical == Decimal("0.05")
    assert thresholds.execution_drift_warning == Decimal("1.5")
    assert thresholds.execution_drift_critical == Decimal("2.0")
    assert thresholds.pnl_absolute_warning == Decimal("0.02")
    assert thresholds.pnl_absolute_critical == Decimal("0.04")
    assert thresholds.pnl_sharpe_warning == Decimal("0.30")
    assert thresholds.pnl_sharpe_critical == Decimal("0.50")


def test_blueprint_accepts_empty_feature_monitor_names():
    bp = DriftMonitorBlueprint(
        blueprint_id="bp-empty",
        feature_monitor_names=(),
    )
    assert bp.feature_monitor_names == ()


def test_blueprint_accepts_empty_signal_monitor_sleeve_ids():
    bp = DriftMonitorBlueprint(
        blueprint_id="bp-empty",
        signal_monitor_sleeve_ids=(),
    )
    assert bp.signal_monitor_sleeve_ids == ()


def test_blueprint_rejects_zero_rolling_window():
    with pytest.raises(ValueError, match="rolling_window_days"):
        DriftMonitorBlueprint(
            blueprint_id="bp",
            execution_drift_rolling_window_days=0,
        )


def test_blueprint_rejects_zero_pnl_window():
    with pytest.raises(ValueError, match="rolling_window_days"):
        DriftMonitorBlueprint(
            blueprint_id="bp",
            pnl_divergence_rolling_window_days=0,
        )


def test_blueprint_rejects_zero_minimum_live_days():
    with pytest.raises(ValueError, match="minimum_live_days"):
        DriftMonitorBlueprint(
            blueprint_id="bp",
            minimum_live_days_for_alarm=0,
        )


def test_blueprint_is_frozen():
    import dataclasses

    bp = DriftMonitorBlueprint(blueprint_id="bp")
    with pytest.raises(dataclasses.FrozenInstanceError):
        bp.blueprint_id = "bp-2"  # type: ignore[misc]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_drift_blueprint.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'tradingx.drift'`.

- [ ] **Step 3: Implement**

Create `src/tradingx/drift/__init__.py`:

```python
"""Live drift monitoring package.

Implements DESIGN-0016: PSI on features, KS on signal outputs,
execution-quality drift, and active-sleeve P&L divergence.
"""

from __future__ import annotations
```

Create `src/tradingx/drift/blueprint.py`:

```python
"""Drift-monitor blueprint + threshold configuration per DESIGN-0016 W1."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class DriftThresholds:
    psi_warning: Decimal = Decimal("0.10")
    psi_critical: Decimal = Decimal("0.25")
    ks_p_value_critical: Decimal = Decimal("0.05")
    execution_drift_warning: Decimal = Decimal("1.5")
    execution_drift_critical: Decimal = Decimal("2.0")
    pnl_absolute_warning: Decimal = Decimal("0.02")
    pnl_absolute_critical: Decimal = Decimal("0.04")
    pnl_sharpe_warning: Decimal = Decimal("0.30")
    pnl_sharpe_critical: Decimal = Decimal("0.50")


@dataclass(frozen=True)
class DriftMonitorBlueprint:
    blueprint_id: str
    thresholds: DriftThresholds = field(default_factory=DriftThresholds)
    feature_monitor_names: tuple[str, ...] = (
        "spy_close_over_sma_200",
        "vix_level",
        "yield_curve_spread_bps",
        "trend_signal_strength",
        "vol_forecast_ewma",
    )
    signal_monitor_sleeve_ids: tuple[str, ...] = (
        "trend-following-v1",
        "vol-target-v1",
    )
    execution_drift_rolling_window_days: int = 30
    pnl_divergence_rolling_window_days: int = 60
    minimum_live_days_for_alarm: int = 30

    def __post_init__(self) -> None:
        if self.execution_drift_rolling_window_days <= 0:
            raise ValueError(
                "execution_drift_rolling_window_days must be > 0"
            )
        if self.pnl_divergence_rolling_window_days <= 0:
            raise ValueError(
                "pnl_divergence_rolling_window_days must be > 0"
            )
        if self.minimum_live_days_for_alarm <= 0:
            raise ValueError(
                "minimum_live_days_for_alarm must be > 0"
            )


__all__ = ("DriftMonitorBlueprint", "DriftThresholds")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_drift_blueprint.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/drift/__init__.py src/tradingx/drift/blueprint.py tests/unit/test_drift_blueprint.py
git commit -m "feat(drift): add DriftMonitorBlueprint and DriftThresholds"
```

---

## W2 — Reference-distribution snapshot

### Task 2: `FeatureDistribution`, `SignalDistribution`, `ReferenceDistributionSnapshot` + build/load/write

**Files:**
- Create: `src/tradingx/drift/reference.py`
- Create: `tests/unit/test_drift_reference_snapshot.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_drift_reference_snapshot.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from tradingx.drift.reference import (
    FeatureDistribution,
    ReferenceDistributionSnapshot,
    SignalDistribution,
    build_reference_distribution_snapshot,
    load_reference_distribution_snapshot,
    write_reference_distribution_snapshot,
)


def test_feature_distribution_bin_proportions_sum_to_one():
    fd = FeatureDistribution(
        feature_name="foo",
        bin_edges=(Decimal("0"), Decimal("0.5"), Decimal("1.0")),
        bin_proportions=(Decimal("0.4"), Decimal("0.6")),
        observation_count=100,
    )
    total = sum(fd.bin_proportions, Decimal("0"))
    assert total == Decimal("1.0")


def test_build_snapshot_produces_deterministic_bins_for_canned_samples():
    feature_samples = {
        "foo": pd.Series([float(i) / 100.0 for i in range(100)]),
    }
    signal_samples = {
        "trend-following-v1": pd.Series([-1.0] * 50 + [1.0] * 50),
    }
    snapshot = build_reference_distribution_snapshot(
        reference_snapshot_id="ref-1",
        blueprint_id="bp",
        feature_samples_by_name=feature_samples,
        signal_samples_by_sleeve_id=signal_samples,
        reference_window_start_utc=datetime(2024, 1, 1, tzinfo=UTC),
        reference_window_end_utc=datetime(2025, 1, 1, tzinfo=UTC),
        n_bins=10,
    )
    assert snapshot.reference_snapshot_id == "ref-1"
    assert len(snapshot.feature_distributions) == 1
    feature = snapshot.feature_distributions[0]
    assert feature.feature_name == "foo"
    assert len(feature.bin_edges) == 11  # n_bins + 1
    assert len(feature.bin_proportions) == 10
    total = sum(feature.bin_proportions, Decimal("0"))
    assert abs(total - Decimal("1.0")) < Decimal("0.0001")
    assert feature.observation_count == 100


def test_build_signal_distribution_preserves_raw_samples():
    signal_samples = {
        "sleeve-x": pd.Series([1.0, 2.0, 3.0]),
    }
    snapshot = build_reference_distribution_snapshot(
        reference_snapshot_id="ref-sig",
        blueprint_id="bp",
        feature_samples_by_name={},
        signal_samples_by_sleeve_id=signal_samples,
        reference_window_start_utc=datetime(2024, 1, 1, tzinfo=UTC),
        reference_window_end_utc=datetime(2025, 1, 1, tzinfo=UTC),
    )
    signal = snapshot.signal_distributions[0]
    assert signal.sleeve_id == "sleeve-x"
    assert signal.observation_count == 3
    assert signal.observed_samples == (
        Decimal("1.0"),
        Decimal("2.0"),
        Decimal("3.0"),
    )


def test_snapshot_roundtrip(tmp_path: Path):
    snapshot = build_reference_distribution_snapshot(
        reference_snapshot_id="ref-rt",
        blueprint_id="bp-rt",
        feature_samples_by_name={"foo": pd.Series([1.0, 2.0, 3.0, 4.0])},
        signal_samples_by_sleeve_id={"sleeve": pd.Series([0.1, 0.2])},
        reference_window_start_utc=datetime(2024, 1, 1, tzinfo=UTC),
        reference_window_end_utc=datetime(2024, 6, 1, tzinfo=UTC),
        n_bins=4,
    )
    path = tmp_path / "ref.json"
    write_reference_distribution_snapshot(path, snapshot)
    loaded = load_reference_distribution_snapshot(path)
    assert loaded == snapshot


def test_load_missing_snapshot_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_reference_distribution_snapshot(tmp_path / "missing.json")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_drift_reference_snapshot.py -v`

Expected: FAIL on `ImportError` for the module.

- [ ] **Step 3: Implement**

Create `src/tradingx/drift/reference.py`:

```python
"""Reference-distribution snapshot for drift monitoring per DESIGN-0016 W2."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd  # type: ignore[import-untyped]


@dataclass(frozen=True)
class FeatureDistribution:
    feature_name: str
    bin_edges: tuple[Decimal, ...]
    bin_proportions: tuple[Decimal, ...]
    observation_count: int


@dataclass(frozen=True)
class SignalDistribution:
    sleeve_id: str
    observed_samples: tuple[Decimal, ...]
    observation_count: int


@dataclass(frozen=True)
class ReferenceDistributionSnapshot:
    reference_snapshot_id: str
    generated_at_utc: datetime
    blueprint_id: str
    feature_distributions: tuple[FeatureDistribution, ...]
    signal_distributions: tuple[SignalDistribution, ...]
    reference_window_start_utc: datetime
    reference_window_end_utc: datetime


def build_reference_distribution_snapshot(
    *,
    reference_snapshot_id: str,
    blueprint_id: str,
    feature_samples_by_name: dict[str, pd.Series],
    signal_samples_by_sleeve_id: dict[str, pd.Series],
    reference_window_start_utc: datetime,
    reference_window_end_utc: datetime,
    n_bins: int = 10,
) -> ReferenceDistributionSnapshot:
    feature_distributions = tuple(
        _build_feature_distribution(name, samples, n_bins=n_bins)
        for name, samples in feature_samples_by_name.items()
    )
    signal_distributions = tuple(
        _build_signal_distribution(sleeve_id, samples)
        for sleeve_id, samples in signal_samples_by_sleeve_id.items()
    )
    return ReferenceDistributionSnapshot(
        reference_snapshot_id=reference_snapshot_id,
        generated_at_utc=datetime.now(UTC),
        blueprint_id=blueprint_id,
        feature_distributions=feature_distributions,
        signal_distributions=signal_distributions,
        reference_window_start_utc=reference_window_start_utc,
        reference_window_end_utc=reference_window_end_utc,
    )


def write_reference_distribution_snapshot(
    path: Path,
    snapshot: ReferenceDistributionSnapshot,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "reference_snapshot_id": snapshot.reference_snapshot_id,
        "generated_at_utc": snapshot.generated_at_utc.astimezone(UTC).isoformat(),
        "blueprint_id": snapshot.blueprint_id,
        "reference_window_start_utc": snapshot.reference_window_start_utc.astimezone(UTC).isoformat(),
        "reference_window_end_utc": snapshot.reference_window_end_utc.astimezone(UTC).isoformat(),
        "feature_distributions": [
            {
                "feature_name": fd.feature_name,
                "bin_edges": [str(edge) for edge in fd.bin_edges],
                "bin_proportions": [str(p) for p in fd.bin_proportions],
                "observation_count": fd.observation_count,
            }
            for fd in snapshot.feature_distributions
        ],
        "signal_distributions": [
            {
                "sleeve_id": sd.sleeve_id,
                "observed_samples": [str(s) for s in sd.observed_samples],
                "observation_count": sd.observation_count,
            }
            for sd in snapshot.signal_distributions
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_reference_distribution_snapshot(
    path: Path,
) -> ReferenceDistributionSnapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ReferenceDistributionSnapshot(
        reference_snapshot_id=str(payload["reference_snapshot_id"]),
        generated_at_utc=_parse_iso(payload["generated_at_utc"]),
        blueprint_id=str(payload["blueprint_id"]),
        feature_distributions=tuple(
            FeatureDistribution(
                feature_name=str(fd["feature_name"]),
                bin_edges=tuple(Decimal(str(edge)) for edge in fd["bin_edges"]),
                bin_proportions=tuple(
                    Decimal(str(p)) for p in fd["bin_proportions"]
                ),
                observation_count=int(fd["observation_count"]),
            )
            for fd in payload["feature_distributions"]
        ),
        signal_distributions=tuple(
            SignalDistribution(
                sleeve_id=str(sd["sleeve_id"]),
                observed_samples=tuple(
                    Decimal(str(s)) for s in sd["observed_samples"]
                ),
                observation_count=int(sd["observation_count"]),
            )
            for sd in payload["signal_distributions"]
        ),
        reference_window_start_utc=_parse_iso(payload["reference_window_start_utc"]),
        reference_window_end_utc=_parse_iso(payload["reference_window_end_utc"]),
    )


def _build_feature_distribution(
    feature_name: str,
    samples: pd.Series,
    *,
    n_bins: int,
) -> FeatureDistribution:
    values = np.asarray(samples.astype(float))
    quantile_levels = np.linspace(0.0, 1.0, n_bins + 1)
    bin_edges_np = np.quantile(values, quantile_levels)
    bin_edges = tuple(Decimal(str(float(edge))) for edge in bin_edges_np)
    # Compute proportions with the usual boundary convention (last bin
    # includes its right edge).
    hist, _ = np.histogram(values, bins=bin_edges_np)
    total = hist.sum()
    if total == 0:
        proportions = tuple(Decimal("0") for _ in range(n_bins))
    else:
        proportions = tuple(
            Decimal(str(float(count) / float(total))) for count in hist
        )
    return FeatureDistribution(
        feature_name=feature_name,
        bin_edges=bin_edges,
        bin_proportions=proportions,
        observation_count=int(len(values)),
    )


def _build_signal_distribution(
    sleeve_id: str,
    samples: pd.Series,
) -> SignalDistribution:
    return SignalDistribution(
        sleeve_id=sleeve_id,
        observed_samples=tuple(
            Decimal(str(float(v))) for v in samples.tolist()
        ),
        observation_count=int(len(samples)),
    )


def _parse_iso(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


__all__ = (
    "FeatureDistribution",
    "ReferenceDistributionSnapshot",
    "SignalDistribution",
    "build_reference_distribution_snapshot",
    "load_reference_distribution_snapshot",
    "write_reference_distribution_snapshot",
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_drift_reference_snapshot.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/drift/reference.py tests/unit/test_drift_reference_snapshot.py
git commit -m "feat(drift): add ReferenceDistributionSnapshot with build/load/write"
```

---

## W3 — PSI computation

### Task 3: `compute_population_stability_index`

**Files:**
- Create: `src/tradingx/drift/psi.py`
- Create: `tests/unit/test_drift_psi.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_drift_psi.py`:

```python
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from tradingx.drift.psi import compute_population_stability_index
from tradingx.drift.reference import FeatureDistribution


def _uniform_ref(n_bins: int = 10) -> FeatureDistribution:
    edges = tuple(
        Decimal(str(i / n_bins)) for i in range(n_bins + 1)
    )
    props = tuple(Decimal("1") / Decimal(n_bins) for _ in range(n_bins))
    return FeatureDistribution(
        feature_name="foo",
        bin_edges=edges,
        bin_proportions=props,
        observation_count=1000,
    )


def test_psi_zero_for_matching_distribution():
    ref = _uniform_ref()
    rng = np.random.default_rng(seed=0)
    live = pd.Series(rng.uniform(0.0, 1.0, size=10_000))
    psi = compute_population_stability_index(
        reference_distribution=ref,
        live_samples=live,
    )
    assert abs(psi) < Decimal("0.05")


def test_psi_breaches_critical_threshold_for_significant_shift():
    ref = _uniform_ref()
    # Live distribution concentrates in the first decile.
    live = pd.Series([0.05] * 9_000 + [0.5] * 1_000)
    psi = compute_population_stability_index(
        reference_distribution=ref,
        live_samples=live,
    )
    assert psi > Decimal("0.25")


def test_psi_empty_live_samples_raises():
    ref = _uniform_ref()
    with pytest.raises(ValueError, match="live_samples"):
        compute_population_stability_index(
            reference_distribution=ref,
            live_samples=pd.Series([], dtype=float),
        )


def test_psi_clips_samples_outside_reference_range():
    ref = _uniform_ref()
    # Samples spread way outside [0, 1]; PSI is defined (no log(0)).
    live = pd.Series(np.concatenate([
        np.linspace(-10.0, -1.0, 500),
        np.linspace(0.0, 1.0, 500),
        np.linspace(2.0, 10.0, 500),
    ]))
    psi = compute_population_stability_index(
        reference_distribution=ref,
        live_samples=live,
    )
    assert psi >= Decimal("0")
    # No exception; psi is a finite Decimal.
    assert psi.is_finite()


def test_psi_handles_zero_proportion_live_bins_via_epsilon():
    ref = _uniform_ref()
    # Live samples concentrate in only one bin; other bins would
    # be 0 → log(0 / 0.1) without epsilon. Epsilon prevents the
    # NaN; PSI is still finite.
    live = pd.Series([0.55] * 1000)
    psi = compute_population_stability_index(
        reference_distribution=ref,
        live_samples=live,
        epsilon=1e-6,
    )
    assert psi.is_finite()
    assert psi > Decimal("0")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_drift_psi.py -v`

Expected: FAIL on `ImportError`.

- [ ] **Step 3: Implement**

Create `src/tradingx/drift/psi.py`:

```python
"""Population Stability Index per DESIGN-0016 W3."""

from __future__ import annotations

import math
from decimal import Decimal

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from tradingx.drift.reference import FeatureDistribution


def compute_population_stability_index(
    *,
    reference_distribution: FeatureDistribution,
    live_samples: pd.Series,
    epsilon: float = 1e-6,
) -> Decimal:
    if len(live_samples) == 0:
        raise ValueError("live_samples must not be empty")

    edges = [float(edge) for edge in reference_distribution.bin_edges]
    # Widen outer edges by +/- inf so live samples outside the
    # reference range fall into the nearest bin (clip semantics).
    edges_with_inf = [-math.inf] + edges[1:-1] + [math.inf]
    live_values = np.asarray(live_samples.astype(float))
    live_hist, _ = np.histogram(live_values, bins=edges_with_inf)
    total = live_hist.sum()
    if total == 0:
        return Decimal("0")
    live_props = live_hist.astype(float) / float(total)
    ref_props = np.asarray(
        [float(p) for p in reference_distribution.bin_proportions],
        dtype=float,
    )
    # Clamp both at epsilon to avoid log(0).
    live_clamped = np.maximum(live_props, epsilon)
    ref_clamped = np.maximum(ref_props, epsilon)
    psi_value = float(
        np.sum(
            (live_clamped - ref_clamped)
            * np.log(live_clamped / ref_clamped)
        )
    )
    return Decimal(str(psi_value))


__all__ = ("compute_population_stability_index",)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_drift_psi.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/drift/psi.py tests/unit/test_drift_psi.py
git commit -m "feat(drift): add compute_population_stability_index"
```

---

## W4 — KS computation

### Task 4: `compute_kolmogorov_smirnov`

**Files:**
- Create: `src/tradingx/drift/ks.py`
- Create: `tests/unit/test_drift_ks.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_drift_ks.py`:

```python
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from tradingx.drift.ks import KSResult, compute_kolmogorov_smirnov


def _samples(*values: float) -> tuple[Decimal, ...]:
    return tuple(Decimal(str(v)) for v in values)


def test_identical_distributions_p_value_near_one():
    rng = np.random.default_rng(seed=0)
    shared = rng.normal(size=1_000).tolist()
    result = compute_kolmogorov_smirnov(
        reference_samples=tuple(Decimal(str(v)) for v in shared),
        live_samples=pd.Series(shared),
    )
    assert isinstance(result, KSResult)
    assert result.p_value > Decimal("0.9")
    assert result.statistic <= Decimal("0.1")


def test_shifted_distributions_p_value_below_critical():
    rng = np.random.default_rng(seed=1)
    reference = rng.normal(size=1_000).tolist()
    live = (rng.normal(size=1_000) + 1.0).tolist()  # mean shift
    result = compute_kolmogorov_smirnov(
        reference_samples=tuple(Decimal(str(v)) for v in reference),
        live_samples=pd.Series(live),
    )
    assert result.p_value < Decimal("0.05")


def test_empty_live_samples_raises():
    with pytest.raises(ValueError, match="live_samples"):
        compute_kolmogorov_smirnov(
            reference_samples=_samples(1.0, 2.0, 3.0),
            live_samples=pd.Series([], dtype=float),
        )


def test_empty_reference_samples_raises():
    with pytest.raises(ValueError, match="reference_samples"):
        compute_kolmogorov_smirnov(
            reference_samples=(),
            live_samples=pd.Series([1.0, 2.0]),
        )


def test_statistic_and_p_value_bounded():
    rng = np.random.default_rng(seed=2)
    reference = rng.normal(size=200).tolist()
    live = rng.normal(loc=0.5, size=200).tolist()
    result = compute_kolmogorov_smirnov(
        reference_samples=tuple(Decimal(str(v)) for v in reference),
        live_samples=pd.Series(live),
    )
    assert Decimal("0") <= result.statistic <= Decimal("1")
    assert Decimal("0") <= result.p_value <= Decimal("1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_drift_ks.py -v`

Expected: FAIL on `ImportError`.

- [ ] **Step 3: Implement**

Create `src/tradingx/drift/ks.py`:

```python
"""Two-sample Kolmogorov–Smirnov test per DESIGN-0016 W4."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]
from scipy import stats  # type: ignore[import-untyped]


@dataclass(frozen=True)
class KSResult:
    statistic: Decimal
    p_value: Decimal


def compute_kolmogorov_smirnov(
    *,
    reference_samples: tuple[Decimal, ...],
    live_samples: pd.Series,
) -> KSResult:
    if not reference_samples:
        raise ValueError("reference_samples must not be empty")
    if len(live_samples) == 0:
        raise ValueError("live_samples must not be empty")
    reference_array = [float(v) for v in reference_samples]
    live_array = [float(v) for v in live_samples.astype(float)]
    ks = stats.ks_2samp(reference_array, live_array)
    return KSResult(
        statistic=Decimal(str(float(ks.statistic))),
        p_value=Decimal(str(float(ks.pvalue))),
    )


__all__ = ("KSResult", "compute_kolmogorov_smirnov")
```

**Note on `scipy`.** The project already has `scipy` available
transitively via `empyrical-reloaded`. If mypy / ruff flags the
import, add the `scipy` requirement explicitly in
`pyproject.toml` in the same commit.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_drift_ks.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/drift/ks.py tests/unit/test_drift_ks.py
git commit -m "feat(drift): add compute_kolmogorov_smirnov over scipy.stats.ks_2samp"
```

---

## W5 — Execution-quality drift

### Task 5: `compute_execution_drift_ratio`

**Files:**
- Create: `src/tradingx/drift/execution.py`
- Create: `tests/unit/test_drift_execution.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_drift_execution.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tradingx.drift.execution import compute_execution_drift_ratio
from tradingx.types import ReplaySlippageRecord


def _record(
    *,
    symbol: str = "SPY",
    divergence_ratio: str = "1.0",
    days_ago: int = 1,
) -> ReplaySlippageRecord:
    now = datetime.now(UTC) - timedelta(days=days_ago)
    return ReplaySlippageRecord(
        replay_id=f"replay-{days_ago}",
        execution_id=f"exec-{days_ago}",
        intent_id=f"intent-{days_ago}",
        symbol=symbol,
        side="buy",
        filled_qty=Decimal("1"),
        reference_price=Decimal("100"),
        paper_fill_price=Decimal("100.1"),
        paper_slippage_bps=Decimal("10"),
        simulated_fill_price=Decimal("100.05"),
        simulated_slippage_bps=Decimal("5"),
        divergence_ratio=Decimal(divergence_ratio),
        quoted_spread_bps=Decimal("4"),
        participation_rate=Decimal("0.01"),
        generated_at_utc=now,
    )


def test_empty_records_returns_zero():
    result = compute_execution_drift_ratio(replay_records=())
    assert result == Decimal("0")


def test_mean_abs_divergence_ratio():
    records = (
        _record(divergence_ratio="1.5", days_ago=1),
        _record(divergence_ratio="-2.0", days_ago=2),
        _record(divergence_ratio="1.0", days_ago=3),
    )
    result = compute_execution_drift_ratio(replay_records=records)
    # mean(|1.5|, |2.0|, |1.0|) = 4.5 / 3 = 1.5
    assert result == Decimal("1.5")


def test_rolling_window_filter_excludes_stale_records():
    records = (
        _record(divergence_ratio="1.5", days_ago=1),
        _record(divergence_ratio="2.0", days_ago=100),  # outside 30d window
    )
    result = compute_execution_drift_ratio(
        replay_records=records,
        rolling_window_days=30,
    )
    # Only the recent record contributes.
    assert result == Decimal("1.5")


def test_symbol_filter_narrows():
    records = (
        _record(symbol="SPY", divergence_ratio="1.5", days_ago=1),
        _record(symbol="QQQ", divergence_ratio="3.0", days_ago=2),
    )
    result = compute_execution_drift_ratio(
        replay_records=records,
        symbol="SPY",
    )
    assert result == Decimal("1.5")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_drift_execution.py -v`

Expected: FAIL on `ImportError`.

- [ ] **Step 3: Implement**

Create `src/tradingx/drift/execution.py`:

```python
"""Execution-quality drift ratio per DESIGN-0016 W5."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradingx.types import ReplaySlippageRecord


def compute_execution_drift_ratio(
    *,
    replay_records: tuple[ReplaySlippageRecord, ...],
    symbol: str | None = None,
    rolling_window_days: int = 30,
) -> Decimal:
    if not replay_records:
        return Decimal("0")
    window_start = datetime.now(UTC) - timedelta(days=rolling_window_days)
    filtered = tuple(
        record
        for record in replay_records
        if record.generated_at_utc >= window_start
        and (symbol is None or record.symbol == symbol)
    )
    if not filtered:
        return Decimal("0")
    total = sum(
        (abs(record.divergence_ratio) for record in filtered),
        start=Decimal("0"),
    )
    return total / Decimal(len(filtered))


__all__ = ("compute_execution_drift_ratio",)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_drift_execution.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/drift/execution.py tests/unit/test_drift_execution.py
git commit -m "feat(drift): add compute_execution_drift_ratio over ReplaySlippageRecord window"
```

---

## W6 — Active-sleeve daily attribution

### Task 6: `SleeveDailyAttributionRecord` type + persistence

**Files:**
- Modify: `src/tradingx/types.py`
- Modify: `src/tradingx/persistence.py`
- Modify: `tests/unit/test_types.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_types.py`:

```python
def test_sleeve_daily_attribution_record_is_frozen():
    import dataclasses
    from datetime import UTC, datetime
    from decimal import Decimal

    from tradingx.types import SleeveDailyAttributionRecord

    record = SleeveDailyAttributionRecord(
        attribution_id="attr-1",
        sleeve_id="trend-following-v1",
        trading_day="2026-04-21",
        recorded_at_utc=datetime.now(UTC),
        starting_equity=Decimal("100000"),
        ending_equity=Decimal("101000"),
        daily_return=Decimal("0.01"),
        per_symbol_open_weight=(("SPY", Decimal("0.5")),),
        per_symbol_close_weight=(("SPY", Decimal("0.52")),),
    )
    assert record.daily_return == Decimal("0.01")
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.attribution_id = "attr-2"  # type: ignore[misc]
```

Add a persistence roundtrip test in a new helper test file (or append to the existing `test_persistence.py` if it exists; otherwise create `tests/unit/test_drift_persistence.py`):

```python
from pathlib import Path

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import SleeveDailyAttributionRecord


def test_sleeve_daily_attribution_record_roundtrip(tmp_path: Path):
    store = FilesystemArtifactStore(tmp_path)
    record = SleeveDailyAttributionRecord(
        attribution_id="attr-a",
        sleeve_id="trend-following-v1",
        trading_day="2026-04-21",
        recorded_at_utc=datetime(2026, 4, 21, 20, 0, tzinfo=UTC),
        starting_equity=Decimal("100000"),
        ending_equity=Decimal("100500"),
        daily_return=Decimal("0.005"),
        per_symbol_open_weight=(("SPY", Decimal("0.4")),),
        per_symbol_close_weight=(("SPY", Decimal("0.42")),),
    )
    path = store.write_sleeve_daily_attribution_record(record)
    assert path.exists()
    # Read via the list reader.
    records = store.list_sleeve_daily_attribution_records(
        sleeve_id="trend-following-v1"
    )
    assert record in records
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_types.py tests/unit/test_drift_persistence.py -v`

Expected: FAIL on missing dataclass / missing store methods.

- [ ] **Step 3: Implement**

In `src/tradingx/types.py`, add the dataclass (near other record types):

```python
@dataclass(frozen=True)
class SleeveDailyAttributionRecord:
    attribution_id: str
    sleeve_id: str
    trading_day: str
    recorded_at_utc: datetime
    starting_equity: Decimal
    ending_equity: Decimal
    daily_return: Decimal
    per_symbol_open_weight: tuple[tuple[str, Decimal], ...]
    per_symbol_close_weight: tuple[tuple[str, Decimal], ...]
```

Add `SleeveDailyAttributionRecord` to `__all__`.

In `src/tradingx/persistence.py`, add two methods on `FilesystemArtifactStore`:

```python
def write_sleeve_daily_attribution_record(
    self,
    record: SleeveDailyAttributionRecord,
) -> Path:
    return self._write_json(
        "sleeve_daily_attribution",
        f"{record.sleeve_id}__{record.trading_day}.json",
        record,
    )


def list_sleeve_daily_attribution_records(
    self,
    *,
    sleeve_id: str,
) -> tuple[SleeveDailyAttributionRecord, ...]:
    directory = self._root / "sleeve_daily_attribution"
    if not directory.exists():
        return ()
    records: list[SleeveDailyAttributionRecord] = []
    for path in sorted(directory.glob(f"{sleeve_id}__*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        records.append(_deserialize_sleeve_daily_attribution_record(payload))
    return tuple(records)
```

Add the import for `SleeveDailyAttributionRecord` at the top and a small `_deserialize_*` helper following the existing `_serialize` convention.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_types.py tests/unit/test_drift_persistence.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/types.py src/tradingx/persistence.py tests/unit/test_types.py tests/unit/test_drift_persistence.py
git commit -m "feat(types): add SleeveDailyAttributionRecord + persistence round-trip"
```

### Task 7: `build_sleeve_daily_attribution_record` + `SleeveAttributionRecorder`

**Files:**
- Create: `src/tradingx/drift/attribution.py`
- Create: `tests/unit/test_drift_attribution.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_drift_attribution.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tradingx.drift.attribution import (
    SleeveAttributionRecorder,
    build_sleeve_daily_attribution_record,
)
from tradingx.types import (
    AccountSnapshot,
    ApprovedWeightSnapshot,
    PortfolioState,
    PositionSnapshot,
    StrategyActivationRecord,
    StrategyCandidate,
)


def _state(
    *,
    equity: Decimal,
    spy_quantity: Decimal = Decimal("0"),
    spy_price: Decimal = Decimal("100"),
) -> PortfolioState:
    return PortfolioState(
        as_of_utc=datetime(2026, 4, 21, 14, 30, tzinfo=UTC),
        cash=equity - spy_quantity * spy_price,
        equity=equity,
        buying_power=equity,
        positions=(
            (
                PositionSnapshot(
                    symbol="SPY",
                    quantity=spy_quantity,
                    average_entry_price=spy_price,
                    market_value=spy_quantity * spy_price,
                ),
            )
            if spy_quantity > 0
            else ()
        ),
        open_orders=(),
    )


def test_build_record_captures_daily_return():
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


def test_build_record_raises_on_zero_open_equity():
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
        activation: StrategyActivationRecord | None,
    ) -> None:
        self._candidate = candidate
        self._activation = activation

    def get_latest_activation(self) -> StrategyActivationRecord | None:
        return self._activation

    def get_active_candidate(self) -> StrategyCandidate | None:
        return self._candidate


class _FakeStore:
    def __init__(self) -> None:
        self.written = []

    def write_sleeve_daily_attribution_record(self, record):
        self.written.append(record)


def test_recorder_skips_non_sleeve_active_strategy():
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
        activation_gateway=_FakeActivationGateway(
            candidate=candidate,
            activation=None,
        ),
        attribution_store=_FakeStore(),
        now_provider=lambda: datetime(2026, 4, 21, tzinfo=UTC),
    )
    result = recorder.record_session(
        trading_day="2026-04-21",
        open_portfolio_state=_state(equity=Decimal("100000")),
        close_portfolio_state=_state(equity=Decimal("101000")),
    )
    assert result is None


def test_recorder_writes_record_for_sleeve_backed_active_strategy():
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
        activation_gateway=_FakeActivationGateway(
            candidate=candidate,
            activation=None,
        ),
        attribution_store=store,
        now_provider=lambda: datetime(2026, 4, 21, tzinfo=UTC),
    )
    result = recorder.record_session(
        trading_day="2026-04-21",
        open_portfolio_state=_state(equity=Decimal("100000")),
        close_portfolio_state=_state(equity=Decimal("101000")),
    )
    assert result is not None
    assert result.sleeve_id == "trend-following-v1"
    assert store.written == [result]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_drift_attribution.py -v`

Expected: FAIL on `ImportError`.

- [ ] **Step 3: Implement**

Create `src/tradingx/drift/attribution.py`:

```python
"""Active-sleeve daily attribution per DESIGN-0016 W6."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from tradingx.types import (
    PortfolioState,
    SleeveDailyAttributionRecord,
    StrategyActivationRecord,
    StrategyCandidate,
)


class AttributionStoreProtocol(Protocol):
    def write_sleeve_daily_attribution_record(
        self, record: SleeveDailyAttributionRecord
    ) -> object: ...


class ActivationGatewayProtocol(Protocol):
    def get_latest_activation(self) -> StrategyActivationRecord | None: ...
    def get_active_candidate(self) -> StrategyCandidate | None: ...


def build_sleeve_daily_attribution_record(
    *,
    attribution_id: str,
    trading_day: str,
    active_sleeve_id: str,
    open_portfolio_state: PortfolioState,
    close_portfolio_state: PortfolioState,
    recorded_at_utc: datetime,
) -> SleeveDailyAttributionRecord:
    if open_portfolio_state.equity <= Decimal("0"):
        raise ValueError(
            "starting_equity must be > 0 for an attribution record"
        )
    daily_return = (
        close_portfolio_state.equity - open_portfolio_state.equity
    ) / open_portfolio_state.equity
    return SleeveDailyAttributionRecord(
        attribution_id=attribution_id,
        sleeve_id=active_sleeve_id,
        trading_day=trading_day,
        recorded_at_utc=recorded_at_utc,
        starting_equity=open_portfolio_state.equity,
        ending_equity=close_portfolio_state.equity,
        daily_return=daily_return,
        per_symbol_open_weight=_state_to_weights(open_portfolio_state),
        per_symbol_close_weight=_state_to_weights(close_portfolio_state),
    )


class SleeveAttributionRecorder:
    def __init__(
        self,
        *,
        activation_gateway: ActivationGatewayProtocol,
        attribution_store: AttributionStoreProtocol,
        now_provider: Callable[[], datetime],
    ) -> None:
        self._activation_gateway = activation_gateway
        self._store = attribution_store
        self._now_provider = now_provider

    def record_session(
        self,
        *,
        trading_day: str,
        open_portfolio_state: PortfolioState,
        close_portfolio_state: PortfolioState,
    ) -> SleeveDailyAttributionRecord | None:
        candidate = self._activation_gateway.get_active_candidate()
        if candidate is None or candidate.sleeve_class_path is None:
            return None
        record = build_sleeve_daily_attribution_record(
            attribution_id=f"{candidate.candidate_id}__{trading_day}",
            trading_day=trading_day,
            active_sleeve_id=candidate.candidate_id,
            open_portfolio_state=open_portfolio_state,
            close_portfolio_state=close_portfolio_state,
            recorded_at_utc=self._now_provider(),
        )
        self._store.write_sleeve_daily_attribution_record(record)
        return record


def _state_to_weights(
    state: PortfolioState,
) -> tuple[tuple[str, Decimal], ...]:
    if state.equity <= Decimal("0"):
        return ()
    return tuple(
        (position.symbol, position.market_value / state.equity)
        for position in state.positions
    )


__all__ = (
    "ActivationGatewayProtocol",
    "AttributionStoreProtocol",
    "SleeveAttributionRecorder",
    "build_sleeve_daily_attribution_record",
)
```

**Note on `get_active_candidate`.** This method may not already
exist on the activation gateway. If it doesn't, add a thin
helper either on `ActivationGateway` or a free function in
`drift/attribution.py` that: (a) calls `get_latest_activation()`,
(b) looks up the `StrategyCandidate` by `strategy_id` in
`build_mandatory_candidate_registry()`, (c) returns the
candidate or `None`. Keep the protocol surface the same as
above.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_drift_attribution.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/drift/attribution.py tests/unit/test_drift_attribution.py
git commit -m "feat(drift): add SleeveAttributionRecorder + active-sleeve daily record"
```

---

## W7 — P&L divergence

### Task 8: `compute_live_vs_backtest_pnl_divergence` + backtest-reference artifact

**Files:**
- Create: `src/tradingx/drift/pnl_divergence.py`
- Create: `src/tradingx/drift/backtest_reference.py`
- Create: `tests/unit/test_drift_pnl_divergence.py`
- Create: `tests/unit/test_drift_backtest_reference.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_drift_pnl_divergence.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tradingx.drift.blueprint import DriftThresholds
from tradingx.drift.pnl_divergence import (
    PnlDivergenceVerdict,
    compute_live_vs_backtest_pnl_divergence,
)
from tradingx.types import SleeveDailyAttributionRecord


def _record(
    *,
    daily_return: str,
    days_ago: int,
) -> SleeveDailyAttributionRecord:
    recorded = datetime.now(UTC) - timedelta(days=days_ago)
    return SleeveDailyAttributionRecord(
        attribution_id=f"attr-{days_ago}",
        sleeve_id="trend-following-v1",
        trading_day=(recorded.date()).isoformat(),
        recorded_at_utc=recorded,
        starting_equity=Decimal("100000"),
        ending_equity=Decimal("100000") * (Decimal("1") + Decimal(daily_return)),
        daily_return=Decimal(daily_return),
        per_symbol_open_weight=(),
        per_symbol_close_weight=(),
    )


def test_pending_when_fewer_than_minimum_live_days():
    records = tuple(_record(daily_return="0.01", days_ago=i) for i in range(10))
    backtest = tuple(Decimal("0.01") for _ in range(60))
    verdict = compute_live_vs_backtest_pnl_divergence(
        sleeve_id="trend-following-v1",
        live_attribution_records=records,
        backtest_returns_series=backtest,
        thresholds=DriftThresholds(),
        minimum_live_days=30,
    )
    assert verdict.severity == "pending"


def test_info_when_matching_series():
    records = tuple(_record(daily_return="0.01", days_ago=i) for i in range(60))
    backtest = tuple(Decimal("0.01") for _ in range(60))
    verdict = compute_live_vs_backtest_pnl_divergence(
        sleeve_id="trend-following-v1",
        live_attribution_records=records,
        backtest_returns_series=backtest,
        thresholds=DriftThresholds(),
        minimum_live_days=30,
    )
    assert verdict.severity == "info"


def test_warning_when_absolute_delta_breaches_warning_threshold():
    records = tuple(_record(daily_return="0.03", days_ago=i) for i in range(60))
    backtest = tuple(Decimal("0.005") for _ in range(60))
    verdict = compute_live_vs_backtest_pnl_divergence(
        sleeve_id="trend-following-v1",
        live_attribution_records=records,
        backtest_returns_series=backtest,
        thresholds=DriftThresholds(),
        minimum_live_days=30,
    )
    # mean(|0.03 - 0.005|) = 0.025 >= 0.02 → warning
    assert verdict.severity == "warning"


def test_critical_when_absolute_delta_breaches_critical_threshold():
    records = tuple(_record(daily_return="0.05", days_ago=i) for i in range(60))
    backtest = tuple(Decimal("0.0") for _ in range(60))
    verdict = compute_live_vs_backtest_pnl_divergence(
        sleeve_id="trend-following-v1",
        live_attribution_records=records,
        backtest_returns_series=backtest,
        thresholds=DriftThresholds(),
        minimum_live_days=30,
    )
    assert verdict.severity == "critical"
```

Create `tests/unit/test_drift_backtest_reference.py`:

```python
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from tradingx.drift.backtest_reference import (
    load_backtest_reference_returns,
    write_backtest_reference_returns,
)


def test_write_and_load_returns(tmp_path: Path):
    artifact_root = tmp_path / "runtime"
    returns = (Decimal("0.001"), Decimal("-0.002"), Decimal("0.003"))
    path = write_backtest_reference_returns(
        artifact_root=artifact_root,
        sleeve_id="trend-following-v1",
        returns=returns,
    )
    assert path.exists()
    # Path must be under the runtime artifact tree, not config/strategy.
    assert path.parent.parent.name == "drift"
    assert "config/strategy" not in str(path)

    loaded = load_backtest_reference_returns(
        artifact_root=artifact_root,
        sleeve_id="trend-following-v1",
    )
    assert loaded == returns


def test_load_missing_returns_empty(tmp_path: Path):
    loaded = load_backtest_reference_returns(
        artifact_root=tmp_path / "runtime",
        sleeve_id="trend-following-v1",
    )
    assert loaded == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_drift_pnl_divergence.py tests/unit/test_drift_backtest_reference.py -v`

Expected: FAIL on `ImportError`.

- [ ] **Step 3: Implement**

Create `src/tradingx/drift/backtest_reference.py`:

```python
"""Backtest-reference returns artifact per DESIGN-0016 W7.

Runtime-tree path: {artifact_root}/drift/backtest_reference_returns/<sleeve_id>.json.
Config/strategy/* is operator-reviewed offline config and is NOT
touched by this module.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path


def _artifact_path(artifact_root: Path, sleeve_id: str) -> Path:
    return (
        artifact_root
        / "drift"
        / "backtest_reference_returns"
        / f"{sleeve_id}.json"
    )


def write_backtest_reference_returns(
    *,
    artifact_root: Path,
    sleeve_id: str,
    returns: tuple[Decimal, ...],
) -> Path:
    path = _artifact_path(artifact_root, sleeve_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "sleeve_id": sleeve_id,
        "returns": [str(value) for value in returns],
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def load_backtest_reference_returns(
    *,
    artifact_root: Path,
    sleeve_id: str,
) -> tuple[Decimal, ...]:
    path = _artifact_path(artifact_root, sleeve_id)
    if not path.exists():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(Decimal(str(v)) for v in payload.get("returns", ()))


__all__ = (
    "load_backtest_reference_returns",
    "write_backtest_reference_returns",
)
```

Create `src/tradingx/drift/pnl_divergence.py`:

```python
"""Live-vs-backtest P&L divergence per DESIGN-0016 W7."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tradingx.drift.blueprint import DriftThresholds
from tradingx.types import SleeveDailyAttributionRecord


@dataclass(frozen=True)
class PnlDivergenceVerdict:
    sleeve_id: str
    live_daily_return_series: tuple[Decimal, ...]
    backtest_daily_return_series: tuple[Decimal, ...]
    absolute_delta: Decimal
    sharpe_delta_ratio: Decimal
    severity: str  # "pending" | "info" | "warning" | "critical"


def compute_live_vs_backtest_pnl_divergence(
    *,
    sleeve_id: str,
    live_attribution_records: tuple[SleeveDailyAttributionRecord, ...],
    backtest_returns_series: tuple[Decimal, ...],
    thresholds: DriftThresholds,
    rolling_window_days: int = 60,
    minimum_live_days: int = 30,
) -> PnlDivergenceVerdict:
    live_filtered = tuple(
        record.daily_return
        for record in sorted(
            live_attribution_records,
            key=lambda r: r.trading_day,
        )[-rolling_window_days:]
        if record.sleeve_id == sleeve_id
    )
    if len(live_filtered) < minimum_live_days:
        return PnlDivergenceVerdict(
            sleeve_id=sleeve_id,
            live_daily_return_series=live_filtered,
            backtest_daily_return_series=(),
            absolute_delta=Decimal("0"),
            sharpe_delta_ratio=Decimal("0"),
            severity="pending",
        )
    backtest_tail = backtest_returns_series[-len(live_filtered):]
    absolute_delta = _mean_abs_delta(live_filtered, backtest_tail)
    sharpe_delta_ratio = _sharpe_delta_ratio(live_filtered, backtest_tail)
    severity = _severity(
        absolute_delta=absolute_delta,
        sharpe_delta_ratio=sharpe_delta_ratio,
        thresholds=thresholds,
    )
    return PnlDivergenceVerdict(
        sleeve_id=sleeve_id,
        live_daily_return_series=live_filtered,
        backtest_daily_return_series=backtest_tail,
        absolute_delta=absolute_delta,
        sharpe_delta_ratio=sharpe_delta_ratio,
        severity=severity,
    )


def _mean_abs_delta(
    live: tuple[Decimal, ...],
    backtest: tuple[Decimal, ...],
) -> Decimal:
    if not live or not backtest:
        return Decimal("0")
    pairs = list(zip(live, backtest, strict=False))
    if not pairs:
        return Decimal("0")
    total = sum((abs(l - b) for l, b in pairs), start=Decimal("0"))
    return total / Decimal(len(pairs))


def _sharpe_delta_ratio(
    live: tuple[Decimal, ...],
    backtest: tuple[Decimal, ...],
) -> Decimal:
    live_sharpe = _sample_sharpe(live)
    bt_sharpe = _sample_sharpe(backtest)
    denominator = max(abs(bt_sharpe), Decimal("0.3"))
    return (live_sharpe - bt_sharpe) / denominator


def _sample_sharpe(returns: tuple[Decimal, ...]) -> Decimal:
    if len(returns) < 2:
        return Decimal("0")
    mean = sum(returns, start=Decimal("0")) / Decimal(len(returns))
    sq_dev = sum(
        ((r - mean) ** 2 for r in returns),
        start=Decimal("0"),
    )
    variance = sq_dev / Decimal(len(returns) - 1)
    if variance <= Decimal("0"):
        return Decimal("0")
    std = Decimal(str(float(variance) ** 0.5))
    return mean / std


def _severity(
    *,
    absolute_delta: Decimal,
    sharpe_delta_ratio: Decimal,
    thresholds: DriftThresholds,
) -> str:
    abs_sharpe_delta = abs(sharpe_delta_ratio)
    if (
        absolute_delta >= thresholds.pnl_absolute_critical
        or abs_sharpe_delta >= thresholds.pnl_sharpe_critical
    ):
        return "critical"
    if (
        absolute_delta >= thresholds.pnl_absolute_warning
        or abs_sharpe_delta >= thresholds.pnl_sharpe_warning
    ):
        return "warning"
    return "info"


__all__ = (
    "PnlDivergenceVerdict",
    "compute_live_vs_backtest_pnl_divergence",
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_drift_pnl_divergence.py tests/unit/test_drift_backtest_reference.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/drift/pnl_divergence.py src/tradingx/drift/backtest_reference.py tests/unit/test_drift_pnl_divergence.py tests/unit/test_drift_backtest_reference.py
git commit -m "feat(drift): add P&L divergence monitor + runtime-tree reference artifact"
```

---

## W8 — `DriftAlarmGateway` concrete implementation

### Task 9: Reader protocols + `DriftMonitorVerdict` + gateway skeleton

**Files:**
- Create: `src/tradingx/drift/gateway.py`
- Create: `tests/unit/test_drift_gateway.py`

- [ ] **Step 1: Write failing tests (gateway happy path + alarm aggregation)**

Create `tests/unit/test_drift_gateway.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

import pandas as pd
import pytest

from tradingx.drift.blueprint import DriftMonitorBlueprint
from tradingx.drift.gateway import (
    DRIFT_ALARM_CONTROL_TYPE,
    DriftAlarmGateway,
    DriftMonitorVerdict,
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


# ...fixtures match the plan's suggested readers; each reader is
# a minimal fake — see test body for each exact shape.

def _uniform_feature_distribution(name: str) -> FeatureDistribution:
    return FeatureDistribution(
        feature_name=name,
        bin_edges=tuple(Decimal(str(i / 10)) for i in range(11)),
        bin_proportions=tuple(Decimal("0.1") for _ in range(10)),
        observation_count=1000,
    )


def _signal_distribution(sleeve_id: str) -> SignalDistribution:
    return SignalDistribution(
        sleeve_id=sleeve_id,
        observed_samples=tuple(Decimal(str(x / 100)) for x in range(100)),
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
        return self._samples.get(feature_name, pd.Series([], dtype=float))


class _SignalReader:
    def __init__(self, samples: dict[str, pd.Series]) -> None:
        self._samples = samples

    def live_samples(self, sleeve_id: str, *, window_days: int) -> pd.Series:
        if sleeve_id not in self._samples:
            raise LookupError(sleeve_id)
        return self._samples[sleeve_id]


class _ReplayReader:
    def __init__(self, records: tuple[ReplaySlippageRecord, ...]) -> None:
        self._records = records

    def recent_records(self, *, window_days: int) -> tuple[ReplaySlippageRecord, ...]:
        return self._records


class _AttributionReader:
    def __init__(self, records: tuple[SleeveDailyAttributionRecord, ...]) -> None:
        self._records = records

    def records_for_sleeve(
        self, sleeve_id: str, *, window_days: int
    ) -> tuple[SleeveDailyAttributionRecord, ...]:
        return tuple(r for r in self._records if r.sleeve_id == sleeve_id)


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


def test_has_alarm_false_when_all_monitors_info(base_snapshot):
    # Provide uniform live samples for PSI; identical signal samples
    # for KS; zero execution drift; empty attribution → all monitors
    # return info or pending.
    feature_reader = _FeatureReader(
        samples={
            "spy_close_over_sma_200": pd.Series(
                [i / 1000 for i in range(1000)]
            ),
        }
    )
    signal_reader = _SignalReader(
        samples={
            "trend-following-v1": pd.Series([x / 100 for x in range(100)]),
            "vol-target-v1": pd.Series([x / 100 for x in range(100)]),
        }
    )
    replay_reader = _ReplayReader(records=())
    attribution_reader = _AttributionReader(records=())
    reference_returns = _ReferenceReturnsReader(returns={})
    risk_sink = _RiskEventSink()
    alerts = _AlertGateway()

    gateway = DriftAlarmGateway(
        blueprint=DriftMonitorBlueprint(blueprint_id="bp"),
        reference_snapshot=base_snapshot,
        feature_sample_reader=feature_reader,
        signal_sample_reader=signal_reader,
        replay_records_reader=replay_reader,
        attribution_records_reader=attribution_reader,
        backtest_reference_returns_reader=reference_returns,
        risk_control_event_sink=risk_sink,
        alert_gateway=alerts,
    )
    verdicts = gateway.refresh()
    assert all(v.severity in {"info", "pending"} for v in verdicts)
    assert gateway.has_alarm(sleeve_id="trend-following-v1") is False
    assert gateway.has_alarm(sleeve_id="vol-target-v1") is False
    # RiskControlEvents emitted for every verdict.
    assert len(risk_sink.events) == len(verdicts)
    # No operator alerts emitted for info or pending.
    assert alerts.alerts == []


def test_has_alarm_true_on_critical_ks_only_for_affected_sleeve(base_snapshot):
    # Shift trend-following-v1's live signal distribution; vol-target-v1
    # stays identical. Only trend-following-v1's has_alarm should fire.
    feature_reader = _FeatureReader(
        samples={
            "spy_close_over_sma_200": pd.Series(
                [i / 1000 for i in range(1000)]
            ),
        }
    )
    signal_reader = _SignalReader(
        samples={
            "trend-following-v1": pd.Series([5.0] * 100),  # constant, critical shift
            "vol-target-v1": pd.Series([x / 100 for x in range(100)]),
        }
    )
    replay_reader = _ReplayReader(records=())
    attribution_reader = _AttributionReader(records=())
    reference_returns = _ReferenceReturnsReader(returns={})
    risk_sink = _RiskEventSink()
    alerts = _AlertGateway()

    gateway = DriftAlarmGateway(
        blueprint=DriftMonitorBlueprint(blueprint_id="bp"),
        reference_snapshot=base_snapshot,
        feature_sample_reader=feature_reader,
        signal_sample_reader=signal_reader,
        replay_records_reader=replay_reader,
        attribution_records_reader=attribution_reader,
        backtest_reference_returns_reader=reference_returns,
        risk_control_event_sink=risk_sink,
        alert_gateway=alerts,
    )
    gateway.refresh()
    assert gateway.has_alarm(sleeve_id="trend-following-v1") is True
    assert gateway.has_alarm(sleeve_id="vol-target-v1") is False
    # Exactly one operator alert emitted (critical KS on trend).
    assert len(alerts.alerts) == 1
    assert alerts.alerts[0].category == DRIFT_ALARM_CONTROL_TYPE


def test_refresh_emits_one_risk_control_event_per_verdict(base_snapshot):
    feature_reader = _FeatureReader(samples={})
    signal_reader = _SignalReader(samples={})
    replay_reader = _ReplayReader(records=())
    attribution_reader = _AttributionReader(records=())
    reference_returns = _ReferenceReturnsReader(returns={})
    risk_sink = _RiskEventSink()
    alerts = _AlertGateway()

    gateway = DriftAlarmGateway(
        blueprint=DriftMonitorBlueprint(
            blueprint_id="bp",
            feature_monitor_names=("spy_close_over_sma_200",),
            signal_monitor_sleeve_ids=(
                "trend-following-v1",
                "vol-target-v1",
            ),
        ),
        reference_snapshot=base_snapshot,
        feature_sample_reader=feature_reader,
        signal_sample_reader=signal_reader,
        replay_records_reader=replay_reader,
        attribution_records_reader=attribution_reader,
        backtest_reference_returns_reader=reference_returns,
        risk_control_event_sink=risk_sink,
        alert_gateway=alerts,
    )
    verdicts = gateway.refresh()
    assert len(risk_sink.events) == len(verdicts)
    # Every event must use the canonical control_type string.
    assert all(
        event.control_type == DRIFT_ALARM_CONTROL_TYPE
        for event in risk_sink.events
    )


def test_ks_sleeve_without_registry_candidate_records_pending(base_snapshot):
    # Signal reader raises LookupError for a sleeve whose candidate
    # isn't in the mandatory registry.
    class _FailingSignalReader:
        def live_samples(self, sleeve_id: str, *, window_days: int):
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
        v for v in verdicts if v.monitor_id.startswith("ks::")
    )
    assert len(ks_verdicts) == 1
    assert ks_verdicts[0].severity == "pending"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_drift_gateway.py -v`

Expected: FAIL on `ImportError`.

- [ ] **Step 3: Implement**

Create `src/tradingx/drift/gateway.py`:

```python
"""Concrete DriftAlarmGateway per DESIGN-0016 W8."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Final, Protocol

import pandas as pd  # type: ignore[import-untyped]

from tradingx.drift.blueprint import DriftMonitorBlueprint
from tradingx.drift.execution import compute_execution_drift_ratio
from tradingx.drift.ks import compute_kolmogorov_smirnov
from tradingx.drift.pnl_divergence import (
    compute_live_vs_backtest_pnl_divergence,
)
from tradingx.drift.psi import compute_population_stability_index
from tradingx.drift.reference import ReferenceDistributionSnapshot
from tradingx.portfolio.sleeve_runtime import DriftAlarmGatewayProtocol
from tradingx.types import (
    OperatorAlert,
    ReplaySlippageRecord,
    RiskControlEvent,
    SleeveDailyAttributionRecord,
)


DRIFT_ALARM_CONTROL_TYPE: Final[str] = "portfolio_drift_alarm"


@dataclass(frozen=True)
class DriftMonitorVerdict:
    monitor_id: str
    sleeve_id: str | None
    severity: str  # "info" | "warning" | "critical" | "pending"
    metric_value: Decimal | None
    threshold_value: Decimal | None
    details: str


class FeatureSampleReaderProtocol(Protocol):
    def live_samples(
        self, feature_name: str, *, window_days: int
    ) -> pd.Series: ...


class SignalSampleReaderProtocol(Protocol):
    def live_samples(
        self, sleeve_id: str, *, window_days: int
    ) -> pd.Series: ...


class ReplayRecordsReaderProtocol(Protocol):
    def recent_records(
        self, *, window_days: int
    ) -> tuple[ReplaySlippageRecord, ...]: ...


class AttributionRecordsReaderProtocol(Protocol):
    def records_for_sleeve(
        self, sleeve_id: str, *, window_days: int
    ) -> tuple[SleeveDailyAttributionRecord, ...]: ...


class BacktestReferenceReturnsReaderProtocol(Protocol):
    def returns_for_sleeve(
        self, sleeve_id: str
    ) -> tuple[Decimal, ...]: ...


class RiskControlEventSinkProtocol(Protocol):
    def write_risk_control_event(
        self, event: RiskControlEvent
    ) -> object: ...


class OperatorAlertGatewayProtocol(Protocol):
    def publish(self, alert: OperatorAlert) -> None: ...


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
        self._latest_verdicts: tuple[DriftMonitorVerdict, ...] = ()

    def has_alarm(self, *, sleeve_id: str) -> bool:
        for verdict in self._latest_verdicts:
            if verdict.severity != "critical":
                continue
            if verdict.sleeve_id is None or verdict.sleeve_id == sleeve_id:
                return True
        return False

    def refresh(self) -> tuple[DriftMonitorVerdict, ...]:
        verdicts: list[DriftMonitorVerdict] = []
        verdicts.extend(self._psi_verdicts())
        verdicts.extend(self._ks_verdicts())
        verdicts.extend(self._execution_verdicts())
        verdicts.extend(self._pnl_verdicts())
        for verdict in verdicts:
            self._risk_sink.write_risk_control_event(
                self._to_risk_event(verdict)
            )
            if verdict.severity in {"warning", "critical"}:
                self._alert_gateway.publish(self._to_alert(verdict))
        self._latest_verdicts = tuple(verdicts)
        return self._latest_verdicts

    def latest_verdicts(self) -> tuple[DriftMonitorVerdict, ...]:
        return self._latest_verdicts

    def _psi_verdicts(self) -> tuple[DriftMonitorVerdict, ...]:
        verdicts: list[DriftMonitorVerdict] = []
        reference_by_name = {
            fd.feature_name: fd
            for fd in self._reference_snapshot.feature_distributions
        }
        for feature_name in self._blueprint.feature_monitor_names:
            ref = reference_by_name.get(feature_name)
            if ref is None:
                verdicts.append(
                    DriftMonitorVerdict(
                        monitor_id=f"psi::{feature_name}",
                        sleeve_id=None,
                        severity="pending",
                        metric_value=None,
                        threshold_value=None,
                        details="no reference distribution",
                    )
                )
                continue
            samples = self._feature_reader.live_samples(
                feature_name,
                window_days=self._blueprint.minimum_live_days_for_alarm,
            )
            if len(samples) < self._blueprint.minimum_live_days_for_alarm:
                verdicts.append(
                    DriftMonitorVerdict(
                        monitor_id=f"psi::{feature_name}",
                        sleeve_id=None,
                        severity="pending",
                        metric_value=None,
                        threshold_value=None,
                        details=(
                            f"insufficient live samples: {len(samples)} "
                            f"< {self._blueprint.minimum_live_days_for_alarm}"
                        ),
                    )
                )
                continue
            psi = compute_population_stability_index(
                reference_distribution=ref,
                live_samples=samples,
            )
            severity = self._psi_severity(psi)
            verdicts.append(
                DriftMonitorVerdict(
                    monitor_id=f"psi::{feature_name}",
                    sleeve_id=None,
                    severity=severity,
                    metric_value=psi,
                    threshold_value=self._blueprint.thresholds.psi_critical,
                    details=f"PSI={psi}",
                )
            )
        return tuple(verdicts)

    def _psi_severity(self, psi: Decimal) -> str:
        thresholds = self._blueprint.thresholds
        if psi >= thresholds.psi_critical:
            return "critical"
        if psi >= thresholds.psi_warning:
            return "warning"
        return "info"

    def _ks_verdicts(self) -> tuple[DriftMonitorVerdict, ...]:
        verdicts: list[DriftMonitorVerdict] = []
        reference_by_sleeve = {
            sd.sleeve_id: sd
            for sd in self._reference_snapshot.signal_distributions
        }
        for sleeve_id in self._blueprint.signal_monitor_sleeve_ids:
            ref = reference_by_sleeve.get(sleeve_id)
            if ref is None:
                verdicts.append(_pending_verdict(f"ks::{sleeve_id}", sleeve_id, "no reference"))
                continue
            try:
                samples = self._signal_reader.live_samples(
                    sleeve_id,
                    window_days=self._blueprint.minimum_live_days_for_alarm,
                )
            except LookupError:
                verdicts.append(
                    _pending_verdict(
                        f"ks::{sleeve_id}",
                        sleeve_id,
                        "sleeve not in mandatory registry or sleeve_class_path=None",
                    )
                )
                continue
            if len(samples) < self._blueprint.minimum_live_days_for_alarm:
                verdicts.append(
                    _pending_verdict(
                        f"ks::{sleeve_id}",
                        sleeve_id,
                        f"insufficient live samples: {len(samples)}",
                    )
                )
                continue
            ks = compute_kolmogorov_smirnov(
                reference_samples=ref.observed_samples,
                live_samples=samples,
            )
            severity = (
                "critical"
                if ks.p_value < self._blueprint.thresholds.ks_p_value_critical
                else "info"
            )
            verdicts.append(
                DriftMonitorVerdict(
                    monitor_id=f"ks::{sleeve_id}",
                    sleeve_id=sleeve_id,
                    severity=severity,
                    metric_value=ks.p_value,
                    threshold_value=self._blueprint.thresholds.ks_p_value_critical,
                    details=f"KS stat={ks.statistic} p={ks.p_value}",
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
                    "execution::portfolio",
                    None,
                    "no replay records in window",
                ),
            )
        ratio = compute_execution_drift_ratio(
            replay_records=records,
            rolling_window_days=self._blueprint.execution_drift_rolling_window_days,
        )
        thresholds = self._blueprint.thresholds
        if ratio >= thresholds.execution_drift_critical:
            severity = "critical"
        elif ratio >= thresholds.execution_drift_warning:
            severity = "warning"
        else:
            severity = "info"
        return (
            DriftMonitorVerdict(
                monitor_id="execution::portfolio",
                sleeve_id=None,
                severity=severity,
                metric_value=ratio,
                threshold_value=thresholds.execution_drift_critical,
                details=f"mean |divergence_ratio|={ratio}",
            ),
        )

    def _pnl_verdicts(self) -> tuple[DriftMonitorVerdict, ...]:
        verdicts: list[DriftMonitorVerdict] = []
        for sleeve_id in self._blueprint.signal_monitor_sleeve_ids:
            records = self._attribution_reader.records_for_sleeve(
                sleeve_id,
                window_days=self._blueprint.pnl_divergence_rolling_window_days,
            )
            reference_returns = self._backtest_reference_reader.returns_for_sleeve(
                sleeve_id,
            )
            verdict = compute_live_vs_backtest_pnl_divergence(
                sleeve_id=sleeve_id,
                live_attribution_records=records,
                backtest_returns_series=reference_returns,
                thresholds=self._blueprint.thresholds,
                rolling_window_days=self._blueprint.pnl_divergence_rolling_window_days,
                minimum_live_days=self._blueprint.minimum_live_days_for_alarm,
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
            severity=_risk_severity(verdict.severity),
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
                f"{verdict.monitor_id} {verdict.severity.upper()}: "
                f"{verdict.details}"
            ),
            evidence_refs=(),
            delivery_targets=("operator_dashboard",),
            sent_at_utc=datetime.now(UTC),
        )


def _pending_verdict(
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


def _risk_severity(drift_severity: str) -> str:
    # DriftMonitorVerdict.severity strings map 1:1 onto RiskControlEvent.severity
    # with 'pending' degraded to 'info' per §P3.
    if drift_severity == "pending":
        return "info"
    return drift_severity


__all__ = (
    "AttributionRecordsReaderProtocol",
    "BacktestReferenceReturnsReaderProtocol",
    "DRIFT_ALARM_CONTROL_TYPE",
    "DriftAlarmGateway",
    "DriftMonitorVerdict",
    "FeatureSampleReaderProtocol",
    "OperatorAlertGatewayProtocol",
    "ReplayRecordsReaderProtocol",
    "RiskControlEventSinkProtocol",
    "SignalSampleReaderProtocol",
)
```

**Sanity check — satisfies `DriftAlarmGatewayProtocol` from
tranche 1.4.** The protocol requires `has_alarm(self, *, sleeve_id: str) -> bool`. This class provides it. `SleeveRuntimeController.__init__` accepts any `DriftAlarmGatewayProtocol`, so wiring is a simple constructor injection.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_drift_gateway.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/drift/gateway.py tests/unit/test_drift_gateway.py
git commit -m "feat(drift): add DriftAlarmGateway concrete implementation + reader protocols"
```

---

## W9 — `LIVE_DAILY_RETURNS` implementation

### Task 10: `SleeveDailyReturnsReader` + SleeveRuntimeController wiring

**Files:**
- Create: `src/tradingx/drift/live_returns_source.py`
- Modify: `src/tradingx/portfolio/sleeve_runtime.py`
- Create: `tests/unit/test_drift_live_returns_source.py`
- Modify: `tests/unit/test_sleeve_runtime_controller.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_drift_live_returns_source.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradingx.drift.live_returns_source import SleeveDailyReturnsReader
from tradingx.types import SleeveDailyAttributionRecord


def _record(sleeve_id: str, daily_return: str, days_ago: int) -> SleeveDailyAttributionRecord:
    recorded = datetime.now(UTC) - timedelta(days=days_ago)
    return SleeveDailyAttributionRecord(
        attribution_id=f"attr-{sleeve_id}-{days_ago}",
        sleeve_id=sleeve_id,
        trading_day=(recorded.date()).isoformat(),
        recorded_at_utc=recorded,
        starting_equity=Decimal("100000"),
        ending_equity=Decimal("100000"),
        daily_return=Decimal(daily_return),
        per_symbol_open_weight=(),
        per_symbol_close_weight=(),
    )


class _FakeReader:
    def __init__(self, records):
        self._records = records

    def records_for_sleeve(self, sleeve_id, *, window_days):
        return tuple(
            r for r in self._records if r.sleeve_id == sleeve_id
        )


def test_reader_returns_daily_returns_in_trading_day_order():
    records = (
        _record("trend-following-v1", "0.01", 3),
        _record("trend-following-v1", "0.02", 2),
        _record("trend-following-v1", "0.03", 1),
        _record("other", "0.99", 1),
    )
    reader = SleeveDailyReturnsReader(
        attribution_records_reader=_FakeReader(records)
    )
    result = reader.live_daily_returns(
        sleeve_id="trend-following-v1",
        window_days=60,
    )
    assert result == (Decimal("0.01"), Decimal("0.02"), Decimal("0.03"))


def test_reader_returns_empty_when_no_records():
    reader = SleeveDailyReturnsReader(
        attribution_records_reader=_FakeReader(records=())
    )
    assert reader.live_daily_returns(sleeve_id="x", window_days=60) == ()
```

Append to `tests/unit/test_sleeve_runtime_controller.py`:

```python
def test_live_daily_returns_above_floor_does_not_fire_gate():
    import numpy as np

    from tradingx.portfolio.sleeve_runtime import (
        LiveDailyReturnsSourceProtocol,
        RollingWindowSource,
        SleeveRuntimeConfig,
        SleeveRuntimeController,
    )

    # 63 days of live returns with positive mean and real variance
    # so annualized Lo-adjusted Sharpe is clearly above the zero
    # floor (the canonical Sharpe definition used by the TRIAL_SUMMARY
    # branch — see _should_trigger_sharpe_gate_via_live_returns).
    rng = np.random.default_rng(seed=1337)
    positive = rng.normal(loc=0.002, scale=0.005, size=63).tolist()

    class _Source:
        def live_daily_returns(self, *, sleeve_id, window_days):
            return tuple(Decimal(str(v)) for v in positive)

    sleeve = _FakeSleeve(_sleeve_delegates_trade())
    config = SleeveRuntimeConfig(
        three_month_sharpe_floor=Decimal("0.0"),
        three_month_window_days=63,
        trial_lookback=3,
        rolling_window_source=RollingWindowSource.LIVE_DAILY_RETURNS,
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=sleeve,
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=config,
        live_daily_returns_source=_Source(),
    )
    out = controller.plan_for_bar(_context())
    # Sharpe > 0 (annualized) → gate does not fire → sleeve delegates.
    assert out[0].rationale == "tsmom_long_vol_targeted"


def test_live_daily_returns_below_floor_fires_sharpe_gate():
    import numpy as np

    from tradingx.portfolio.sleeve_runtime import (
        LiveDailyReturnsSourceProtocol,
        RollingWindowSource,
        SleeveRuntimeConfig,
        SleeveRuntimeController,
    )

    # 63 days of returns with negative mean and real variance →
    # annualized Lo-adjusted Sharpe below the zero floor.
    rng = np.random.default_rng(seed=2026)
    negative = rng.normal(loc=-0.002, scale=0.005, size=63).tolist()

    class _Source:
        def live_daily_returns(self, *, sleeve_id, window_days):
            return tuple(Decimal(str(v)) for v in negative)

    sleeve = _FakeSleeve(_sleeve_delegates_trade())
    config = SleeveRuntimeConfig(
        three_month_sharpe_floor=Decimal("0.0"),
        three_month_window_days=63,
        trial_lookback=3,
        rolling_window_source=RollingWindowSource.LIVE_DAILY_RETURNS,
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=sleeve,
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=config,
        live_daily_returns_source=_Source(),
    )
    out = controller.plan_for_bar(_context())
    assert out[0].rationale == SleeveFailureReason.SLEEVE_SHARPE_BELOW_THRESHOLD_6M


def test_live_daily_returns_zero_variance_returns_pending():
    # Constant returns → undefined Sharpe (zero variance) →
    # lo_adjusted_sharpe_ratio returns None → gate does not fire
    # (pending semantics). Pins the defensive branch in
    # _should_trigger_sharpe_gate_via_live_returns.
    from tradingx.portfolio.sleeve_runtime import (
        RollingWindowSource,
        SleeveRuntimeConfig,
        SleeveRuntimeController,
    )

    class _Source:
        def live_daily_returns(self, *, sleeve_id, window_days):
            return tuple(Decimal("0.001") for _ in range(63))

    sleeve = _FakeSleeve(_sleeve_delegates_trade())
    config = SleeveRuntimeConfig(
        three_month_sharpe_floor=Decimal("0.0"),
        three_month_window_days=63,
        trial_lookback=3,
        rolling_window_source=RollingWindowSource.LIVE_DAILY_RETURNS,
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=sleeve,
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=config,
        live_daily_returns_source=_Source(),
    )
    out = controller.plan_for_bar(_context())
    assert out[0].rationale == "tsmom_long_vol_targeted"


def test_live_daily_returns_insufficient_records_skips_gate():
    from tradingx.portfolio.sleeve_runtime import (
        RollingWindowSource,
        SleeveRuntimeConfig,
        SleeveRuntimeController,
    )

    # Fewer than three_month_window_days of returns → skip gate (pending).
    class _Source:
        def live_daily_returns(self, *, sleeve_id, window_days):
            return tuple(Decimal("-0.1") for _ in range(10))

    sleeve = _FakeSleeve(_sleeve_delegates_trade())
    config = SleeveRuntimeConfig(
        three_month_sharpe_floor=Decimal("0.0"),
        three_month_window_days=63,
        trial_lookback=3,
        rolling_window_source=RollingWindowSource.LIVE_DAILY_RETURNS,
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=sleeve,
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=config,
        live_daily_returns_source=_Source(),
    )
    out = controller.plan_for_bar(_context())
    # Insufficient live history → pending semantics → sleeve delegates.
    assert out[0].rationale == "tsmom_long_vol_targeted"


def test_live_daily_returns_source_missing_raises_value_error():
    from tradingx.portfolio.sleeve_runtime import (
        RollingWindowSource,
        SleeveRuntimeConfig,
        SleeveRuntimeController,
    )

    sleeve = _FakeSleeve(_sleeve_delegates_trade())
    config = SleeveRuntimeConfig(
        three_month_sharpe_floor=Decimal("0.0"),
        three_month_window_days=63,
        trial_lookback=3,
        rolling_window_source=RollingWindowSource.LIVE_DAILY_RETURNS,
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=sleeve,
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=config,
        live_daily_returns_source=None,
    )
    with pytest.raises(ValueError, match="live_daily_returns_source"):
        controller.plan_for_bar(_context())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_drift_live_returns_source.py tests/unit/test_sleeve_runtime_controller.py -v`

Expected: FAIL on `ImportError` for `LiveDailyReturnsSourceProtocol` and `SleeveDailyReturnsReader`.

- [ ] **Step 3: Implement**

Create `src/tradingx/drift/live_returns_source.py`:

```python
"""Live daily returns source for the SleeveRuntimeController per DESIGN-0016 W9."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from tradingx.types import SleeveDailyAttributionRecord


class AttributionRecordsReaderProtocol(Protocol):
    def records_for_sleeve(
        self, sleeve_id: str, *, window_days: int
    ) -> tuple[SleeveDailyAttributionRecord, ...]: ...


class SleeveDailyReturnsReader:
    def __init__(
        self,
        *,
        attribution_records_reader: AttributionRecordsReaderProtocol,
    ) -> None:
        self._reader = attribution_records_reader

    def live_daily_returns(
        self,
        *,
        sleeve_id: str,
        window_days: int,
    ) -> tuple[Decimal, ...]:
        records = self._reader.records_for_sleeve(
            sleeve_id, window_days=window_days
        )
        if not records:
            return ()
        sorted_records = sorted(
            records, key=lambda r: r.trading_day
        )
        return tuple(record.daily_return for record in sorted_records)


__all__ = (
    "AttributionRecordsReaderProtocol",
    "SleeveDailyReturnsReader",
)
```

In `src/tradingx/portfolio/sleeve_runtime.py`, make the following changes:

```python
# Add to existing imports (top of file):
from collections.abc import Callable


class LiveDailyReturnsSourceProtocol(Protocol):
    def live_daily_returns(
        self, *, sleeve_id: str, window_days: int
    ) -> tuple[Decimal, ...]: ...


class SleeveRuntimeController:
    def __init__(
        self,
        *,
        wrapped_sleeve: SleeveProtocol,
        operator_halt_store: SleeveOperatorHaltStoreProtocol,
        drift_alarm_gateway: DriftAlarmGatewayProtocol | None,
        trials_ledger: TrialsLedgerReadProtocol | None,
        config: SleeveRuntimeConfig,
        live_daily_returns_source: LiveDailyReturnsSourceProtocol | None = None,
    ) -> None:
        self._sleeve = wrapped_sleeve
        self._halt_store = operator_halt_store
        self._drift_gateway = drift_alarm_gateway
        self._ledger = trials_ledger
        self._config = config
        self._live_returns_source = live_daily_returns_source
```

**`plan_for_bar` changes.** Remove the
`NotImplementedError` in the
`rolling_window_source == LIVE_DAILY_RETURNS` branch. Replace
it with a misconfiguration guard + fall-through (the gate check
happens in `_should_trigger_sharpe_gate`, not in `plan_for_bar`):

```python
def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
    if (
        self._config.rolling_window_source == RollingWindowSource.LIVE_DAILY_RETURNS
        and self._live_returns_source is None
    ):
        raise ValueError(
            "live_daily_returns_source is required when "
            "rolling_window_source=LIVE_DAILY_RETURNS"
        )

    if self._halt_store.is_halted(sleeve_id=self._sleeve.sleeve_id):
        return self._emit_termination(
            context, rationale=SleeveFailureReason.HALT_BY_OPERATOR,
        )

    if self._drift_gateway is not None and self._drift_gateway.has_alarm(
        sleeve_id=self._sleeve.sleeve_id,
    ):
        return self._emit_termination(
            context, rationale=SleeveFailureReason.DRIFT_ALARM_LIVE,
        )

    if self._should_trigger_sharpe_gate():
        return self._emit_termination(
            context,
            rationale=SleeveFailureReason.SLEEVE_SHARPE_BELOW_THRESHOLD_6M,
        )

    return self._sleeve.plan_for_bar(context)
```

**`_should_trigger_sharpe_gate` now branches on source.** This
is the load-bearing change that delivers the spec's contract:
when `rolling_window_source == LIVE_DAILY_RETURNS`, the gate
consults the live daily returns source and computes Sharpe on
that series rather than the trials ledger.

**Sharpe scale (Codex round-2 plan-review P1 fix).** Both
branches MUST compare against the same Sharpe scale, because
`three_month_sharpe_floor` is a single configured number. The
`TRIAL_SUMMARY` branch consumes `TrialRecord.observed_sharpe_net_of_costs`
which is written by `evaluate_candidate` at
[evaluation.py:53](/src/tradingx/evaluation.py:53) via
`lo_adjusted_sharpe_ratio(returns, risk_free_daily_rates, periods_per_year=TRADING_DAYS_PER_YEAR)`
in [stats.py:92](/src/tradingx/stats.py:92) — **annualized
Lo-adjusted Sharpe at 252 periods/year**. The live branch MUST
use the same function so the floor applies consistently. Do
not invent a new `_sample_sharpe` helper that returns a
per-period `mean/std`; use the canonical `lo_adjusted_sharpe_ratio`.

```python
from tradingx.stats import lo_adjusted_sharpe_ratio
from tradingx.evaluation import TRADING_DAYS_PER_YEAR


def _should_trigger_sharpe_gate(self) -> bool:
    if self._config.rolling_window_source == RollingWindowSource.LIVE_DAILY_RETURNS:
        return self._should_trigger_sharpe_gate_via_live_returns()
    return self._should_trigger_sharpe_gate_via_trial_summary()


def _should_trigger_sharpe_gate_via_live_returns(self) -> bool:
    # Guarded in plan_for_bar; reaching here means source is non-None.
    assert self._live_returns_source is not None
    returns = self._live_returns_source.live_daily_returns(
        sleeve_id=self._sleeve.sleeve_id,
        window_days=self._config.three_month_window_days,
    )
    # Pending semantics: fewer than `three_month_window_days` of live
    # records → insufficient evidence → do not fire.
    if len(returns) < self._config.three_month_window_days:
        return False
    sharpe = lo_adjusted_sharpe_ratio(
        returns=[float(r) for r in returns],
        risk_free_daily_rates=(0.0,) * len(returns),
        periods_per_year=TRADING_DAYS_PER_YEAR,
    )
    if sharpe is None:
        # Undefined Sharpe (e.g., zero variance) → pending, do not fire.
        return False
    return Decimal(str(sharpe)) < self._config.three_month_sharpe_floor


def _should_trigger_sharpe_gate_via_trial_summary(self) -> bool:
    # Existing TRIAL_SUMMARY logic from tranche 1.4, unchanged.
    if self._ledger is None:
        return False
    records = self._ledger.records_for_candidate(self._sleeve.sleeve_id)
    # ...same as the 1.4 implementation (trial_lookback consecutive
    # records with window >= three_month_window_days all below floor).
```

**Why `risk_free_daily_rates=(0.0,) * len(returns)`.** The
existing Gate 1 path in
[validation.py:73](/src/tradingx/validation.py:73) also calls
`lo_adjusted_sharpe_ratio` with zero daily risk-free rates
when computing `observed_sharpe_net_of_costs`, so the
TRIAL_SUMMARY side's floor is already calibrated against this
assumption. The live branch follows the same convention to
keep the floor comparable. If a future amendment introduces
real risk-free rates for the live path, the TRIAL_SUMMARY
side must be updated in lockstep (and the floor re-calibrated).

Add `LiveDailyReturnsSourceProtocol` to `__all__`. No new
`_sample_sharpe` helper is added in this task — the canonical
`lo_adjusted_sharpe_ratio` is the single source of truth and
`drift/pnl_divergence.py` (Task 8) already carries its own
simpler per-period Sharpe for delta comparison against the
backtest reference series (where BOTH live and backtest go
through the same local helper, so the delta is scale-consistent
even if not annualized — see Task 8's contract).

**Design note — LIVE_DAILY_RETURNS gate semantics (Codex
round-1 + round-2 plan-review P1 fixes).** 1.5 replaces the
`NotImplementedError` AND delivers the live-Sharpe gate logic
the merged spec requires, using the same annualized Lo-adjusted
Sharpe definition the TRIAL_SUMMARY branch consumes. The gate
is source-selectable via `rolling_window_source`: TRIAL_SUMMARY
(1.4's behavior, unchanged) or LIVE_DAILY_RETURNS (1.5's new
behavior with matched Sharpe scale). Default remains
TRIAL_SUMMARY for backwards compatibility; operators opt into
LIVE_DAILY_RETURNS by setting
`SleeveRuntimeConfig.rolling_window_source`. The misconfiguration
guard in `plan_for_bar` raises `ValueError` if LIVE_DAILY_RETURNS
is selected but no source is injected — this is what Task 10's
`test_live_daily_returns_source_missing_raises_value_error`
pins.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_drift_live_returns_source.py tests/unit/test_sleeve_runtime_controller.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/drift/live_returns_source.py src/tradingx/portfolio/sleeve_runtime.py tests/unit/test_drift_live_returns_source.py tests/unit/test_sleeve_runtime_controller.py
git commit -m "feat(drift): replace LIVE_DAILY_RETURNS NotImplementedError with real reader"
```

---

## W10 — Operator surface + integration + closing pass

### Task 11: `recalibrate_drift_reference` operator action

**Files:**
- Modify: `src/tradingx/operator_control.py`
- Modify: `tests/unit/test_operator_control.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_operator_control.py`:

```python
def test_recalibrate_drift_reference_records_audit_entry(tmp_path):
    # Uses the existing operator_control_fixture style from the
    # file. Exact fixture name may vary; match the existing pattern.
    store = operator_control_store_fixture(tmp_path)

    result = store.recalibrate_drift_reference(
        snapshot_id="ref-2026-04-21",
        now=datetime(2026, 4, 21, 20, 0, tzinfo=UTC),
    )
    assert result.last_command == "drift_reference_recalibrated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_operator_control.py -k recalibrate_drift_reference -v`

Expected: FAIL on `AttributeError`.

- [ ] **Step 3: Implement**

In `src/tradingx/operator_control.py`, add:

```python
def recalibrate_drift_reference(
    self,
    *,
    snapshot_id: str,
    now: datetime,
) -> OperatorControlState:
    """Record that the operator has asked to recalibrate the
    drift-monitor reference distribution to the given snapshot_id.

    The snapshot file replacement itself happens via
    tradingx.drift.reference.write_reference_distribution_snapshot;
    this method only records the audit entry for the operator
    control surface.
    """
    state = self._write_state(
        now=now,
        last_command="drift_reference_recalibrated",
    )
    # Optionally persist the snapshot_id alongside the audit
    # marker so dashboards can show which reference is active.
    marker = self._root_dir / "drift_reference_recalibration.json"
    marker.write_text(
        json.dumps(
            {
                "snapshot_id": snapshot_id,
                "at_utc": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return state
```

Make sure `json` and `UTC` are already imported; add if missing.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_operator_control.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/operator_control.py tests/unit/test_operator_control.py
git commit -m "feat(operator_control): add recalibrate_drift_reference action"
```

### Task 12: Automation hook — end-of-session `refresh()` + attribution

**Files:**
- Modify: `src/tradingx/automation.py`
- Modify: `tests/unit/test_automation.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_automation.py`:

```python
def test_automation_calls_drift_gateway_refresh_at_end_of_session(
    market_day_automation_fixture,
):
    # Fixture should inject a spy DriftAlarmGateway and a spy
    # SleeveAttributionRecorder. Match the existing fixture
    # factory in this file.
    runner = market_day_automation_fixture.runner
    spy_gateway = market_day_automation_fixture.drift_alarm_gateway
    spy_recorder = market_day_automation_fixture.attribution_recorder

    runner.run_close()  # or whatever the end-of-session method is called

    assert spy_gateway.refresh_call_count == 1
    assert spy_recorder.record_session_call_count == 1
```

Match the existing `MarketDayAutomationRunner` test fixture style; if the fixture doesn't expose close-session hooks cleanly, build them along the existing test-harness pattern.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_automation.py -k drift_gateway_refresh -v`

Expected: FAIL on the runner not calling the gateway.

- [ ] **Step 3: Implement**

**Current state (Codex round-1 plan-review P1 note).** The
existing `MarketDayAutomationRunner.__init__` at
[automation.py:48](/src/tradingx/automation.py:48) does NOT
take a portfolio gateway — it coordinates time and writes
checkpoint artifacts via injected stores and builders, not
broker / portfolio state. The preopen and close steps at
[automation.py:252](/src/tradingx/automation.py:252) and
[automation.py:305](/src/tradingx/automation.py:305) are pure
checkpoint writers. Adding attribution + drift refresh
therefore requires threading a portfolio-state source through
the runner explicitly — this plan amends Task 12 to call that
work out as first-class scope rather than assume a pre-existing
seam.

**Additions to `MarketDayAutomationRunner`:**

1. **New constructor parameter**
   `portfolio_gateway: PortfolioGatewayProtocol | None = None`.
   Defaults to `None` so existing call sites (tests + `__main__`)
   keep working without changes; the runner no-ops the
   attribution + drift-refresh hook when the gateway is absent.
2. **New constructor parameters**
   `drift_alarm_gateway: DriftAlarmGateway | None = None` and
   `attribution_recorder: SleeveAttributionRecorder | None = None`.
   Same default-None pattern.
3. **New private field**
   `self._session_open_portfolio_state: PortfolioState | None = None`
   populated in the preopen step.

```python
from tradingx.runtime_host import PortfolioGatewayProtocol  # already defined in 1.4 runtime_host.py


class MarketDayAutomationRunner:
    def __init__(
        self,
        *,
        # ...existing parameters unchanged...
        portfolio_gateway: PortfolioGatewayProtocol | None = None,
        drift_alarm_gateway: DriftAlarmGateway | None = None,
        attribution_recorder: SleeveAttributionRecorder | None = None,
    ) -> None:
        # ...existing assignments unchanged...
        self._portfolio_gateway = portfolio_gateway
        self._drift_alarm_gateway = drift_alarm_gateway
        self._attribution_recorder = attribution_recorder
        self._session_open_portfolio_state: PortfolioState | None = None
```

**Preopen hook addition (capture the open-time snapshot):**

```python
# Inside the existing preopen step at automation.py:252:
if self._portfolio_gateway is not None:
    self._session_open_portfolio_state = (
        self._portfolio_gateway.get_portfolio_state()
    )
```

**Close hook addition (record attribution + refresh drift):**

```python
# Inside the existing close step at automation.py:305:
if (
    self._attribution_recorder is not None
    and self._portfolio_gateway is not None
    and self._session_open_portfolio_state is not None
):
    close_state = self._portfolio_gateway.get_portfolio_state()
    self._attribution_recorder.record_session(
        trading_day=trading_day,
        open_portfolio_state=self._session_open_portfolio_state,
        close_portfolio_state=close_state,
    )
    self._session_open_portfolio_state = None  # reset for next session

if self._drift_alarm_gateway is not None:
    self._drift_alarm_gateway.refresh()
```

**Wiring at `__main__.py`.** When the runner is constructed by
`build_default_market_day_automation_runner` at
[automation.py:545](/src/tradingx/automation.py:545) (or by
`__main__` if that is where composition happens), pass the
portfolio gateway (already constructed for the runtime host in
1.4) as the new parameter, along with a `DriftAlarmGateway`
instance wired from the drift package and a `SleeveAttributionRecorder`
wired to the activation gateway + `FilesystemArtifactStore`.
Follow the same composition conventions the 1.4 integration
work used for `PortfolioHardHaltController`.

**Fixture update.** The existing test harness at
[test_automation.py:20](/tests/unit/test_automation.py:20) does
not construct a portfolio gateway. For the new test, inject a
minimal `_PortfolioGatewayStub` that returns a canned
`PortfolioState` from both `get_portfolio_state()` calls and a
spy `DriftAlarmGateway` and `SleeveAttributionRecorder` that
record their call counts. Keep the existing non-drift tests
green by leaving `portfolio_gateway=None` (default) on their
constructor calls.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_automation.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/automation.py tests/unit/test_automation.py
git commit -m "feat(automation): invoke DriftAlarmGateway.refresh + SleeveAttributionRecorder at session close"
```

### Task 13: Integration test — drift end-to-end

**Files:**
- Create: `tests/integration/test_drift_end_to_end.py`

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_drift_end_to_end.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from tradingx.drift.blueprint import DriftMonitorBlueprint
from tradingx.drift.gateway import (
    DRIFT_ALARM_CONTROL_TYPE,
    DriftAlarmGateway,
)
from tradingx.drift.reference import (
    build_reference_distribution_snapshot,
)
from tradingx.types import (
    OperatorAlert,
    ReplaySlippageRecord,
    RiskControlEvent,
    SleeveDailyAttributionRecord,
)


def test_drift_alarm_gateway_end_to_end_produces_expected_verdicts():
    # Build a reference snapshot from canned uniform samples.
    feature_samples = {
        "spy_close_over_sma_200": pd.Series([i / 1000 for i in range(1000)]),
    }
    signal_samples = {
        "trend-following-v1": pd.Series([x / 100 for x in range(100)]),
        "vol-target-v1": pd.Series([x / 100 for x in range(100)]),
    }
    snapshot = build_reference_distribution_snapshot(
        reference_snapshot_id="ref-it",
        blueprint_id="bp-it",
        feature_samples_by_name=feature_samples,
        signal_samples_by_sleeve_id=signal_samples,
        reference_window_start_utc=datetime(2023, 1, 1, tzinfo=UTC),
        reference_window_end_utc=datetime(2024, 1, 1, tzinfo=UTC),
    )

    # Readers: one returns identical samples → info; another returns
    # drifted samples → critical.
    class _FeatureReader:
        def live_samples(self, feature_name, *, window_days):
            # Pathological drift: live samples all in one bin.
            return pd.Series([0.55] * 2000)

    class _SignalReader:
        def live_samples(self, sleeve_id, *, window_days):
            if sleeve_id == "trend-following-v1":
                # Identical to reference → info.
                return pd.Series([x / 100 for x in range(100)])
            # vol-target-v1 shifted → critical.
            return pd.Series([5.0] * 100)

    class _ReplayReader:
        def recent_records(self, *, window_days):
            return ()

    class _AttributionReader:
        def records_for_sleeve(self, sleeve_id, *, window_days):
            return ()

    class _ReferenceReturnsReader:
        def returns_for_sleeve(self, sleeve_id):
            return ()

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

    # PSI should be critical on the shifted feature.
    psi_verdicts = tuple(v for v in verdicts if v.monitor_id.startswith("psi::"))
    assert any(v.severity == "critical" for v in psi_verdicts)

    # trend-following-v1 KS info; vol-target-v1 KS critical.
    ks_trend = next(v for v in verdicts if v.monitor_id == "ks::trend-following-v1")
    ks_vol = next(v for v in verdicts if v.monitor_id == "ks::vol-target-v1")
    assert ks_trend.severity == "info"
    assert ks_vol.severity == "critical"

    # has_alarm reflects critical verdicts:
    # - PSI critical fires for any portfolio-level monitor → both sleeves affected.
    # - KS critical on vol-target-v1 fires only for vol-target-v1.
    assert gateway.has_alarm(sleeve_id="trend-following-v1") is True  # PSI critical
    assert gateway.has_alarm(sleeve_id="vol-target-v1") is True  # PSI + KS critical

    # One RiskControlEvent per verdict.
    assert len(risk_events) == len(verdicts)
    assert all(e.control_type == DRIFT_ALARM_CONTROL_TYPE for e in risk_events)

    # Operator alerts emitted only for warning + critical.
    assert all(
        a.severity in {"warning", "critical"}
        and a.category == DRIFT_ALARM_CONTROL_TYPE
        for a in alerts
    )
```

- [ ] **Step 2: Run the integration test**

Run: `uv run pytest tests/integration/test_drift_end_to_end.py -v`

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_drift_end_to_end.py
git commit -m "test(drift): add end-to-end integration for DriftAlarmGateway"
```

### Task 14: GATES-0001 Gate 3 note + INDEX bump + closing pass

**Files:**
- Modify: `docs/validation/acceptance_gates.md`
- Modify: `docs/INDEX.md`

- [ ] **Step 1: Update GATES-0001**

Front-matter: bump `version: 1.2.0` → `version: 1.2.1`; set `supersedes: GATES-0001@1.2.0`. No criterion changes.

In Gate 3 "Primary evidence" block, add a bullet (Codex
round-1 plan-review P2 fix: the text now matches the actual
`RiskControlEvent` + `OperatorAlert` schemas; the earlier
"monitor metadata in details" wording referenced a field that
does not exist on `RiskControlEvent`):

> - `ExecutionQualityDriftMonitor` alarms. Evidence is carried by
>   two artifacts that the `DriftAlarmGateway` emits at each
>   `refresh()`: (a) a `RiskControlEvent` with
>   `control_type = "portfolio_drift_alarm"` and `severity`
>   matching the verdict (persisted at `{artifact_root}/risk_events/`);
>   (b) for warning/critical verdicts, a matching `OperatorAlert`
>   with `category = "portfolio_drift_alarm"` whose `summary`
>   field carries the monitor id + severity + observed
>   divergence ratio (persisted at `{artifact_root}/operator_alerts/`).
>   Both artifacts together reinforce the Gate 3 "realized
>   slippage ≤ 1.5× backtest assumption" evidence; alarms fire
>   at 1.5× warning / 2.0× critical on the rolling mean
>   `|divergence_ratio|` of `ReplaySlippageRecord` over the
>   configured window.

- [ ] **Step 2: Update INDEX**

Bump INDEX front-matter (e.g., 1.2.30 → 1.2.31). Update the GATES-0001 row version to 1.2.1.

- [ ] **Step 3: Validate**

Run: `python3 scripts/check_index.py`

Expected: `INDEX validation passed.`

- [ ] **Step 4: Commit**

```bash
git add docs/validation/acceptance_gates.md docs/INDEX.md
git commit -m "gov(gates): note ExecutionQualityDriftMonitor in Gate 3 evidence (GATES-0001 1.2.1)"
```

### Task 15: Full regression + lint + typecheck + index + validate

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
git commit -m "chore: formatting fixups after tranche 1.5"
```

Skip if no fixups needed.

---

## Self-review

### Spec coverage

- DESIGN-0016 W1 (`DriftMonitorBlueprint`, `DriftThresholds`): Task 1.
- DESIGN-0016 W2 (`ReferenceDistributionSnapshot` + build/load/write): Task 2.
- DESIGN-0016 W3 (PSI): Task 3.
- DESIGN-0016 W4 (KS): Task 4.
- DESIGN-0016 W5 (execution drift): Task 5.
- DESIGN-0016 W6 (`SleeveDailyAttributionRecord` + recorder): Tasks 6–7.
- DESIGN-0016 W7 (P&L divergence + backtest-reference artifact): Task 8.
- DESIGN-0016 W8 (`DriftAlarmGateway`): Task 9.
- DESIGN-0016 W9 (`LIVE_DAILY_RETURNS` wiring): Task 10.
- DESIGN-0016 W10 (operator action + automation hook + GATES + regression): Tasks 11–15.

### Placeholder scan

No TBD / TODO / "implement later" in production code. A small number of fixture-name placeholders flagged for the implementer to match existing repo conventions (test fixture factories in `test_automation.py` and `test_operator_control.py`) — test-file concerns, not production code.

### Type consistency

- `DriftMonitorBlueprint` + `DriftThresholds` from Task 1 consumed by every monitor computation and by `DriftAlarmGateway`.
- `FeatureDistribution`, `SignalDistribution`, `ReferenceDistributionSnapshot` from Task 2 consumed by Tasks 3, 4, 9.
- `compute_population_stability_index`, `compute_kolmogorov_smirnov`, `compute_execution_drift_ratio`, `compute_live_vs_backtest_pnl_divergence` are pure functions invoked only by `DriftAlarmGateway`.
- `SleeveDailyAttributionRecord` from Task 6 consumed by Task 7's recorder, Task 8's P&L divergence, Task 10's live-returns reader, and the gateway's attribution reader path.
- `DRIFT_ALARM_CONTROL_TYPE = "portfolio_drift_alarm"` from Task 9 is the canonical alert category + RiskControlEvent control_type string. No other place in the codebase duplicates the string.

### Open judgment calls left to the implementer

1. **`ActivationGatewayProtocol.get_active_candidate`.** Task 7 describes the method signature the recorder expects. If the existing activation gateway doesn't already expose it, add a thin helper that resolves the latest activation's `strategy_id` → `StrategyCandidate` via `build_mandatory_candidate_registry()`. Keep the protocol surface stable.
2. **Automation hook placement.** Task 12 describes the logical placement (session-close step); match the existing `MarketDayAutomationRunner` checkpoint pattern and fixture style. If adding two optional constructor parameters feels wrong, a small `DriftAutomationHook` dataclass that bundles both is an acceptable alternative.
3. **Fixture-name placeholders** in `test_automation.py` and `test_operator_control.py` — match whatever conventions already exist. The plan identifies the required behaviors; the fixture-wiring is an implementer match.
4. **`recalibrate_drift_reference` audit marker.** Task 11 proposes a new `drift_reference_recalibration.json` marker alongside the existing `clearance_request` marker in the operator control store. If a different location aligns better with the existing operator audit log, move it — the method's public surface is the stable contract.
5. **`scipy` dependency declaration.** If `uv sync` does not already pull scipy transitively through `empyrical-reloaded`, add it explicitly to `pyproject.toml` alongside Task 4.

### Execution handoff

Plan is for Codex to execute. No subagent-driven or inline execution invocation from this session. Same pattern as tranches 1.1–1.4.
