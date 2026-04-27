"""SQLite-backed append-only trials ledger for validation."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from tradingx.authority import canonical_payload_hash
from tradingx.types import TrialRecord, TrialStatistics

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trials (
    trial_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    family TEXT NOT NULL,
    window_start_utc TEXT NOT NULL,
    window_end_utc TEXT NOT NULL,
    observed_sharpe_net_of_costs TEXT NOT NULL,
    observed_cagr_net_of_costs TEXT NOT NULL,
    observed_max_drawdown TEXT NOT NULL,
    observed_cdar_95 TEXT NOT NULL,
    annualized_cost_drag_bps TEXT NOT NULL,
    passed INTEGER NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    git_sha TEXT NOT NULL,
    config_fingerprint TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trials_candidate ON trials(candidate_id);
CREATE INDEX IF NOT EXISTS idx_trials_family ON trials(family);
CREATE INDEX IF NOT EXISTS idx_trials_window
    ON trials(window_start_utc, window_end_utc);
"""


class TrialsLedgerIntegrityError(ValueError):
    """Raised when an append-only trial record is rewritten with new content."""


class TrialsLedger:
    def __init__(self, *, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def record(self, trial: TrialRecord) -> None:
        payload = _record_payload(trial)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM trials WHERE trial_id = ?",
                (trial.trial_id,),
            ).fetchone()
            if existing is not None:
                if canonical_payload_hash(
                    _record_payload(_row_to_record(existing))
                ) == (canonical_payload_hash(payload)):
                    return
                raise TrialsLedgerIntegrityError(
                    f"trial_id changed payload: {trial.trial_id}"
                )
            connection.execute(
                """
                INSERT INTO trials VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    trial.trial_id,
                    trial.candidate_id,
                    trial.family,
                    trial.window_start_utc.isoformat(),
                    trial.window_end_utc.isoformat(),
                    str(trial.observed_sharpe_net_of_costs),
                    str(trial.observed_cagr_net_of_costs),
                    str(trial.observed_max_drawdown),
                    str(trial.observed_cdar_95),
                    str(trial.annualized_cost_drag_bps),
                    1 if trial.passed else 0,
                    trial.recorded_at_utc.isoformat(),
                    trial.git_sha,
                    trial.config_fingerprint,
                ),
            )

    def list_for_candidate(
        self,
        candidate_id: str,
        *,
        window_start_utc: datetime | None = None,
        window_end_utc: datetime | None = None,
    ) -> tuple[TrialRecord, ...]:
        query = "SELECT * FROM trials WHERE candidate_id = ?"
        params: list[object] = [candidate_id]
        if window_start_utc is not None:
            query += " AND window_start_utc >= ?"
            params.append(window_start_utc.isoformat())
        if window_end_utc is not None:
            query += " AND window_end_utc <= ?"
            params.append(window_end_utc.isoformat())
        query += " ORDER BY recorded_at_utc"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return tuple(_row_to_record(row) for row in rows)

    def records_for_candidate(
        self,
        candidate_id: str,
        *,
        window_start_utc: datetime | None = None,
        window_end_utc: datetime | None = None,
    ) -> tuple[TrialRecord, ...]:
        return self.list_for_candidate(
            candidate_id,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
        )

    def trial_statistics_for_family(self, family: str) -> TrialStatistics:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT observed_sharpe_net_of_costs FROM trials WHERE family = ?",
                (family,),
            ).fetchall()
        if not rows:
            return TrialStatistics(
                n_trials=0,
                trial_sharpe_mean=0.0,
                trial_sharpe_variance=0.0,
            )
        sharpes = [float(Decimal(str(row[0]))) for row in rows]
        n_trials = len(sharpes)
        trial_sharpe_mean = sum(sharpes) / n_trials
        if n_trials < 2:
            trial_sharpe_variance = 0.0
        else:
            trial_sharpe_variance = sum(
                (sharpe - trial_sharpe_mean) ** 2 for sharpe in sharpes
            ) / (n_trials - 1)
        return TrialStatistics(
            n_trials=n_trials,
            trial_sharpe_mean=trial_sharpe_mean,
            trial_sharpe_variance=trial_sharpe_variance,
        )


def _row_to_record(row: tuple[object, ...]) -> TrialRecord:
    return TrialRecord(
        trial_id=str(row[0]),
        candidate_id=str(row[1]),
        family=str(row[2]),
        window_start_utc=datetime.fromisoformat(str(row[3])),
        window_end_utc=datetime.fromisoformat(str(row[4])),
        observed_sharpe_net_of_costs=Decimal(str(row[5])),
        observed_cagr_net_of_costs=Decimal(str(row[6])),
        observed_max_drawdown=Decimal(str(row[7])),
        observed_cdar_95=Decimal(str(row[8])),
        annualized_cost_drag_bps=Decimal(str(row[9])),
        passed=bool(row[10]),
        recorded_at_utc=datetime.fromisoformat(str(row[11])),
        git_sha=str(row[12]),
        config_fingerprint=str(row[13]),
    )


def _record_payload(trial: TrialRecord) -> dict[str, object]:
    return {
        "trial_id": trial.trial_id,
        "candidate_id": trial.candidate_id,
        "family": trial.family,
        "window_start_utc": trial.window_start_utc.isoformat(),
        "window_end_utc": trial.window_end_utc.isoformat(),
        "observed_sharpe_net_of_costs": str(trial.observed_sharpe_net_of_costs),
        "observed_cagr_net_of_costs": str(trial.observed_cagr_net_of_costs),
        "observed_max_drawdown": str(trial.observed_max_drawdown),
        "observed_cdar_95": str(trial.observed_cdar_95),
        "annualized_cost_drag_bps": str(trial.annualized_cost_drag_bps),
        "passed": trial.passed,
        "recorded_at_utc": trial.recorded_at_utc.isoformat(),
        "git_sha": trial.git_sha,
        "config_fingerprint": trial.config_fingerprint,
    }


__all__ = ("TrialsLedger", "TrialsLedgerIntegrityError")
