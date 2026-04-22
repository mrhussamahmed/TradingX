from __future__ import annotations

import dataclasses
import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

import tradingx.validation as validation_module
from tradingx.persistence import FilesystemArtifactStore
from tradingx.strategy import build_mandatory_candidate_registry
from tradingx.validation import _run_cpcv_for_candidate


def _fixture_bars(
    *,
    start: datetime,
    periods: int,
    symbols: tuple[str, ...],
) -> dict[str, pd.DataFrame]:
    index = pd.date_range(start=start, periods=periods, freq="B", tz="UTC")
    return {
        symbol: pd.DataFrame(
            {
                "open": [100.0 + index_value * 0.01 for index_value in range(periods)],
                "high": [100.5 + index_value * 0.01 for index_value in range(periods)],
                "low": [99.5 + index_value * 0.01 for index_value in range(periods)],
                "close": [100.0 + index_value * 0.02 for index_value in range(periods)],
                "bid": [99.95 + index_value * 0.01 for index_value in range(periods)],
                "ask": [100.05 + index_value * 0.01 for index_value in range(periods)],
                "volume": [1_000_000.0] * periods,
            },
            index=index,
        )
        for symbol in symbols
    }


def _fixture_sleeve_candidate():
    registry = build_mandatory_candidate_registry(("SPY", "QQQ"))
    return next(
        candidate
        for candidate in registry
        if candidate.candidate_id == "trend-following-v1"
    )


def test_run_cpcv_for_candidate_writes_exactly_45_records(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    bars = _fixture_bars(
        start=datetime(2020, 1, 1, tzinfo=UTC),
        periods=200,
        symbols=("SPY", "QQQ"),
    )

    records = _run_cpcv_for_candidate(
        candidate=_fixture_sleeve_candidate(),
        bars_by_symbol=bars,
        window_start_utc=bars["SPY"].index[0].to_pydatetime(),
        window_end_utc=bars["SPY"].index[-1].to_pydatetime(),
        artifact_store=store,
    )

    assert len(records) == 45
    assert len(tuple((tmp_path / "cpcv_trials").glob("*.json"))) == 45
    assert all(record.in_sample_n_trades == 0 for record in records)
    assert all(record.out_of_sample_n_trades == 0 for record in records)


def test_run_cpcv_for_candidate_stage_1_returns_records_only(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    bars = _fixture_bars(
        start=datetime(2020, 1, 1, tzinfo=UTC),
        periods=200,
        symbols=("SPY", "QQQ"),
    )

    records = _run_cpcv_for_candidate(
        candidate=_fixture_sleeve_candidate(),
        bars_by_symbol=bars,
        window_start_utc=bars["SPY"].index[0].to_pydatetime(),
        window_end_utc=bars["SPY"].index[-1].to_pydatetime(),
        artifact_store=store,
    )

    assert len(records) == 45
    assert not (tmp_path / "pbo_reports").exists()


def test_run_cpcv_for_candidate_skips_when_insufficient_history(
    tmp_path: Path,
    caplog,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    bars = _fixture_bars(
        start=datetime(2026, 1, 1, tzinfo=UTC),
        periods=50,
        symbols=("SPY", "QQQ"),
    )
    caplog.set_level(logging.INFO)

    records = _run_cpcv_for_candidate(
        candidate=_fixture_sleeve_candidate(),
        bars_by_symbol=bars,
        window_start_utc=bars["SPY"].index[0].to_pydatetime(),
        window_end_utc=bars["SPY"].index[-1].to_pydatetime(),
        artifact_store=store,
    )

    assert records == ()
    assert not (tmp_path / "cpcv_trials").exists()
    assert any(
        "cpcv_insufficient_history" in record.message for record in caplog.records
    )


def test_run_cpcv_for_candidate_noop_when_no_sleeve_class_path(
    tmp_path: Path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    candidate = dataclasses.replace(_fixture_sleeve_candidate(), sleeve_class_path=None)
    bars = _fixture_bars(
        start=datetime(2020, 1, 1, tzinfo=UTC),
        periods=200,
        symbols=("SPY", "QQQ"),
    )

    records = _run_cpcv_for_candidate(
        candidate=candidate,
        bars_by_symbol=bars,
        window_start_utc=bars["SPY"].index[0].to_pydatetime(),
        window_end_utc=bars["SPY"].index[-1].to_pydatetime(),
        artifact_store=store,
    )

    assert records == ()


def test_run_cpcv_for_candidate_evaluates_disjoint_paths_by_contiguous_segment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    bars = _fixture_bars(
        start=datetime(2020, 1, 1, tzinfo=UTC),
        periods=200,
        symbols=("SPY", "QQQ"),
    )
    observed_segments: list[tuple[pd.Timestamp, ...]] = []

    def _fake_generate_cpcv_paths(
        **_: object,
    ) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
        return (((0, 1, 2, 8, 9), (3, 4, 10, 11)),)

    def _fake_candidate_returns(*, candidate, bars_by_symbol, **kwargs):  # type: ignore[no-untyped-def]
        del candidate, kwargs
        observed_segments.append(tuple(bars_by_symbol["SPY"].index))
        return (
            tuple(Decimal("0.01") for _ in range(len(bars_by_symbol["SPY"].index))),
            Decimal("0"),
        )

    monkeypatch.setattr(
        validation_module,
        "generate_cpcv_paths",
        _fake_generate_cpcv_paths,
    )
    monkeypatch.setattr(
        validation_module,
        "_candidate_returns",
        _fake_candidate_returns,
    )

    records = _run_cpcv_for_candidate(
        candidate=_fixture_sleeve_candidate(),
        bars_by_symbol=bars,
        window_start_utc=bars["SPY"].index[0].to_pydatetime(),
        window_end_utc=bars["SPY"].index[-1].to_pydatetime(),
        artifact_store=store,
    )

    assert len(records) == 1
    assert [len(segment) for segment in observed_segments] == [3, 2, 2, 2]
