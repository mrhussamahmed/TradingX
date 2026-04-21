"""Two-sample Kolmogorov-Smirnov helpers."""

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
    result = stats.ks_2samp(
        [float(value) for value in reference_samples],
        [float(value) for value in live_samples.dropna().astype(float)],
    )
    return KSResult(
        statistic=Decimal(str(float(result.statistic))),
        p_value=Decimal(str(float(result.pvalue))),
    )


__all__ = ("KSResult", "compute_kolmogorov_smirnov")
