"""Probability-of-backtest-overfitting helpers."""

from __future__ import annotations

import hashlib
import math
import random
import statistics
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.types import CPCVTrialRecord, PBOReport

DEFAULT_MIN_COHORT_SIZE = 50
DEFAULT_MIN_PATHS = 20
DEFAULT_N_SPLITS = 10_000
DEFAULT_RANDOM_SEED = 2026
_LOGIT_PERCENTILES = (
    Decimal("5"),
    Decimal("25"),
    Decimal("50"),
    Decimal("75"),
    Decimal("95"),
)
_METRIC_NAME = "lo_adjusted_sharpe"


class InsufficientCPCVCohortError(ValueError):
    """Cohort or path count below the reliability threshold."""


class MixedCohortWindowError(ValueError):
    """CPCV records span more than one cohort window."""


def compute_pbo(
    *,
    cpcv_records: tuple[CPCVTrialRecord, ...],
    min_cohort_size: int = DEFAULT_MIN_COHORT_SIZE,
    min_paths: int = DEFAULT_MIN_PATHS,
    random_seed: int = DEFAULT_RANDOM_SEED,
    evaluation_id: str | None = None,
    generated_at_utc: datetime | None = None,
) -> PBOReport:
    if not cpcv_records:
        raise InsufficientCPCVCohortError("cpcv_records is empty.")

    cohort_window_ids = {record.cohort_window_id for record in cpcv_records}
    if len(cohort_window_ids) != 1:
        raise MixedCohortWindowError(
            "cpcv_records span multiple cohort windows: "
            f"{sorted(cohort_window_ids)!r}"
        )

    strategies = sorted({record.strategy_config_id for record in cpcv_records})
    paths = sorted({record.cpcv_path_id for record in cpcv_records})
    if len(strategies) < min_cohort_size:
        raise InsufficientCPCVCohortError(
            f"cohort_size={len(strategies)} < min_cohort_size={min_cohort_size}"
        )
    if len(paths) < min_paths:
        raise InsufficientCPCVCohortError(
            f"n_paths={len(paths)} < min_paths={min_paths}"
        )

    matrix = {
        (record.cpcv_path_id, record.strategy_config_id): record.out_of_sample_sharpe
        for record in cpcv_records
    }
    for path_id in paths:
        for strategy_config_id in strategies:
            if (path_id, strategy_config_id) not in matrix:
                raise InsufficientCPCVCohortError(
                    "missing matrix cell for "
                    f"(cpcv_path_id={path_id}, "
                    f"strategy_config_id={strategy_config_id})"
                )

    random_state = random.Random(random_seed)
    in_sample_size = len(paths) // 2
    clamp_low = 1.0 / (len(strategies) + 1)
    clamp_high = len(strategies) / (len(strategies) + 1)
    logit_distribution: list[float] = []

    for _ in range(DEFAULT_N_SPLITS):
        in_sample_paths = frozenset(random_state.sample(paths, in_sample_size))
        out_of_sample_paths = [
            path_id for path_id in paths if path_id not in in_sample_paths
        ]
        in_sample_means: dict[str, float] = {}
        out_of_sample_means: dict[str, float] = {}
        for strategy_config_id in strategies:
            in_sample_means[strategy_config_id] = statistics.fmean(
                float(matrix[(path_id, strategy_config_id)])
                for path_id in paths
                if path_id in in_sample_paths
            )
            out_of_sample_means[strategy_config_id] = statistics.fmean(
                float(matrix[(path_id, strategy_config_id)])
                for path_id in out_of_sample_paths
            )

        winner = max(in_sample_means, key=in_sample_means.__getitem__)
        winner_out_of_sample = out_of_sample_means[winner]
        rank_fraction = _average_rank_fraction(
            values=tuple(out_of_sample_means.values()),
            target_value=winner_out_of_sample,
        )
        rank_fraction = max(min(rank_fraction, clamp_high), clamp_low)
        logit_distribution.append(math.log(rank_fraction / (1.0 - rank_fraction)))

    pbo_value = Decimal(
        str(
            sum(1 for logit_value in logit_distribution if logit_value <= 0.0)
            / len(logit_distribution)
        )
    )
    sorted_logits = tuple(sorted(logit_distribution))
    sample = cpcv_records[0]
    resolved_evaluation_id = evaluation_id or _default_evaluation_id(
        cpcv_records=cpcv_records,
        random_seed=random_seed,
    )

    return PBOReport(
        report_id=f"pbo-{resolved_evaluation_id}",
        evaluation_id=resolved_evaluation_id,
        cohort_window_id=sample.cohort_window_id,
        cohort_size=len(strategies),
        n_paths=len(paths),
        n_splits_sampled=DEFAULT_N_SPLITS,
        pbo_value=pbo_value,
        logit_distribution_percentiles=tuple(
            (percentile, _percentile(sorted_logits, percentile))
            for percentile in _LOGIT_PERCENTILES
        ),
        cpcv_config_fingerprint=(
            f"N={sample.n_groups},"
            f"k={sample.test_group_count},"
            f"h={sample.embargo_days},"
            f"L={sample.label_horizon}"
        ),
        metric_name=_METRIC_NAME,
        random_seed=random_seed,
        generated_at_utc=generated_at_utc or datetime.now(UTC),
    )


def cohort_window_id_for(
    *,
    window_start_utc: datetime,
    window_end_utc: datetime,
    cpcv_config_fingerprint: str,
) -> str:
    payload = (
        f"{window_start_utc.isoformat()}"
        f"|{window_end_utc.isoformat()}"
        f"|{cpcv_config_fingerprint}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"cohort-{digest[:16]}"


def _default_evaluation_id(
    *,
    cpcv_records: tuple[CPCVTrialRecord, ...],
    random_seed: int,
) -> str:
    payload = "|".join(
        [
            cpcv_records[0].cohort_window_id,
            str(random_seed),
            *sorted(record.trial_id for record in cpcv_records),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"eval-{digest[:16]}"


def _average_rank_fraction(*, values: tuple[float, ...], target_value: float) -> float:
    less_than = sum(1 for value in values if value < target_value)
    equal_to = sum(1 for value in values if value == target_value)
    return (less_than + 0.5 * equal_to + 0.5) / len(values)


def _percentile(values: tuple[float, ...], percentile: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    rank = (float(percentile) / 100.0) * (len(values) - 1)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return Decimal(str(values[lower]))
    fraction = rank - lower
    return Decimal(str(values[lower] * (1.0 - fraction) + values[upper] * fraction))


__all__ = (
    "DEFAULT_MIN_COHORT_SIZE",
    "DEFAULT_MIN_PATHS",
    "DEFAULT_N_SPLITS",
    "DEFAULT_RANDOM_SEED",
    "InsufficientCPCVCohortError",
    "MixedCohortWindowError",
    "cohort_window_id_for",
    "compute_pbo",
)
