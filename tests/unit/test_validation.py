from __future__ import annotations

import importlib
import json
from decimal import Decimal

import pandas as pd

from tradingx.costs import CostModelConfig
from tradingx.evaluation import AdversarialCheckContext
from tradingx.evaluation import _sharpe_ratio as evaluation_sharpe_ratio
from tradingx.strategy import build_mandatory_candidate_registry
from tradingx.trials import TrialsLedger
from tradingx.types import (
    BenchmarkStackPayload,
    EvaluationEvidencePack,
    OperatingConstraintBudget,
    StrategyCandidate,
)
from tradingx.validation import (
    _build_gate1_candidate_result,
    _candidate_returns,
    build_gate_report,
    evaluate_gate1_benchmark_criteria,
    evaluate_hurdle_clearance,
    evaluate_operating_constraint,
    evaluate_opportunity_cost_edge,
)
from tradingx.validation import (
    _sharpe_ratio as validation_sharpe_ratio,
)


def _build_close_series(
    *,
    periods: int,
    up_return: Decimal,
    down_return: Decimal,
    down_every: int,
    start_price: Decimal = Decimal("100"),
) -> tuple[Decimal, ...]:
    closes = [start_price]
    price = start_price
    for index in range(periods):
        daily_return = down_return if index % down_every == 0 else up_return
        price *= Decimal("1") + daily_return
        closes.append(price.quantize(Decimal("0.0001")))
    return tuple(closes)


def _ohlcv_frame(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2023-01-03", periods=len(closes), freq="B", tz="UTC")
    close_series = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close_series,
            "high": close_series * 1.01,
            "low": close_series * 0.99,
            "close": close_series,
            "volume": 1_000_000.0,
        },
        index=index,
    )


def _quote_enriched_ohlcv_frame(closes: list[float]) -> pd.DataFrame:
    frame = _ohlcv_frame(closes)
    frame["open"] = frame["close"].shift(1).fillna(frame["close"].iloc[0])
    frame["high"] = frame[["open", "close"]].max(axis=1) * 1.01
    frame["low"] = frame[["open", "close"]].min(axis=1) * 0.99
    frame["bid"] = frame["open"] - 0.05
    frame["ask"] = frame["open"] + 0.05
    return frame


def _compound_total_return(returns: tuple[Decimal, ...]) -> Decimal:
    equity = Decimal("1")
    for value in returns:
        equity *= Decimal("1") + value
    return equity - Decimal("1")


def _benchmark_stack_payload_for_periods(return_periods: int) -> BenchmarkStackPayload:
    return BenchmarkStackPayload(
        hurdle_returns=tuple([Decimal("0.0001")] * return_periods),
        opportunity_cost_returns=tuple([Decimal("0.0002")] * return_periods),
        opportunity_cost_weights=(
            ("SPY", Decimal("0.6")),
            ("AGG", Decimal("0.4")),
        ),
        operating_constraint=OperatingConstraintBudget(
            max_drawdown_design=Decimal("0.15"),
            max_drawdown_halt=Decimal("0.25"),
            cdar_threshold=Decimal("0.08"),
            cdar_confidence=Decimal("0.95"),
        ),
    )


def test_validation_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.validation")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_build_gate_report_runs_real_backtests_from_daily_bars() -> None:
    bars_by_symbol = {
        "SPY": _ohlcv_frame(
            [
                100.0,
                101.0,
                102.0,
                103.0,
                104.0,
                105.0,
                106.0,
                107.0,
                108.0,
                109.0,
            ]
        ),
        "QQQ": _ohlcv_frame(
            [
                100.0,
                100.5,
                101.0,
                102.0,
                101.0,
                102.5,
                103.0,
                104.0,
                103.5,
                104.5,
            ]
        ),
    }
    candidates = build_mandatory_candidate_registry(("SPY", "QQQ"))

    report = build_gate_report(
        gate_id="1",
        bars_by_symbol=bars_by_symbol,
        candidates=candidates,
        benchmark_stack_payload=_benchmark_stack_payload_for_periods(len(bars_by_symbol["SPY"])),
        window_start_utc=bars_by_symbol["SPY"].index[0].to_pydatetime(),
        window_end_utc=bars_by_symbol["SPY"].index[-1].to_pydatetime(),
    )

    assert report.gate_id == "1"
    assert report.benchmark_symbol == "SPY+AGG"
    assert len(report.candidate_results) == 3
    assert {result.candidate_id for result in report.candidate_results} == {
        "trend-following-v1",
        "vol-target-v1",
        "mean-reversion-v1",
    }
    assert all(result.evidence_pack_id for result in report.candidate_results)


