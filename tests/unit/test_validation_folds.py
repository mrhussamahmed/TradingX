from __future__ import annotations

import pytest

from tradingx.validation_folds import purged_kfold_indices


def test_purged_kfold_splits_cover_all_samples() -> None:
    splits = purged_kfold_indices(n_samples=100, k=5, embargo_days=0)
    test_indices = set()
    for _, test in splits:
        test_indices.update(test)
    assert test_indices == set(range(100))
    assert len(splits) == 5


def test_purged_kfold_no_train_test_overlap() -> None:
    splits = purged_kfold_indices(n_samples=100, k=5, embargo_days=0)
    for train, test in splits:
        assert not (set(train) & set(test))


def test_purged_kfold_deterministic() -> None:
    a = purged_kfold_indices(n_samples=100, k=5, embargo_days=0)
    b = purged_kfold_indices(n_samples=100, k=5, embargo_days=0)
    assert a == b
