from __future__ import annotations

import math

import pytest

from tradingx.validation_folds import generate_cpcv_paths


def test_generate_cpcv_paths_emits_expected_path_count() -> None:
    paths = generate_cpcv_paths(
        n_samples=1000,
        n_groups=10,
        test_group_count=2,
        embargo_days=5,
        label_horizon=1,
    )

    assert len(paths) == math.comb(10, 2)


def test_generate_cpcv_paths_has_disjoint_train_and_test_indices() -> None:
    paths = generate_cpcv_paths(
        n_samples=1000,
        n_groups=10,
        test_group_count=2,
        embargo_days=5,
        label_horizon=1,
    )

    for train_indices, test_indices in paths:
        assert not (set(train_indices) & set(test_indices))


def test_generate_cpcv_paths_respects_embargo_window() -> None:
    paths = generate_cpcv_paths(
        n_samples=1000,
        n_groups=10,
        test_group_count=2,
        embargo_days=5,
        label_horizon=1,
    )

    for train_indices, test_indices in paths:
        test_end = max(test_indices)
        for index in range(test_end + 1, min(1000, test_end + 6)):
            assert index not in train_indices


def test_generate_cpcv_paths_is_deterministic() -> None:
    args = dict(
        n_samples=1000,
        n_groups=10,
        test_group_count=2,
        embargo_days=5,
        label_horizon=1,
    )

    assert generate_cpcv_paths(**args) == generate_cpcv_paths(**args)


def test_generate_cpcv_paths_rejects_k_equal_1() -> None:
    with pytest.raises(ValueError, match="test_group_count"):
        generate_cpcv_paths(
            n_samples=1000,
            n_groups=10,
            test_group_count=1,
            embargo_days=5,
            label_horizon=1,
        )


def test_generate_cpcv_paths_rejects_n_groups_below_4() -> None:
    with pytest.raises(ValueError, match="n_groups"):
        generate_cpcv_paths(
            n_samples=1000,
            n_groups=3,
            test_group_count=2,
            embargo_days=5,
            label_horizon=1,
        )


def test_generate_cpcv_paths_rejects_embargo_smaller_than_label_horizon() -> None:
    with pytest.raises(ValueError, match="embargo_days"):
        generate_cpcv_paths(
            n_samples=1000,
            n_groups=10,
            test_group_count=2,
            embargo_days=0,
            label_horizon=1,
        )


def test_generate_cpcv_paths_rejects_too_few_samples() -> None:
    with pytest.raises(ValueError, match="n_samples"):
        generate_cpcv_paths(
            n_samples=20,
            n_groups=10,
            test_group_count=2,
            embargo_days=5,
            label_horizon=1,
        )


def test_generate_cpcv_paths_sample_appears_in_expected_test_count() -> None:
    n_samples = 1000
    n_groups = 10
    test_group_count = 2
    paths = generate_cpcv_paths(
        n_samples=n_samples,
        n_groups=n_groups,
        test_group_count=test_group_count,
        embargo_days=5,
        label_horizon=1,
    )

    counts = {index: 0 for index in range(n_samples)}
    for _, test_indices in paths:
        for index in test_indices:
            counts[index] += 1

    assert all(
        count == math.comb(n_groups - 1, test_group_count - 1)
        for count in counts.values()
    )


def test_generate_cpcv_paths_uses_lexicographic_path_order() -> None:
    paths = generate_cpcv_paths(
        n_samples=1000,
        n_groups=10,
        test_group_count=2,
        embargo_days=5,
        label_horizon=1,
    )

    fold_size = 1000 // 10
    first_test = paths[0][1]
    last_test = paths[-1][1]

    assert first_test[0] == 0
    assert first_test[-1] == (2 * fold_size) - 1
    assert last_test[0] == 8 * fold_size
    assert last_test[-1] == 999