def test_hurdle_clearance_passes_when_candidate_beats_cash() -> None:
    candidate_returns = tuple([Decimal("0.0003")] * 252)
    hurdle_returns = tuple([Decimal("0.0002")] * 252)

    result = evaluate_hurdle_clearance(
        candidate_returns=candidate_returns,
        hurdle_returns=hurdle_returns,
    )

    assert result.passed is True
    assert result.criterion_id == "hurdle_clearance"


def test_hurdle_clearance_fails_when_candidate_underperforms_cash() -> None:
    candidate_returns = tuple([Decimal("0.0001")] * 252)
    hurdle_returns = tuple([Decimal("0.0002")] * 252)

    result = evaluate_hurdle_clearance(
        candidate_returns=candidate_returns,
        hurdle_returns=hurdle_returns,
    )

    assert result.passed is False


def test_opportunity_cost_edge_passes_when_candidate_beats_60_40() -> None:
    candidate_returns = tuple([Decimal("0.0005")] * 252)
    opportunity_cost_returns = tuple([Decimal("0.0003")] * 252)

    result = evaluate_opportunity_cost_edge(
        candidate_returns=candidate_returns,
        opportunity_cost_returns=opportunity_cost_returns,
        opportunity_cost_weights=(("SPY", Decimal("0.6")), ("AGG", Decimal("0.4"))),
    )

    assert result.passed is True
    assert result.criterion_id == "opportunity_cost_edge"
    assert "SPY:0.6" in result.details
    assert "AGG:0.4" in result.details


def test_opportunity_cost_edge_fails_when_candidate_underperforms_60_40() -> None:
    candidate_returns = tuple([Decimal("0.0001")] * 252)
    opportunity_cost_returns = tuple([Decimal("0.0004")] * 252)

    result = evaluate_opportunity_cost_edge(
        candidate_returns=candidate_returns,
        opportunity_cost_returns=opportunity_cost_returns,
        opportunity_cost_weights=(("SPY", Decimal("0.6")), ("AGG", Decimal("0.4"))),
    )

    assert result.passed is False


def test_operating_constraint_passes_within_budget() -> None:
    returns = tuple([Decimal("0.01")] * 10 + [Decimal("-0.005")] * 5)
    constraint = OperatingConstraintBudget(
        max_drawdown_design=Decimal("0.15"),
        max_drawdown_halt=Decimal("0.25"),
        cdar_threshold=Decimal("0.08"),
        cdar_confidence=Decimal("0.95"),
    )

    result = evaluate_operating_constraint(
        candidate_returns=returns,
        constraint=constraint,
    )

    assert result.criterion_id == "operating_constraint"
    assert result.passed is True


def test_operating_constraint_fails_when_mdd_exceeds_design() -> None:
    returns = tuple([Decimal("0.01")] * 20 + [Decimal("-0.03")] * 12)
    constraint = OperatingConstraintBudget(
        max_drawdown_design=Decimal("0.15"),
        max_drawdown_halt=Decimal("0.25"),
        cdar_threshold=Decimal("0.08"),
        cdar_confidence=Decimal("0.95"),
    )

    result = evaluate_operating_constraint(
        candidate_returns=returns,
        constraint=constraint,
    )

    assert result.passed is False
    assert "max_drawdown" in result.details


def test_gate1_benchmark_criteria_use_benchmark_stack_payload() -> None:
    payload = BenchmarkStackPayload(
        hurdle_returns=tuple([Decimal("0.0002")] * 252),
        opportunity_cost_returns=tuple([Decimal("0.0003")] * 252),
        opportunity_cost_weights=(
            ("SPY", Decimal("0.6")),
            ("AGG", Decimal("0.4")),
        ),
        operating_constraint=OperatingConstraintBudget(
            max_drawdown_design=Decimal("0.15"),
            max_drawdown_halt=Decimal("0.25"),
            cdar_threshold=Decimal("0.08"),
            cdar_confidence=Decimal("0.95"),
        ),
    )

    criteria = evaluate_gate1_benchmark_criteria(
        candidate_returns=tuple([Decimal("0.0005")] * 252),
        benchmark_stack_payload=payload,
    )

    criterion_ids = {criterion.criterion_id for criterion in criteria}

    assert criterion_ids == {
        "hurdle_clearance",
        "opportunity_cost_edge",
        "operating_constraint",
    }


