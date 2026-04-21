"""Purged/embargoed k-fold cross-validation splitter."""

from __future__ import annotations


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


__all__ = ("purged_kfold_indices",)
