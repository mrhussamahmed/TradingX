"""Purged/embargoed k-fold and combinatorial cross-validation splitters."""

from __future__ import annotations

from itertools import combinations


def purged_kfold_indices(
    *,
    n_samples: int,
    k: int,
    embargo_days: int = 5,
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    if k < 2:
        raise ValueError("k must be >= 2.")
    if embargo_days < 0:
        raise ValueError("embargo_days must be >= 0.")
    if n_samples < k * 2 + embargo_days:
        raise ValueError(
            f"n_samples={n_samples} is too small for k={k} and "
            f"embargo_days={embargo_days}; need at least "
            f"{k * 2 + embargo_days}."
        )

    fold_size = n_samples // k
    splits: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    for fold_idx in range(k):
        test_start = fold_idx * fold_size
        test_end = (fold_idx + 1) * fold_size if fold_idx < k - 1 else n_samples
        test = tuple(range(test_start, test_end))
        embargo_end = min(n_samples, test_end + embargo_days)
        train = tuple(i for i in range(n_samples) if i < test_start or i >= embargo_end)
        splits.append((train, test))
    return tuple(splits)


def generate_cpcv_paths(
    *,
    n_samples: int,
    n_groups: int = 10,
    test_group_count: int = 2,
    embargo_days: int = 5,
    label_horizon: int = 1,
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    if n_groups < 4:
        raise ValueError(f"n_groups must be >= 4, got {n_groups}.")
    if not (2 <= test_group_count < n_groups):
        raise ValueError(
            "test_group_count must satisfy 2 <= test_group_count < n_groups; "
            f"got test_group_count={test_group_count} with n_groups={n_groups}."
        )
    if label_horizon < 1:
        raise ValueError(f"label_horizon must be >= 1, got {label_horizon}.")
    if label_horizon > 1:
        raise ValueError(
            "label_horizon > 1 is not yet supported by generate_cpcv_paths."
        )
    if embargo_days < label_horizon:
        raise ValueError(
            f"embargo_days={embargo_days} must be >= label_horizon={label_horizon}."
        )
    min_required = n_groups * (2 + label_horizon + embargo_days)
    if n_samples < min_required:
        raise ValueError(
            f"n_samples={n_samples} is too small; need at least {min_required} "
            f"for n_groups={n_groups}, label_horizon={label_horizon}, "
            f"embargo_days={embargo_days}."
        )

    fold_size = n_samples // n_groups
    group_ranges = tuple(
        range(
            group_index * fold_size,
            (group_index + 1) * fold_size if group_index < n_groups - 1 else n_samples,
        )
        for group_index in range(n_groups)
    )
    paths: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    for test_groups in combinations(range(n_groups), test_group_count):
        test_indices = tuple(
            index for group_index in test_groups for index in group_ranges[group_index]
        )
        test_index_set = set(test_indices)
        embargo_indices = {
            index
            for group_index in test_groups
            for index in range(
                group_ranges[group_index].stop,
                min(n_samples, group_ranges[group_index].stop + embargo_days),
            )
        }
        train_indices = tuple(
            index
            for index in range(n_samples)
            if index not in test_index_set and index not in embargo_indices
        )
        paths.append((train_indices, test_indices))
    return tuple(paths)


__all__ = ("generate_cpcv_paths", "purged_kfold_indices")