def test_candidate_returns_support_parameter_overrides_and_cost_replays() -> None:
    trend_candidate = StrategyCandidate(
        candidate_id="trend-test",
        family="trend_following",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={
            "lookback_days": 8,
            "sma_window_days": 5,
            "skip_recent_days": 1,
            "signal": "long_only",
        },
        status="under_evaluation",
    )
    trend_bars = {
        "SPY": _quote_enriched_ohlcv_frame(
            [100.0] * 10
            + [
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
                95.0,
                96.0,
                97.0,
                98.0,
                99.0,
                100.0,
                101.0,
                102.0,
                103.0,
                104.0,
            ]
        )
    }

    base_trend_returns, base_trend_drag = _candidate_returns(
        trend_candidate,
        bars_by_symbol=trend_bars,
    )
    overridden_trend_returns, overridden_trend_drag = _candidate_returns(
        trend_candidate,
        bars_by_symbol=trend_bars,
        parameter_overrides={"lookback_days": 4, "sma_window_days": 3},
    )

    assert overridden_trend_returns != base_trend_returns
    assert base_trend_drag >= Decimal("0")
    assert overridden_trend_drag >= Decimal("0")

    vol_candidate = build_mandatory_candidate_registry(("SPY",))[1]
    vol_bars = {
        "SPY": _quote_enriched_ohlcv_frame(
            [
                100.0 + (0.6 * float(index)) + (2.5 * (-1.0 if index % 7 == 0 else 1.0))
                for index in range(90)
            ]
        )
    }

    base_vol_returns, base_vol_drag = _candidate_returns(
        vol_candidate,
        bars_by_symbol=vol_bars,
    )
    explicit_default_returns, explicit_default_drag = _candidate_returns(
        vol_candidate,
        bars_by_symbol=vol_bars,
        cost_model_config=CostModelConfig(),
    )

    assert explicit_default_returns == base_vol_returns
    assert explicit_default_drag == base_vol_drag
    assert base_vol_drag >= Decimal("0")


def test_adversarial_backtest_runner_still_returns_plain_tuple(monkeypatch) -> None:
    bars_by_symbol = {
        "SPY": _quote_enriched_ohlcv_frame(
            [
                100.0 + (0.4 * float(index)) + (1.5 * (-1.0 if index % 9 == 0 else 1.0))
                for index in range(300)
            ]
        ),
        "QQQ": _quote_enriched_ohlcv_frame(
            [
                98.0
                + (0.45 * float(index))
                + (1.2 * (-1.0 if index % 11 == 0 else 1.0))
                for index in range(300)
            ]
        ),
    }
    candidate = build_mandatory_candidate_registry(("SPY", "QQQ"))[1]

    def fake_evaluate_candidate(
        candidate: StrategyCandidate,
        *,
        candidate_returns: tuple[Decimal, ...],
        benchmark_returns: tuple[Decimal, ...],
        window_start_utc,
        window_end_utc,
        adversarial_context: AdversarialCheckContext,
        annualized_cost_drag_bps: Decimal | None = None,
        trials_ledger: TrialsLedger | None = None,
    ) -> EvaluationEvidencePack:
        del benchmark_returns, annualized_cost_drag_bps, trials_ledger
        rerun_returns = adversarial_context.backtest_runner(
            candidate,
            parameter_overrides={"lookback_days": 10},
        )
        assert isinstance(rerun_returns, tuple)
        assert rerun_returns
        assert all(isinstance(value, Decimal) for value in rerun_returns)
        return EvaluationEvidencePack(
            evidence_pack_id="eval-shape",
            candidate_id=candidate.candidate_id,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            benchmark_metrics={"sharpe_ratio": 0.1},
            candidate_metrics={"sharpe_ratio": 0.2, "excess_return": 0.1},
            adversarial_checks=(),
            recommendation="research_further",
            assumptions=(),
        )

    monkeypatch.setattr("tradingx.validation.evaluate_candidate", fake_evaluate_candidate)

    report = build_gate_report(
        gate_id="2",
        bars_by_symbol=bars_by_symbol,
        candidates=(candidate,),
        benchmark_stack_payload=_benchmark_stack_payload_for_periods(
            len(bars_by_symbol["SPY"])
        ),
        window_start_utc=bars_by_symbol["SPY"].index[0].to_pydatetime(),
        window_end_utc=bars_by_symbol["SPY"].index[-1].to_pydatetime(),
    )

    assert report.candidate_results[0].candidate_id == candidate.candidate_id


