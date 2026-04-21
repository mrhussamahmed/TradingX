"""Reference-distribution snapshot helpers for drift monitoring."""

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
    generated_at_utc: datetime | None = None,
) -> ReferenceDistributionSnapshot:
    feature_distributions = tuple(
        _build_feature_distribution(name, samples, n_bins=n_bins)
        for name, samples in sorted(feature_samples_by_name.items())
    )
    signal_distributions = tuple(
        _build_signal_distribution(sleeve_id, samples)
        for sleeve_id, samples in sorted(signal_samples_by_sleeve_id.items())
    )
    return ReferenceDistributionSnapshot(
        reference_snapshot_id=reference_snapshot_id,
        generated_at_utc=(generated_at_utc or datetime.now(UTC)).astimezone(UTC),
        blueprint_id=blueprint_id,
        feature_distributions=feature_distributions,
        signal_distributions=signal_distributions,
        reference_window_start_utc=reference_window_start_utc.astimezone(UTC),
        reference_window_end_utc=reference_window_end_utc.astimezone(UTC),
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
        "reference_window_start_utc": snapshot.reference_window_start_utc.astimezone(
            UTC
        ).isoformat(),
        "reference_window_end_utc": snapshot.reference_window_end_utc.astimezone(
            UTC
        ).isoformat(),
        "feature_distributions": [
            {
                "feature_name": distribution.feature_name,
                "bin_edges": [str(edge) for edge in distribution.bin_edges],
                "bin_proportions": [
                    str(value) for value in distribution.bin_proportions
                ],
                "observation_count": distribution.observation_count,
            }
            for distribution in snapshot.feature_distributions
        ],
        "signal_distributions": [
            {
                "sleeve_id": distribution.sleeve_id,
                "observed_samples": [
                    str(value) for value in distribution.observed_samples
                ],
                "observation_count": distribution.observation_count,
            }
            for distribution in snapshot.signal_distributions
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_reference_distribution_snapshot(path: Path) -> ReferenceDistributionSnapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ReferenceDistributionSnapshot(
        reference_snapshot_id=str(payload["reference_snapshot_id"]),
        generated_at_utc=_parse_iso(payload["generated_at_utc"]),
        blueprint_id=str(payload["blueprint_id"]),
        feature_distributions=tuple(
            FeatureDistribution(
                feature_name=str(distribution["feature_name"]),
                bin_edges=tuple(
                    Decimal(str(edge)) for edge in distribution["bin_edges"]
                ),
                bin_proportions=tuple(
                    Decimal(str(value)) for value in distribution["bin_proportions"]
                ),
                observation_count=int(distribution["observation_count"]),
            )
            for distribution in payload["feature_distributions"]
        ),
        signal_distributions=tuple(
            SignalDistribution(
                sleeve_id=str(distribution["sleeve_id"]),
                observed_samples=tuple(
                    Decimal(str(value)) for value in distribution["observed_samples"]
                ),
                observation_count=int(distribution["observation_count"]),
            )
            for distribution in payload["signal_distributions"]
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
    values = samples.dropna().astype(float).to_numpy()
    if values.size == 0:
        raise ValueError(f"feature samples for {feature_name} must not be empty")
    quantile_levels = np.linspace(0.0, 1.0, n_bins + 1)
    bin_edges_np = np.quantile(values, quantile_levels)
    for index in range(1, len(bin_edges_np)):
        if bin_edges_np[index] <= bin_edges_np[index - 1]:
            bin_edges_np[index] = bin_edges_np[index - 1] + 1e-12
    hist, _ = np.histogram(values, bins=bin_edges_np)
    total = int(hist.sum())
    proportions = (
        tuple(Decimal("0") for _ in range(n_bins))
        if total == 0
        else tuple(Decimal(str(float(count) / float(total))) for count in hist)
    )
    return FeatureDistribution(
        feature_name=feature_name,
        bin_edges=tuple(Decimal(str(float(edge))) for edge in bin_edges_np),
        bin_proportions=proportions,
        observation_count=int(values.size),
    )


def _build_signal_distribution(
    sleeve_id: str,
    samples: pd.Series,
) -> SignalDistribution:
    clean = samples.dropna().astype(float)
    return SignalDistribution(
        sleeve_id=sleeve_id,
        observed_samples=tuple(Decimal(str(float(value))) for value in clean.tolist()),
        observation_count=int(clean.size),
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
