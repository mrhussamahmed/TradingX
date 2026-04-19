from __future__ import annotations

import importlib

import pytest


def test_day0_fake_strategy_and_learning_symbols_are_removed() -> None:
    strategy_module = importlib.import_module("tradingx.strategy")
    evaluation_module = importlib.import_module("tradingx.evaluation")
    runtime_host_module = importlib.import_module("tradingx.runtime_host")
    types_module = importlib.import_module("tradingx.types")

    assert not hasattr(strategy_module, "build_candidate_return_series")
    assert not hasattr(evaluation_module, "NautilusReplayEvaluationAdapter")
    assert not hasattr(
        runtime_host_module.LocalRuntimeHostManager,
        "generate_learning_proposal",
    )
    assert not hasattr(types_module, "ModelWeightProposal")


def test_day0_learning_module_is_removed() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("tradingx.learning")
