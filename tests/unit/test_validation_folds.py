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


def test_purged_kfold_embargo_respected() -> None:
    splits = purged_kfold_indices(n_samples=100, k=5, embargo_days=3)
    for train, test in splits:
        if not test:
            continue
        test_end = max(test) + 1
        forbidden_train = set(range(test_end, min(100, test_end + 3)))
        assert not (set(train) & forbidden_train), (
            f"Training set leaked into embargo zone: " f"{set(train) & forbidden_train}"
        )


def test_purged_kfold_rejects_insufficient_samples() -> None:
    with pytest.raises(ValueError, match="too small"):
        purged_kfold_indices(n_samples=5, k=5, embargo_days=0)


def test_purged_kfold_rejects_invalid_k() -> None:
    with pytest.raises(ValueError, match="k must be >= 2"):
        purged_kfold_indices(n_samples=100, k=1, embargo_days=0)


def test_purged_kfold_rejects_negative_embargo() -> None:
    with pytest.raises(ValueError, match="embargo_days"):
        purged_kfold_indices(n_samples=100, k=5, embargo_days=-1)
