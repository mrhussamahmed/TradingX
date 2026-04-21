from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from tradingx.drift.psi import compute_population_stability_index
from tradingx.drift.reference import FeatureDistribution


def _uniform_ref(n_bins: int = 10) -> FeatureDistribution:
    edges = tuple(Decimal(str(index / n_bins)) for index in range(n_bins + 1))
    proportions = tuple(Decimal("1") / Decimal(n_bins) for _ in range(n_bins))
    return FeatureDistribution(
        feature_name="foo",
        bin_edges=edges,
        bin_proportions=proportions,
        observation_count=1000,
    )


def test_psi_zero_for_matching_distribution() -> None:
    rng = np.random.default_rng(seed=0)
    live = pd.Series(rng.uniform(0.0, 1.0, size=10_000))
    psi = compute_population_stability_index(
        reference_distribution=_uniform_ref(),
        live_samples=live,
    )
    assert abs(psi) < Decimal("0.05")


def test_psi_breaches_critical_threshold_for_significant_shift() -> None:
    psi = compute_population_stability_index(
        reference_distribution=_uniform_ref(),
        live_samples=pd.Series([0.05] * 9_000 + [0.5] * 1_000),
    )
    assert psi > Decimal("0.25")


def test_psi_empty_live_samples_raises() -> None:
    with pytest.raises(ValueError, match="live_samples"):
        compute_population_stability_index(
            reference_distribution=_uniform_ref(),
            live_samples=pd.Series([], dtype=float),
        )


def test_psi_clips_samples_outside_reference_range() -> None:
    live = pd.Series(
        np.concatenate(
            [
                np.linspace(-10.0, -1.0, 500),
                np.linspace(0.0, 1.0, 500),
                np.linspace(2.0, 10.0, 500),
            ]
        )
    )
    psi = compute_population_stability_index(
        reference_distribution=_uniform_ref(),
        live_samples=live,
    )
    assert psi.is_finite()
    assert psi >= Decimal("0")


def test_psi_handles_zero_proportion_live_bins_via_epsilon() -> None:
    psi = compute_population_stability_index(
        reference_distribution=_uniform_ref(),
        live_samples=pd.Series([0.55] * 1000),
        epsilon=1e-6,
    )
    assert psi.is_finite()
    assert psi > Decimal("0")
