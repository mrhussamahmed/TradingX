"""Defect 8 — Wave 4-10 CLI subcommand smoke tests.

Verifies every new CLI subcommand:
  * accepts ``--ref`` arguments
  * emits canonical JSON
  * returns non-zero on blocker_codes
  * returns zero on a clean payload
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradingx import __main__ as cli

WAVE_SUBCOMMANDS = (
    "portfolio-utility",
    "optimizer-validation",
    "optimizer-fallback",
    "forecast-manifest",
    "sizing-policy",
    "short-capability",
    "borrow-snapshot",
    "short-financing",
    "short-risk-report",
    "live-probe-plan",
    "live-probe-run",
    "live-probe-recertification",
    "change-control",
    "replay-equivalence",
    "recertification",
    "drift-monitor-spec",
    "legacy-migration-report",
)


@pytest.mark.parametrize("subcommand", WAVE_SUBCOMMANDS)
def test_wave_subcommand_returns_nonzero_with_no_refs(
    subcommand: str, capsys
) -> None:
    """Calling without --ref must fail closed with missing_sources."""

    exit_code = cli.main((subcommand,))
    payload = json.loads(capsys.readouterr().out)
    assert exit_code != 0
    assert "missing_sources" in payload["blocker_codes"]


@pytest.mark.parametrize("subcommand", WAVE_SUBCOMMANDS)
def test_wave_subcommand_emits_canonical_json_with_clean_ref(
    subcommand: str, tmp_path: Path, capsys
) -> None:
    """A payload with no concerning content emits zero blockers."""

    # Use a kind that the wave-7 evaluator ignores (non-short-side kind);
    # all evaluators short-circuit when the kind is not theirs, so this
    # tests the JSON-emit/return-code wiring without imposing a per-kind
    # fixture.
    payload = {
        "schema_version": "1.0",
        "kind": "promotion_evidence",
        "strategy_id": "trend-following-v1",
        "evidence_class": "valid",
        "artifact_refs": [],
    }
    ref_path = tmp_path / "payload.json"
    ref_path.write_text(json.dumps(payload), encoding="utf-8")
    exit_code = cli.main((subcommand, "--ref", str(ref_path)))
    output = json.loads(capsys.readouterr().out)
    assert output["command"] == subcommand
    assert isinstance(output["blocker_codes"], list)
    assert "evaluator" in output
    # promotion_evidence is not handled by any wave 4-10 evaluator, so no
    # blockers should fire.
    assert output["blocker_codes"] == []
    assert exit_code == 0


def test_wave_subcommand_returns_nonzero_when_evaluator_emits_blockers(
    tmp_path: Path, capsys
) -> None:
    """A change_control_record with critical scope must surface blockers."""

    payload = {
        "schema_version": "1.0",
        "kind": "change_control_record",
        "change_id": "chg-test",
        "change_type": "code",
        "change_scope": "feature_set",
        "unknown_scope": True,  # triggers unrecorded_material_change
        "affected_strategies": ["trend-following-v1"],
        "affected_evidence_refs": [],
        "dependency_index_refs": [],  # triggers dependency_scope_unresolved
        "materiality_class": "critical",
        "automatic_classification": "critical",
        "manual_classification": "critical",
        "classifier_confidence": "0.95",
        "classifier_version": "v1",
        "change_hash": "sha256:" + "a" * 64,
        "git_shas": ["abc123"],
        "creator": "ops",
        "replay_required": True,
        "recertification_required": True,
        "schema_compatibility_status": "compatible",
        "approval_ref": "cas://approval-001",
        "created_at_utc": "2026-04-26T00:00:00Z",
        "blocker_codes": [],
    }
    ref_path = tmp_path / "change.json"
    ref_path.write_text(json.dumps(payload), encoding="utf-8")
    exit_code = cli.main(("change-control", "--ref", str(ref_path)))
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert "dependency_scope_unresolved" in output["blocker_codes"]
