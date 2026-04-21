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


def test_trials_ledger_filters_by_window(tmp_path: Path) -> None:
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    early = _make_record("trial-early")
    late = _make_record("trial-late")

    ledger.record(early)
    ledger.record(late)
    recent = ledger.list_for_candidate(
        "trend-following-v1",
        window_start_utc=datetime(2025, 6, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 12, 31, tzinfo=UTC),
    )

    assert {record.trial_id for record in recent} == {"trial-early", "trial-late"}


def test_trial_statistics_for_family_aggregates_across_candidates(
    tmp_path: Path,
) -> None:
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")

    for idx, sharpe in enumerate(["0.5", "0.8", "1.1", "1.3"]):
        ledger.record(_make_record(f"trial-{idx}", sharpe))

    stats = ledger.trial_statistics_for_family("trend_following")
    expected_variance = (
        (0.5 - 0.925) ** 2
        + (0.8 - 0.925) ** 2
        + (1.1 - 0.925) ** 2
        + (1.3 - 0.925) ** 2
    ) / 3.0

    assert stats.n_trials == 4
    assert abs(stats.trial_sharpe_mean - 0.925) < 1e-9
    assert abs(stats.trial_sharpe_variance - expected_variance) < 1e-9


def test_trial_statistics_for_family_handles_single_trial(tmp_path: Path) -> None:
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")

    ledger.record(_make_record("trial-only", "1.2"))
    stats = ledger.trial_statistics_for_family("trend_following")

    assert stats.n_trials == 1
    assert stats.trial_sharpe_variance == 0.0


def test_trial_statistics_for_family_returns_empty_stats_for_unknown_family(
    tmp_path: Path,
) -> None:
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")

    ledger.record(_make_record())
    stats = ledger.trial_statistics_for_family("carry")

    assert stats.n_trials == 0
    assert stats.trial_sharpe_variance == 0.0