def test_build_gate_report_threads_trials_ledger_to_gate_layer(tmp_path) -> None:
    bars_by_symbol = {
        "SPY": _ohlcv_frame(
            [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
        ),
        "QQQ": _ohlcv_frame(
            [100.0, 100.5, 101.0, 102.0, 101.0, 102.5, 103.0, 104.0, 103.5, 104.5]
        ),
    }
    candidates = build_mandatory_candidate_registry(("SPY", "QQQ"))
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")

    build_gate_report(
        gate_id="1",
        bars_by_symbol=bars_by_symbol,
        candidates=candidates,
        benchmark_stack_payload=_benchmark_stack_payload_for_periods(
            len(bars_by_symbol["SPY"])
        ),
        window_start_utc=bars_by_symbol["SPY"].index[0].to_pydatetime(),
        window_end_utc=bars_by_symbol["SPY"].index[-1].to_pydatetime(),
        trials_ledger=ledger,
    )

    for candidate in candidates:
        records = ledger.list_for_candidate(candidate.candidate_id)
        assert records, f"No trial recorded for {candidate.candidate_id}"


def test_build_gate1_candidate_result_records_trial_with_real_gate_status(
    tmp_path,
) -> None:
    candidate = build_mandatory_candidate_registry(("SPY",))[0]
    candidate_returns = tuple(
        Decimal("0.0012") if index % 4 in (0, 1) else Decimal("-0.0003")
        for index in range(1008)
    )
    benchmark_bars = _ohlcv_frame([100.0 + (0.25 * index) for index in range(1008)])
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")

    result = _build_gate1_candidate_result(
        candidate=candidate,
        candidate_returns=candidate_returns,
        annualized_cost_drag_bps=Decimal("7.5"),
        benchmark_stack_payload=_benchmark_stack_payload_for_periods(
            len(candidate_returns)
        ),
        window_start_utc=benchmark_bars.index[0].to_pydatetime(),
        window_end_utc=benchmark_bars.index[-1].to_pydatetime(),
        adversarial_context=AdversarialCheckContext(
            benchmark_bars=benchmark_bars,
            backtest_runner=lambda *_args, **_kwargs: candidate_returns,
            base_cost_model_config=CostModelConfig(),
        ),
        trials_ledger=ledger,
    )

    records = ledger.list_for_candidate(candidate.candidate_id)

    assert len(records) == 1
    assert records[0].passed is (result.status == "pass")


def test_build_gate1_candidate_result_populates_cost_drag_on_result(tmp_path) -> None:
    candidate = build_mandatory_candidate_registry(("SPY",))[0]
    candidate_returns = tuple(
        Decimal("0.0012") if index % 4 in (0, 1) else Decimal("-0.0003")
        for index in range(1008)
    )
    benchmark_bars = _ohlcv_frame([100.0 + (0.25 * index) for index in range(1008)])
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")

    result = _build_gate1_candidate_result(
        candidate=candidate,
        candidate_returns=candidate_returns,
        annualized_cost_drag_bps=Decimal("7.5"),
        benchmark_stack_payload=_benchmark_stack_payload_for_periods(
            len(candidate_returns)
        ),
        window_start_utc=benchmark_bars.index[0].to_pydatetime(),
        window_end_utc=benchmark_bars.index[-1].to_pydatetime(),
        adversarial_context=AdversarialCheckContext(
            benchmark_bars=benchmark_bars,
            backtest_runner=lambda *_args, **_kwargs: candidate_returns,
            base_cost_model_config=CostModelConfig(),
        ),
        trials_ledger=ledger,
    )

    assert result.annualized_cost_drag_bps == Decimal("7.5")
    assert result.annualized_cost_drag_bps >= Decimal("0")


def test_build_gate2_report_uses_real_stress_descriptions() -> None:
    bars_by_symbol = {
        "SPY": _quote_enriched_ohlcv_frame(
            [
                100.0 + (0.4 * float(index)) + (1.5 * (-1.0 if index % 9 == 0 else 1.0))
                for index in range(300)
            ]
        ),
        "QQQ": _quote_enriched_ohlcv_frame(
            [
                98.0
                + (0.45 * float(index))
                + (1.2 * (-1.0 if index % 11 == 0 else 1.0))
                for index in range(300)
            ]
        ),
    }
    candidate = build_mandatory_candidate_registry(("SPY", "QQQ"))[1]

    report = build_gate_report(
        gate_id="2",
        bars_by_symbol=bars_by_symbol,
        candidates=(candidate,),
        benchmark_stack_payload=_benchmark_stack_payload_for_periods(len(bars_by_symbol["SPY"])),
        window_start_utc=bars_by_symbol["SPY"].index[0].to_pydatetime(),
        window_end_utc=bars_by_symbol["SPY"].index[-1].to_pydatetime(),
    )

    criteria_by_id = {
        criterion.criterion_id: criterion
        for criterion in report.candidate_results[0].criteria
    }

    assert "per-period cost penalty" not in criteria_by_id["cost_stress"].details
    assert "half-spread" in criteria_by_id["cost_stress"].details
    assert "impact" in criteria_by_id["cost_stress"].details
    assert "commission" in criteria_by_id["cost_stress"].details
    assert "1x, 2x, and 4x" in criteria_by_id["cost_stress"].threshold


def test_gate1_drawdown_reports_design_target_separately_from_hard_limit() -> None:
    candidate = build_mandatory_candidate_registry(("SPY",))[0]
    candidate_returns = (
        Decimal("0.10"),
        Decimal("-0.13"),
        Decimal("0.00"),
        Decimal("0.00"),
    )
    benchmark_bars = _ohlcv_frame([100.0, 101.0, 102.0, 103.0])

    result = _build_gate1_candidate_result(
        candidate=candidate,
        candidate_returns=candidate_returns,
        benchmark_stack_payload=BenchmarkStackPayload(
            hurdle_returns=tuple(Decimal("0.00") for _ in candidate_returns),
            opportunity_cost_returns=tuple(Decimal("0.00") for _ in candidate_returns),
            opportunity_cost_weights=(
                ("SPY", Decimal("0.6")),
                ("AGG", Decimal("0.4")),
            ),
            operating_constraint=OperatingConstraintBudget(
                max_drawdown_design=Decimal("0.15"),
                max_drawdown_halt=Decimal("0.25"),
                cdar_threshold=Decimal("0.08"),
                cdar_confidence=Decimal("0.95"),
            ),
        ),
        window_start_utc=benchmark_bars.index[0].to_pydatetime(),
        window_end_utc=benchmark_bars.index[-1].to_pydatetime(),
        adversarial_context=AdversarialCheckContext(
            benchmark_bars=benchmark_bars,
            backtest_runner=lambda *_args, **_kwargs: candidate_returns,
            base_cost_model_config=CostModelConfig(),
        ),
    )

    criteria_by_id = {
        criterion.criterion_id: criterion for criterion in result.criteria
    }

    assert criteria_by_id["operating_constraint"].passed is False
    assert "halt=0.250" in criteria_by_id["operating_constraint"].details


def test_load_benchmark_close_series_reads_metadata_rich_artifact(tmp_path) -> None:
    module = importlib.import_module("tradingx.validation")
    artifact_file = tmp_path / "spy-dividend-benchmark.json"
    artifact_file.write_text(
        json.dumps(
            {
                "symbol": "SPY",
                "window_start_utc": "2023-01-01T00:00:00+00:00",
                "window_end_utc": "2026-04-17T00:00:00+00:00",
                "generated_at_utc": "2026-04-17T21:15:00+00:00",
                "feed": "iex",
                "adjustment": "dividend",
                "series_is_adjusted": True,
                "closes": ["100", "101.5", "102.25"],
            }
        ),
        encoding="utf-8",
    )

    series = module.load_benchmark_close_series(artifact_file)

    assert series.symbol == "SPY"
    assert series.series_is_adjusted is True
    assert series.feed == "iex"
    assert series.adjustment == "dividend"
    assert series.closes == (
        Decimal("100"),
        Decimal("101.5"),
        Decimal("102.25"),
    )


def test_load_benchmark_close_series_warns_on_legacy_json_list(
    tmp_path,
    caplog,
) -> None:
    module = importlib.import_module("tradingx.validation")
    artifact_file = tmp_path / "legacy-benchmark.json"
    artifact_file.write_text(
        json.dumps(["100", "101.5", "102.25"]),
        encoding="utf-8",
    )

    with caplog.at_level("WARNING"):
        series = module.load_benchmark_close_series(artifact_file)

    assert series.symbol == "SPY"
    assert series.series_is_adjusted is False
    assert "legacy JSON-list format without metadata" in caplog.text


def test_validation_sharpe_ratio_matches_evaluation_sharpe_definition() -> None:
    returns = (
        [0.012] * 40
        + [-0.004] * 10
        + [0.010] * 40
        + [-0.003] * 10
    )

    assert validation_sharpe_ratio(returns) == evaluation_sharpe_ratio(
        returns=returns,
        risk_free_daily_rates=[0.0] * len(returns),
    )
