from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.trials import TrialsLedger
from tradingx.types import TrialRecord


def _make_record(trial_id: str = "trial-1", sharpe: str = "1.0") -> TrialRecord:
    return TrialRecord(
        trial_id=trial_id,
        candidate_id="trend-following-v1",
        family="trend_following",
        window_start_utc=datetime(2026, 1, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 12, 31, tzinfo=UTC),
        observed_sharpe_net_of_costs=Decimal(sharpe),
        observed_cagr_net_of_costs=Decimal("0.12"),
        observed_max_drawdown=Decimal("0.09"),
        observed_cdar_95=Decimal("0.06"),
        annualized_cost_drag_bps=Decimal("8.4"),
        passed=True,
        recorded_at_utc=datetime(2026, 12, 31, 23, tzinfo=UTC),
        git_sha="abc1234",
        config_fingerprint="deadbeef",
    )


def test_trials_ledger_round_trip(tmp_path: Path) -> None:
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    record = _make_record()

    ledger.record(record)
    fetched = ledger.list_for_candidate("trend-following-v1")

    assert len(fetched) == 1
    assert fetched[0].trial_id == "trial-1"
    assert fetched[0].observed_sharpe_net_of_costs == Decimal("1.0")


def test_trials_ledger_idempotent_on_trial_id(tmp_path: Path) -> None:
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")

    ledger.record(_make_record("trial-1", "1.0"))
    ledger.record(_make_record("trial-1", "2.0"))
    fetched = ledger.list_for_candidate("trend-following-v1")

    assert len(fetched) == 1
    assert fetched[0].observed_sharpe_net_of_costs == Decimal("1.0")
