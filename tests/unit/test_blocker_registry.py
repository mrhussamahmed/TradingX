from __future__ import annotations

from pathlib import Path

import pytest

from tradingx.promotion import (
    BLOCKER_REGISTRY,
    NOT_RUNTIME_APPLICABLE,
    Blocker,
    PromotionState,
    blocker_registry_coverage_rows,
    strictest_state_cap,
    validate_blocker_registry_coverage,
)


def test_registry_seeds_roadmap_deterministic_and_provisional_codes() -> None:
    expected = {
        "authority_artifact_invalid": PromotionState.DISABLED,
        "ledger_key_worm_controls_missing": PromotionState.DISABLED,
        "state_action_contract_missing": PromotionState.DISABLED,
        "replay_path_missing": PromotionState.RESEARCH_ONLY,
        "capacity_extrapolation_risk": PromotionState.PAPER_SHADOW,
        "unsupported_side": PromotionState.RESEARCH_ONLY,
        "short_support_missing": PromotionState.RESEARCH_ONLY,
        "legacy_statistical_evidence": PromotionState.PAPER_SHADOW,
        "dependency_scope_unresolved": PromotionState.PAPER_SHADOW,
    }

    for code, max_state in expected.items():
        assert BLOCKER_REGISTRY[code].max_state == max_state


def test_registry_coverage_requires_full_enforcement_mapping() -> None:
    incomplete = dict(BLOCKER_REGISTRY)
    record = incomplete["replay_path_missing"]
    incomplete["replay_path_missing"] = record.without_runtime_mapping()

    with pytest.raises(ValueError, match="replay_path_missing"):
        validate_blocker_registry_coverage(incomplete)


def test_registry_coverage_requires_real_evaluator_red_test_and_outputs() -> None:
    incomplete = dict(BLOCKER_REGISTRY)
    record = incomplete["replay_path_missing"]
    incomplete["replay_path_missing"] = record.__class__(
        **{**record.__dict__, "evaluator": "evaluate_missing_blocker_for_test"}
    )
    with pytest.raises(ValueError, match="evaluate_missing_blocker_for_test"):
        validate_blocker_registry_coverage(incomplete)

    incomplete = dict(BLOCKER_REGISTRY)
    record = incomplete["replay_path_missing"]
    incomplete["replay_path_missing"] = record.__class__(
        **{**record.__dict__, "red_test": "test_missing_blocker_for_registry"}
    )
    with pytest.raises(ValueError, match="test_missing_blocker_for_registry"):
        validate_blocker_registry_coverage(incomplete)

    incomplete = dict(BLOCKER_REGISTRY)
    record = incomplete["replay_path_missing"]
    incomplete["replay_path_missing"] = record.__class__(
        **{**record.__dict__, "cli_output": "promotion-check.missing_field"}
    )
    with pytest.raises(ValueError, match="promotion-check.missing_field"):
        validate_blocker_registry_coverage(incomplete)


def test_registry_coverage_rejects_not_runtime_for_emitted_blocker_fields() -> None:
    incomplete = dict(BLOCKER_REGISTRY)
    record = incomplete["utility_definition_missing"]
    incomplete["utility_definition_missing"] = record.__class__(
        **{
            **record.__dict__,
            "evaluator": NOT_RUNTIME_APPLICABLE,
            "red_test": NOT_RUNTIME_APPLICABLE,
            "fixture": NOT_RUNTIME_APPLICABLE,
            "cli_output": NOT_RUNTIME_APPLICABLE,
            "web_report_field": NOT_RUNTIME_APPLICABLE,
        }
    )

    with pytest.raises(ValueError, match="utility_definition_missing"):
        validate_blocker_registry_coverage(incomplete)


def test_coverage_matrix_has_schema_to_runtime_trace_for_each_blocker() -> None:
    rows = blocker_registry_coverage_rows()

    assert any(row["blocker"] == "authority_artifact_invalid" for row in rows)
    emitted_rows = {
        row["blocker"]: row
        for row in rows
        if row["blocker"]
        in {
            "utility_definition_missing",
            "instrument_package_missing",
            "state_action_contract_missing",
        }
    }
    assert set(emitted_rows) == {
        "utility_definition_missing",
        "instrument_package_missing",
        "state_action_contract_missing",
    }
    for row in emitted_rows.values():
        assert row["evaluator"] != NOT_RUNTIME_APPLICABLE
        assert row["red_test"] != NOT_RUNTIME_APPLICABLE
        assert row["fixture"] != NOT_RUNTIME_APPLICABLE
        assert row["cli_output"] != NOT_RUNTIME_APPLICABLE
        assert row["web_report_field"] != NOT_RUNTIME_APPLICABLE
    assert all(
        row["max_state"]
        and row["owning_wave"]
        and row["schema_field"]
        and row["evaluator"]
        and row["red_test"]
        and row["fixture"]
        and row["cli_output"]
        and row["runtime_enforcement"]
        for row in rows
    )


def test_registry_coverage_fails_for_discovered_unregistered_blocker(tmp_path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "sample.py").write_text(
        'from tradingx.promotion import Blocker\nBlocker("unregistered_blocker")\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unregistered_blocker"):
        validate_blocker_registry_coverage(repo_root=tmp_path)


def test_wave1_registry_fixtures_exist() -> None:
    for code in (
        "authority_artifact_invalid",
        "ledger_key_worm_controls_missing",
        "replay_path_missing",
        "unsupported_side",
        "short_support_missing",
    ):
        fixture = BLOCKER_REGISTRY[code].fixture
        assert fixture != "not_runtime_applicable"
        assert Path(fixture).exists()


def test_strictest_state_cap_always_wins() -> None:
    cap = strictest_state_cap(
        (
            Blocker("capacity_extrapolation_risk"),
            Blocker("authority_artifact_invalid"),
            Blocker("live_sample_requirement_unmet"),
        )
    )

    assert cap == PromotionState.DISABLED
