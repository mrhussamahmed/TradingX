"""Population Stability Index helpers."""

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
    edges_with_inf = [-math.inf] + edges[1:-1] + [math.inf]
    live_values = np.asarray(live_samples.dropna().astype(float))
    if live_values.size == 0:
        raise ValueError("live_samples must contain at least one non-null sample")
    live_hist, _ = np.histogram(live_values, bins=edges_with_inf)
    total = int(live_hist.sum())
    if total == 0:
        return Decimal("0")
    live_props = live_hist.astype(float) / float(total)
    ref_props = np.asarray(
        [float(value) for value in reference_distribution.bin_proportions],
        dtype=float,
    )
    live_clamped = np.maximum(live_props, epsilon)
    ref_clamped = np.maximum(ref_props, epsilon)
    psi_value = float(
        np.sum((live_clamped - ref_clamped) * np.log(live_clamped / ref_clamped))
    )
    return Decimal(str(psi_value))


__all__ = ("compute_population_stability_index",)
