from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from tradingx.drift.ks import KSResult, compute_kolmogorov_smirnov


def test_identical_distributions_p_value_near_one() -> None:
    rng = np.random.default_rng(seed=0)
    shared = rng.normal(size=1000).tolist()
    result = compute_kolmogorov_smirnov(
        reference_samples=tuple(Decimal(str(value)) for value in shared),
        live_samples=pd.Series(shared),
    )
    assert isinstance(result, KSResult)
    assert result.p_value > Decimal("0.9")
    assert result.statistic <= Decimal("0.1")


def test_shifted_distributions_p_value_below_critical() -> None:
    rng = np.random.default_rng(seed=1)
    reference = rng.normal(size=1000).tolist()
    live = (rng.normal(size=1000) + 1.0).tolist()
    result = compute_kolmogorov_smirnov(
        reference_samples=tuple(Decimal(str(value)) for value in reference),
        live_samples=pd.Series(live),
    )
    assert result.p_value < Decimal("0.05")


def test_empty_live_samples_raises() -> None:
    with pytest.raises(ValueError, match="live_samples"):
        compute_kolmogorov_smirnov(
            reference_samples=(Decimal("1"), Decimal("2"), Decimal("3")),
            live_samples=pd.Series([], dtype=float),
        )


def test_empty_reference_samples_raises() -> None:
    with pytest.raises(ValueError, match="reference_samples"):
        compute_kolmogorov_smirnov(
            reference_samples=(),
            live_samples=pd.Series([1.0, 2.0]),
        )


def test_statistic_and_p_value_bounded() -> None:
    rng = np.random.default_rng(seed=2)
    result = compute_kolmogorov_smirnov(
        reference_samples=tuple(Decimal(str(value)) for value in rng.normal(size=200)),
        live_samples=pd.Series(rng.normal(loc=0.5, size=200)),
    )
    assert Decimal("0") <= result.statistic <= Decimal("1")
    assert Decimal("0") <= result.p_value <= Decimal("1")
