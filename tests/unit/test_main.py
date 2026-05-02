from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx import __main__ as cli
from tradingx import controller as controller_module
from tradingx.execution import OrderRouteAuthorityError
from tradingx.journal import SqliteOmsJournal
from tradingx.persistence import FilesystemArtifactStore
from tradingx.snapshots import (
    CandidateIntentSnapshot,
    ContentAddressedSnapshotStore,
    DecisionSnapshotV1,
)
from tradingx.types import (
    AccountSnapshot,
    ApprovedWeightSnapshot,
    BenchmarkStackPayload,
    ExecutionLifecycleRecord,
    GateDecisionBrief,
    GateDecisionCandidateSummary,
    HistoricalWarmupRecord,
    LatestQuote,
    MarketAutomationRunRecord,
    MarketAutomationRunResult,
    MarketDaySchedulerRunResult,
    MarketSnapshot,
    OperatingConstraintBudget,
    OpportunityScore,
    OpportunitySelectionRecord,
    OrderRecord,
    PortfolioState,
    RoundTripResult,
    ServiceCycleSnapshot,
    ServiceSymbolResult,
    StrategyActivationRecord,
    TradeIntent,
)


def test_tier0a_decision_report_writes_required_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    input_path = tmp_path / "tier0-input.json"
    metrics_path = tmp_path / "metrics.json"
    report_path = tmp_path / "report.md"
    input_path.write_text(
        json.dumps(
            {
                "memo_inputs": {},
                "as_is_replay": {"status": "missing"},
                "hard_hurdles": {"status": "missing"},
                "geometric_uncertainty": {"status": "missing"},
                "stress_coverage": {"status": "missing"},
                "manifest_evidence": {"status": "missing"},
                "pbo_cpcv": {"status": "missing"},
                "marginal_portfolio_contribution": {"status": "missing"},
                "cost_stress": {"status": "missing"},
            }
        ),
        encoding="utf-8",
    )

    exit_code = cli.main(
        (
            "tier0a-decision-report",
            "--input-file",
            str(input_path),
            "--metrics-output",
            str(metrics_path),
            "--report-output",
            str(report_path),
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["decision"] == "blocked_as_is_unreproducible"
    assert json.loads(metrics_path.read_text(encoding="utf-8"))["decision"] == (
        "blocked_as_is_unreproducible"
    )
    assert "blocked_as_is_unreproducible" in report_path.read_text(encoding="utf-8")


def test_promotion_check_reports_blockers_from_fixture_artifacts(capsys) -> None:
    exit_code = cli.main(
        (
            "promotion-check",
            "--strategy-id",
            "trend-following-v1",
            "--artifact-root",
            "tests/fixtures/promotion/key_policy_missing",
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["strategy_id"] == "trend-following-v1"
    assert payload["max_state"] == "disabled"
    assert payload["blocker_codes"] == ["ledger_key_worm_controls_missing"]


def test_promotion_check_summary_format_reports_state_and_blockers(capsys) -> None:
    exit_code = cli.main(
        (
            "promotion-check",
            "--strategy-id",
            "trend-following-v1",
            "--artifact-root",
            "tests/fixtures/promotion/paper_shadow_placeholder",
            "--format",
            "summary",
        )
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "strategy_id: trend-following-v1" in output
    assert "max_state: paper_shadow" in output
    assert "blocker_codes: none" in output
    assert "mandate_blocker_codes: none" in output
    assert "statistical_blocker_codes: none" in output


def test_promotion_check_default_artifact_root_allows_paper_trading_only(
    capsys,
) -> None:
    exit_code = cli.main(
        (
            "promotion-check",
            "--strategy-id",
            "trend-following-v1",
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["strategy_id"] == "trend-following-v1"
    assert payload["requested_state"] == "paper_trading"
    assert payload["max_state"] == "paper_trading"
    assert payload["blocker_codes"] == []
    assert payload["mandate_blocker_codes"] == []
    assert payload["statistical_blocker_codes"] == []


def test_promotion_check_replays_wave2_mandate_fixture_bundle(capsys) -> None:
    exit_code = cli.main(
        (
            "promotion-check",
            "--strategy-id",
            "trend-following-v1",
            "--artifact-root",
            "tests/fixtures/mandate/external_capital_unknown",
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["max_state"] == "disabled"
    # The mandate fixture predates Defect 1 and ships without wave 4-10 stub
    # artifacts, so a production-targeted bundle now surfaces every required
    # kind missing alongside the existing mandate concern.
    assert "external_capital_compliance_unknown" in payload["blocker_codes"]
    assert payload["mandate_blocker_codes"] == ["external_capital_compliance_unknown"]
    expected_missing_kinds = {
        "authority_boundary_missing",
        "capacity_curve_report_missing",
        "cost_model_report_missing",
        "drift_monitor_spec_missing",
        "live_probe_plan_missing",
        "live_probe_recertification_report_missing",
        "operational_safety_drill_missing",
        "optimizer_validation_report_missing",
        "portfolio_utility_definition_missing",
        "pre_trade_control_manifest_missing",
        "recertification_report_missing",
        "sizing_policy_missing",
        "statistical_validation_report_missing",
    }
    assert expected_missing_kinds <= set(payload["blocker_codes"])


def test_promotion_check_wrong_strategy_artifact_fails_closed(capsys) -> None:
    exit_code = cli.main(
        (
            "promotion-check",
            "--strategy-id",
            "mean-reversion-v1",
            "--artifact-root",
            "tests/fixtures/promotion/paper_shadow_placeholder",
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["strategy_id"] == "mean-reversion-v1"
    assert payload["max_state"] == "disabled"
    assert payload["blocker_codes"] == ["authority_artifact_invalid"]
    assert payload["mismatched_artifact_strategy_id"] == "trend-following-v1"


def test_default_paper_order_authority_uses_operator_promotion_bundle(
    monkeypatch, tmp_path
) -> None:
    observed_roots: list[Path] = []

    def fake_provider(root: Path):
        observed_roots.append(root)
        return lambda strategy_id: strategy_id

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        controller_module, "build_artifact_promotion_decision_provider", fake_provider
    )

    config = controller_module.TradingConfig.from_mapping(
        {"TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
    )

    guard = controller_module._build_default_authority_guard(
        config, broker_mode="paper"
    )

    assert guard is not None
    assert observed_roots == [Path("config/strategy/promotion")]


class FakeController:
    def run_paper_roundtrip(
        self,
        symbol: str,
        quantity: Decimal,
        *,
        log_dir: Path,
    ) -> RoundTripResult:
        return RoundTripResult(
            symbol=symbol,
            quantity=quantity,
            quote=LatestQuote(
                symbol=symbol,
                bid_price=Decimal("599.90"),
                ask_price=Decimal("600.10"),
                timestamp=datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
            ),
            initial_account=AccountSnapshot(
                cash=Decimal("100000"),
                equity=Decimal("100000"),
                buying_power=Decimal("200000"),
            ),
            final_account=AccountSnapshot(
                cash=Decimal("99999.75"),
                equity=Decimal("100001"),
                buying_power=Decimal("199999"),
            ),
            buy_order=OrderRecord(
                order_id="buy-1",
                client_order_id="buy-client-1",
                symbol=symbol,
                side="buy",
                status="filled",
                filled_qty=Decimal("1"),
                filled_avg_price=Decimal("600.00"),
            ),
            sell_order=OrderRecord(
                order_id="sell-1",
                client_order_id="sell-client-1",
                symbol=symbol,
                side="sell",
                status="filled",
                filled_qty=Decimal("1"),
                filled_avg_price=Decimal("600.25"),
            ),
            final_position_quantity=Decimal("0"),
            cash_delta=Decimal("-0.25"),
            log_path=log_dir / "spy-paper-roundtrip.json",
        )


class FakePaperLoopController:
    def __init__(self) -> None:
        self.called_with = None
        self.recovered_symbol = None

    def run_trading_cycle(self, symbol: str, quantity: Decimal):
        self.called_with = (symbol, quantity)
        return {
            "symbol": symbol,
            "terminal_state": "reconciled_trade",
        }

    def recover_trading_cycle(self, symbol: str):
        self.recovered_symbol = symbol
        return {
            "symbol": symbol,
            "terminal_state": "reconciled_trade",
            "recovered": True,
        }


class FakeAuthorityBlockedPaperLoopController:
    def run_trading_cycle(self, symbol: str, quantity: Decimal):
        del symbol, quantity
        raise OrderRouteAuthorityError(
            "paper_order for trend-following-v1 is capped at research_only; "
            "requires paper_trading."
        )


class FakePaperServiceController:
    def __init__(self) -> None:
        self.called_with = None

    def run(
        self,
        *,
        symbols,
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int,
    ):
        self.called_with = {
            "symbols": symbols,
            "quantity": quantity,
            "interval_seconds": interval_seconds,
            "max_cycles": max_cycles,
        }
        return {
            "cycles_completed": max_cycles,
            "last_cycle": {
                "cycle_status": "executed",
                "symbols": list(symbols),
            },
        }


class FakeMarketDayAutomationRunner:
    def __init__(self) -> None:
        self.called_with = None

    def run_market_day(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_heartbeats: int | None,
    ) -> MarketAutomationRunResult:
        self.called_with = {
            "symbols": symbols,
            "quantity": quantity,
            "interval_seconds": interval_seconds,
            "max_heartbeats": max_heartbeats,
        }
        return MarketAutomationRunResult(
            run_record=MarketAutomationRunRecord(
                run_id="automation-1",
                started_at_utc=datetime(2026, 4, 18, 13, 0, tzinfo=UTC),
                completed_at_utc=datetime(2026, 4, 18, 13, 30, tzinfo=UTC),
                trading_day="2026-04-18",
                status="completed",
                heartbeat_count=2,
                preopen_session_id="session-preopen-1",
                heartbeat_session_ids=("session-heartbeat-1", "session-heartbeat-2"),
                close_session_id="session-close-1",
                latest_replay_summary_id="replay-summary-1",
                latest_gate3_report_id="gate3-1",
                latest_gate3_package_id="gate3-package-1",
                summary="Automation completed.",
                evidence_refs=(
                    "artifacts/operator_platform/market_automation_runs/automation-1.json",
                ),
            ),
            run_record_path=Path(
                "artifacts/operator_platform/market_automation_runs/automation-1.json"
            ),
            session_paths=(),
            daily_digest_paths=(),
            replay_summary_path=Path(
                "artifacts/validation/replay_slippage_summaries/replay-summary-1.json"
            ),
            gate3_report_path=Path("artifacts/validation/gate3_reports/gate3-1.json"),
            gate3_package_path=Path(
                "artifacts/validation/gate3_packages/gate3-package-1.json"
            ),
        )


class FakeMarketDayScheduler:
    def __init__(self) -> None:
        self.called_with = None

    def run(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        poll_interval_seconds: int,
        max_scheduled_days: int | None,
        stop_event=None,
        state_callback=None,
    ) -> MarketDaySchedulerRunResult:
        self.called_with = {
            "symbols": symbols,
            "quantity": quantity,
            "interval_seconds": interval_seconds,
            "poll_interval_seconds": poll_interval_seconds,
            "max_scheduled_days": max_scheduled_days,
        }
        return MarketDaySchedulerRunResult(
            scheduled_days_completed=max_scheduled_days or 0,
            latest_schedule_record_path=Path(
                "artifacts/operator_platform/market_day_schedules/schedule-1.json"
            ),
        )


class FakeOperatorSupervisor:
    def __init__(self) -> None:
        self.called_with = None

    def run(
        self,
        *,
        poll_interval_seconds: int,
        telegram_poll_seconds: int,
        max_loops: int | None,
    ):
        self.called_with = {
            "poll_interval_seconds": poll_interval_seconds,
            "telegram_poll_seconds": telegram_poll_seconds,
            "max_loops": max_loops,
        }
        return {"status": "running", "child_status": "running"}


class FakeGateValidationController:
    def __init__(self) -> None:
        self.called_with = None

    def generate_gate_report(
        self,
        *,
        gate_id: str,
        benchmark_stack_payload: BenchmarkStackPayload,
        window_start_utc: datetime,
        window_end_utc: datetime,
        universe: tuple[str, ...],
        metric_visibility_context=None,
        dataset_manifest_id: str | None = None,
    ):
        self.called_with = {
            "gate_id": gate_id,
            "benchmark_stack_payload": benchmark_stack_payload,
            "window_start_utc": window_start_utc,
            "window_end_utc": window_end_utc,
            "universe": universe,
            "metric_visibility_context": metric_visibility_context,
            "dataset_manifest_id": dataset_manifest_id,
        }
        return {
            "report": {
                "gate_id": gate_id,
                "status": "pass",
            },
            "gate_assessment": {
                "gate_id": gate_id,
                "status": "pass",
            },
        }


def fake_gate_decision_brief() -> GateDecisionBrief:
    return GateDecisionBrief(
        gate_id="1",
        status="pass",
        decision_summary="Gate 1 passed for trend-following-v1.",
        required_operator_action=(
            "Review the evidence and decide whether to advance to Gate 2."
        ),
        generated_at_utc=datetime(2026, 4, 17, 21, 45, tzinfo=UTC),
        evidence_refs=("validation_reports/gate-1-20260417.json",),
        candidate_summaries=(
            GateDecisionCandidateSummary(
                candidate_id="trend-following-v1",
                status="pass",
                failed_criteria=(),
                summary="All Gate 1 criteria satisfied.",
            ),
        ),
        latest_open_positions=("SPY",),
        latest_cash=Decimal("10025.00"),
        latest_equity=Decimal("10030.00"),
        blocked_trade_count=1,
        reconciliation_failure_count=0,
        latest_alert_summary="stale_data blocked trade intent intent-1",
    )


@dataclass(frozen=True)
class FakeBenchmarkSeries:
    symbol: str
    closes: tuple[Decimal, ...]
    window_start_utc: datetime
    window_end_utc: datetime
    generated_at_utc: datetime
    feed: str
    adjustment: str
    series_is_adjusted: bool


class FakeBenchmarkGateway:
    def __init__(self) -> None:
        self.called_with = None

    def get_daily_close_series(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
        feed: str,
        adjustment: str,
    ) -> FakeBenchmarkSeries:
        self.called_with = {
            "symbol": symbol,
            "start_utc": start_utc,
            "end_utc": end_utc,
            "feed": feed,
            "adjustment": adjustment,
        }
        return FakeBenchmarkSeries(
            symbol=symbol,
            closes=(Decimal("100"), Decimal("101"), Decimal("102")),
            window_start_utc=start_utc,
            window_end_utc=end_utc,
            generated_at_utc=datetime(2026, 4, 17, 21, 30, tzinfo=UTC),
            feed=feed,
            adjustment=adjustment,
            series_is_adjusted=adjustment in {"dividend", "all"},
        )


@dataclass(frozen=True)
class FakeBenchmarkStack:
    payload: BenchmarkStackPayload

    def materialize(self, *, session_dates) -> BenchmarkStackPayload:
        del session_dates
        return self.payload


class FakeWebRunner:
    def __init__(self) -> None:
        self.called_with = None

    def __call__(self, config, *, host: str, port: int) -> None:
        self.called_with = {
            "config": config,
            "host": host,
            "port": port,
        }


class FakeControlCenterLauncher:
    def __init__(self) -> None:
        self.called_with = None

    def __call__(self, *, config, repo_root: Path, env_file: Path):
        self.called_with = {
            "config": config,
            "repo_root": repo_root,
            "env_file": env_file,
        }
        return {
            "status": "connected",
            "dashboard_url": f"http://{config.web.host}:{config.web.port}",
            "reused_existing_server": True,
        }


class FakeRuntimeActivationGateway:
    def __init__(
        self,
        activation: StrategyActivationRecord,
        snapshot: ApprovedWeightSnapshot,
    ) -> None:
        self._activation = activation
        self._snapshot = snapshot

    def load_or_create_active_records(
        self,
        symbols: tuple[str, ...],
    ) -> tuple[StrategyActivationRecord, ApprovedWeightSnapshot]:
        return self._activation, self._snapshot


class FakeRuntimeWarmupService:
    def __init__(self, warmup: HistoricalWarmupRecord) -> None:
        self._warmup = warmup

    def build_warmup(
        self,
        *,
        symbols: tuple[str, ...],
        benchmark_symbol: str,
        warmup_days: int,
        required_bar_count: int,
    ) -> HistoricalWarmupRecord:
        return self._warmup


class FakeRuntimePortfolioGateway:
    def get_portfolio_state(self) -> PortfolioState:
        return PortfolioState(
            as_of_utc=datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
            cash=Decimal("100000"),
            equity=Decimal("100000"),
            buying_power=Decimal("200000"),
            positions=(),
            open_orders=(),
        )


class FakeRuntimeOpportunityPlanner:
    def __init__(self, selection: OpportunitySelectionRecord) -> None:
        self._selection = selection

    def plan(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        activation: StrategyActivationRecord,
        model_snapshot: ApprovedWeightSnapshot,
        warmup: HistoricalWarmupRecord,
    ) -> OpportunitySelectionRecord:
        return self._selection


class FakeRuntimeService:
    def __init__(self) -> None:
        self.called_with = None

    def run(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None,
    ) -> dict[str, object]:
        self.called_with = {
            "symbols": symbols,
            "quantity": quantity,
            "interval_seconds": interval_seconds,
            "max_cycles": max_cycles,
        }
        return {"cycles_completed": max_cycles or 0}


def test_parser_exposes_market_day_scheduler_command() -> None:
    parser = cli.build_parser()
    choices = parser._subparsers._group_actions[0].choices

    assert "run-market-scheduler" in choices


def test_main_runs_statistical_report_command(tmp_path, capsys) -> None:
    def write_payload(name: str, payload: dict[str, object]) -> Path:
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        return path

    threshold = write_payload(
        "threshold",
        {
            "kind": "threshold_justification",
            "status": "valid",
            "blocker_codes": [],
        },
    )
    power = write_payload(
        "power",
        {
            "kind": "power_analysis_report",
            "status": "powered",
            "blocker_codes": [],
        },
    )
    bootstrap = write_payload(
        "bootstrap",
        {
            "kind": "bootstrap_report",
            "tail_stability_status": "stable",
            "blocker_codes": [],
        },
    )
    paired = write_payload(
        "paired",
        {
            "kind": "paired_benchmark_uncertainty_report",
            "status": "complete",
            "blocker_codes": [],
        },
    )
    trial_manifest = write_payload(
        "trial_manifest",
        {
            "kind": "trial_universe_manifest",
            "trial_statistics": {
                "effective_independent_trial_count": 42,
                "trial_correlation_estimate": "0.30",
                "selection_rule": "max_oos_sharpe_after_cpcv",
                "selected_strategy_rank": 1,
                "trial_sharpe_mean": "0.05",
                "trial_sharpe_variance": "0.20",
                "trial_return_skewness": "-0.10",
                "trial_return_kurtosis": "3.50",
                "failed_run_treatment": "failed_runs_counted_as_trials",
                "full_cpcv_pbo_matrix_ref": "cas://matrix/full-cpcv.json",
            },
        },
    )
    pbo = write_payload(
        "pbo",
        {
            "report_id": "pbo-eval-1",
            "full_cpcv_matrix_ref": "cas://matrix/full-cpcv.json",
        },
    )
    output = tmp_path / "reports" / "statistical.json"

    exit_code = cli.main(
        (
            "statistical-report",
            "--strategy-id",
            "trend-following-v1",
            "--threshold-justification",
            str(threshold),
            "--power-report",
            str(power),
            "--bootstrap-report",
            str(bootstrap),
            "--paired-benchmark-report",
            str(paired),
            "--trial-universe-manifest",
            str(trial_manifest),
            "--pbo-report",
            str(pbo),
            "--output-file",
            str(output),
        )
    )

    payload = json.loads(capsys.readouterr().out)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["kind"] == "statistical_validation_report"
    assert payload["promotion_valid"] is True
    assert payload == written


def test_main_prints_safe_config_summary(tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        "TRADINGX_WEB_WRITE_SIGNING_SECRET=super-secret\n"
        f"TRADINGX_DATA_ROOT={tmp_path / 'data'}\n",
        encoding="utf-8",
    )

    exit_code = cli.main(["config-summary", "--env-file", str(env_file)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_real_paper_credentials"] is True
    assert payload["artifact_root"] == "artifacts"
    assert "api_key" not in payload
    assert "super-secret" not in json.dumps(payload, sort_keys=True)
    assert payload["web_write_signing_configured"] is True


def test_main_runs_paper_roundtrip_command(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        f"TRADINGX_DATA_ROOT={tmp_path / 'data'}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli, "build_default_controller", lambda config: FakeController()
    )

    exit_code = cli.main(
        [
            "paper-roundtrip",
            "--env-file",
            str(env_file),
            "--symbol",
            "SPY",
            "--quantity",
            "1",
            "--log-dir",
            str(tmp_path / "artifacts"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["symbol"] == "SPY"
    assert payload["final_position_quantity"] == "0"


def test_main_runs_paper_loop_command(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        f"TRADINGX_DATA_ROOT={tmp_path / 'data'}\n",
        encoding="utf-8",
    )
    fake_controller = FakePaperLoopController()
    monkeypatch.setattr(
        cli,
        "build_default_paper_trading_controller",
        lambda config: fake_controller,
    )

    exit_code = cli.main(
        [
            "paper-loop",
            "--env-file",
            str(env_file),
            "--symbol",
            "SPY",
            "--quantity",
            "1",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert fake_controller.called_with == ("SPY", Decimal("1"))
    assert payload["terminal_state"] == "reconciled_trade"


def test_main_paper_loop_rejects_when_runtime_lock_is_held(
    monkeypatch, tmp_path, capsys
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        f"TRADINGX_DATA_ROOT={tmp_path / 'data'}\n",
        encoding="utf-8",
    )
    fake_controller = FakePaperLoopController()
    monkeypatch.setattr(
        cli,
        "build_default_paper_trading_controller",
        lambda config: fake_controller,
    )

    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    lock_path = data_root / "runtime.pid"
    with cli.runtime_process_lock(lock_path):
        exit_code = cli.main(
            [
                "paper-loop",
                "--env-file",
                str(env_file),
                "--symbol",
                "SPY",
                "--quantity",
                "1",
            ]
        )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert "already controls this data root" in payload["error"]
    assert fake_controller.called_with is None


def test_main_paper_loop_reports_authority_block_without_traceback(
    monkeypatch, tmp_path, capsys
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        f"TRADINGX_DATA_ROOT={tmp_path / 'data'}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli,
        "build_default_paper_trading_controller",
        lambda config: FakeAuthorityBlockedPaperLoopController(),
    )

    exit_code = cli.main(
        [
            "paper-loop",
            "--env-file",
            str(env_file),
            "--symbol",
            "SPY",
            "--quantity",
            "1",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload == {
        "status": "blocked",
        "error_type": "order_route_authority",
        "error": (
            "paper_order for trend-following-v1 is capped at research_only; "
            "requires paper_trading."
        ),
    }


def test_main_runs_recovery_command(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        f"TRADINGX_ARTIFACT_ROOT={tmp_path / 'artifacts'}\n"
        f"TRADINGX_DATA_ROOT={tmp_path / 'data'}\n",
        encoding="utf-8",
    )
    fake_controller = FakePaperLoopController()
    monkeypatch.setattr(
        cli,
        "build_default_paper_trading_controller",
        lambda config: fake_controller,
    )

    exit_code = cli.main(
        [
            "paper-recover",
            "--env-file",
            str(env_file),
            "--symbol",
            "SPY",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert fake_controller.recovered_symbol == "SPY"
    assert payload["recovered"] is True


def test_main_runs_paper_service_command(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        f"TRADINGX_ARTIFACT_ROOT={tmp_path / 'artifacts'}\n"
        f"TRADINGX_DATA_ROOT={tmp_path / 'data'}\n",
        encoding="utf-8",
    )
    fake_controller = FakePaperServiceController()
    monkeypatch.setattr(
        cli,
        "build_default_paper_service",
        lambda config: fake_controller,
    )

    exit_code = cli.main(
        [
            "run-paper-service",
            "--env-file",
            str(env_file),
            "--symbols",
            "SPY,QQQ",
            "--quantity",
            "1",
            "--interval-seconds",
            "300",
            "--max-cycles",
            "2",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert fake_controller.called_with == {
        "symbols": ("SPY", "QQQ"),
        "quantity": Decimal("1"),
        "interval_seconds": 300,
        "max_cycles": 2,
    }
    assert payload["cycles_completed"] == 2


def test_main_runtime_plan_command_writes_plan_artifact(
    monkeypatch, tmp_path, capsys
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\nALPACA_PAPER_API_SECRET=sk-paper\n",
        encoding="utf-8",
    )

    class FakePlanner:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def plan_for_service(self, *, symbols, portfolio_state):
            del portfolio_state
            timestamp = datetime(2026, 4, 19, 13, 30, tzinfo=UTC)
            snapshot = MarketSnapshot(
                symbol="SPY",
                last_trade_price=Decimal("100"),
                bid_price=Decimal("99.95"),
                ask_price=Decimal("100.05"),
                average_daily_volume_30d=Decimal("1500000"),
                timestamp=timestamp,
            )
            from tradingx.runtime_portfolio import (
                RuntimePortfolioPlan,
                RuntimePortfolioTrade,
            )

            return RuntimePortfolioPlan(
                plan_id="runtime-plan-1",
                generated_at_utc=timestamp,
                strategy_id="trend-following-v1",
                universe_snapshot_id="universe-spy",
                benchmark_symbol="SPY",
                crash_overlay_active=False,
                symbols_considered=symbols,
                current_weights={"SPY": Decimal("0.10")},
                target_weights={"SPY": Decimal("0.20")},
                trade_intents=(
                    TradeIntent(
                        intent_id="intent-spy",
                        candidate_id="trend-following-v1",
                        symbol="SPY",
                        side="buy",
                        quantity=Decimal("10"),
                        reason_code="target_weight_entry",
                        generated_at_utc=timestamp,
                    ),
                ),
                planned_trades=(
                    RuntimePortfolioTrade(
                        symbol="SPY",
                        side="buy",
                        reason_code="target_weight_entry",
                        last_trade_price=Decimal("100"),
                        current_weight=Decimal("0.10"),
                        target_weight=Decimal("0.20"),
                        current_quantity=Decimal("10"),
                        target_quantity=Decimal("20"),
                        delta_quantity=Decimal("10"),
                        no_trade_band_applied=False,
                    ),
                ),
                market_snapshots={"SPY": snapshot},
            )

    class FakePortfolioGateway:
        def __init__(self, trading_client) -> None:
            del trading_client

        def get_portfolio_state(self) -> PortfolioState:
            return PortfolioState(
                as_of_utc=datetime(2026, 4, 19, 13, 29, tzinfo=UTC),
                cash=Decimal("9000"),
                equity=Decimal("10000"),
                buying_power=Decimal("20000"),
                positions=(),
                open_orders=(),
            )

    activation_kwargs: list[dict[str, object]] = []

    class FakeActivationGateway:
        def __init__(self, *, store, runtime_snapshot_store=None, **kwargs) -> None:
            del store, runtime_snapshot_store
            activation_kwargs.append(kwargs)

        def load_or_create_active_records(self, symbols):
            del symbols
            return (
                StrategyActivationRecord(
                    activation_id="activation-1",
                    strategy_id="trend-following-v1",
                    strategy_version="1.0.0",
                    approved_symbols=("SPY",),
                    deploy_threshold=Decimal("0.5"),
                    allow_fallback_weights=True,
                    status="approved",
                    activated_at_utc=datetime(2026, 4, 19, 13, 0, tzinfo=UTC),
                    notes="Trend activation.",
                ),
                ApprovedWeightSnapshot(
                    snapshot_id="snapshot-1",
                    strategy_id="trend-following-v1",
                    status="approved",
                    generated_at_utc=datetime(2026, 4, 19, 13, 0, tzinfo=UTC),
                    minimum_supporting_trades=5,
                    weights={"signal": Decimal("1.0")},
                ),
            )

    monkeypatch.setattr(
        cli,
        "build_trading_client_for_mode",
        lambda config, decision: object(),
    )
    monkeypatch.setattr(
        cli,
        "build_market_data_gateway_for_mode",
        lambda config, *, broker_mode=None: object(),
    )
    monkeypatch.setattr(
        cli,
        "AlpacaPortfolioGateway",
        FakePortfolioGateway,
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "LocalActivationGateway",
        FakeActivationGateway,
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "RuntimePortfolioPlanner",
        FakePlanner,
        raising=False,
    )

    exit_code = cli.main(
        [
            "runtime-plan",
            "--env-file",
            str(env_file),
            "--symbols",
            "SPY",
            "--output-dir",
            str(tmp_path / "runtime-plan"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["strategy_id"] == "trend-following-v1"
    assert Path(payload["artifact_path"]).exists()
    assert activation_kwargs
    assert activation_kwargs[0]["legacy_non_authority_mode"] is True
    assert "promotion_decision_provider" not in activation_kwargs[0]
    assert "required_promotion_state" not in activation_kwargs[0]


def test_main_runtime_plan_command_reports_blocked_research_strategy(
    monkeypatch, tmp_path, capsys
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\nALPACA_PAPER_API_SECRET=sk-paper\n",
        encoding="utf-8",
    )

    class FakePlanner:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def plan_for_service(self, *, symbols, portfolio_state):
            del symbols, portfolio_state
            from tradingx.runtime_portfolio import UnsupportedRuntimePortfolioPlanError

            raise UnsupportedRuntimePortfolioPlanError(
                "Runtime portfolio planner only supports non-negative target weights "
                "for mean-reversion-v1."
            )

    class FakePortfolioGateway:
        def __init__(self, trading_client) -> None:
            del trading_client

        def get_portfolio_state(self) -> PortfolioState:
            return PortfolioState(
                as_of_utc=datetime(2026, 4, 19, 13, 29, tzinfo=UTC),
                cash=Decimal("9000"),
                equity=Decimal("10000"),
                buying_power=Decimal("20000"),
                positions=(),
                open_orders=(),
            )

    class FakeActivationGateway:
        def __init__(self, *, store, runtime_snapshot_store=None, **kwargs) -> None:
            del store, runtime_snapshot_store, kwargs

        def load_or_create_active_records(self, symbols):
            del symbols
            return (
                StrategyActivationRecord(
                    activation_id="activation-1",
                    strategy_id="mean-reversion-v1",
                    strategy_version="1.0.0",
                    approved_symbols=("SPY", "QQQ"),
                    deploy_threshold=Decimal("0.5"),
                    allow_fallback_weights=True,
                    status="approved",
                    activated_at_utc=datetime(2026, 4, 19, 13, 0, tzinfo=UTC),
                    notes="Mean reversion activation.",
                ),
                ApprovedWeightSnapshot(
                    snapshot_id="snapshot-1",
                    strategy_id="mean-reversion-v1",
                    status="approved",
                    generated_at_utc=datetime(2026, 4, 19, 13, 0, tzinfo=UTC),
                    minimum_supporting_trades=5,
                    weights={"signal": Decimal("1.0")},
                ),
            )

    monkeypatch.setattr(
        cli,
        "build_trading_client_for_mode",
        lambda config, decision: object(),
    )
    monkeypatch.setattr(
        cli,
        "build_market_data_gateway_for_mode",
        lambda config, *, broker_mode=None: object(),
    )
    monkeypatch.setattr(
        cli,
        "AlpacaPortfolioGateway",
        FakePortfolioGateway,
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "LocalActivationGateway",
        FakeActivationGateway,
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "RuntimePortfolioPlanner",
        FakePlanner,
        raising=False,
    )

    exit_code = cli.main(
        [
            "runtime-plan",
            "--env-file",
            str(env_file),
            "--symbols",
            "SPY,QQQ",
            "--output-dir",
            str(tmp_path / "runtime-plan"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "portfolio_planner_blocked"
    assert payload["strategy_id"] == "mean-reversion-v1"


def test_main_runtime_start_fails_closed_when_warmup_is_incomplete(
    monkeypatch, tmp_path, capsys
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        f"TRADINGX_ARTIFACT_ROOT={tmp_path / 'artifacts'}\n"
        f"TRADINGX_DATA_ROOT={tmp_path / 'data'}\n",
        encoding="utf-8",
    )
    activation = StrategyActivationRecord(
        activation_id="activation-1",
        strategy_id="baseline-long-only-v1",
        strategy_version="1.0.0",
        approved_symbols=("SPY", "QQQ"),
        deploy_threshold=Decimal("0.5"),
        allow_fallback_weights=True,
        status="approved",
        activated_at_utc=datetime(2026, 4, 19, 11, 0, tzinfo=UTC),
        notes="Baseline activation.",
    )
    snapshot = ApprovedWeightSnapshot(
        snapshot_id="snapshot-1",
        strategy_id="baseline-long-only-v1",
        status="approved",
        generated_at_utc=datetime(2026, 4, 19, 11, 5, tzinfo=UTC),
        minimum_supporting_trades=5,
        weights={
            "signal": Decimal("1.0"),
            "regime": Decimal("1.0"),
            "liquidity": Decimal("1.0"),
            "spread_penalty": Decimal("1.0"),
            "volatility_penalty": Decimal("1.0"),
            "portfolio_overlap_penalty": Decimal("1.0"),
            "execution_cost_penalty": Decimal("1.0"),
        },
    )
    warmup = HistoricalWarmupRecord(
        warmup_id="warmup-1",
        generated_at_utc=datetime(2026, 4, 19, 11, 30, tzinfo=UTC),
        benchmark_symbol="SPY",
        symbols=("SPY", "QQQ"),
        window_start_utc=datetime(2026, 2, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 18, tzinfo=UTC),
        required_bar_count=30,
        symbols_ready=("SPY",),
        symbols_blocked={"QQQ": "insufficient_bars"},
        return_summary={"SPY": {"cumulative_return": Decimal("0.02")}},
    )
    selection = OpportunitySelectionRecord(
        selection_id="selection-1",
        generated_at_utc=datetime(2026, 4, 19, 11, 35, tzinfo=UTC),
        strategy_id="baseline-long-only-v1",
        model_snapshot_id="snapshot-1",
        symbols_considered=("SPY", "QQQ"),
        ranked_opportunities=(
            OpportunityScore(
                symbol="SPY",
                base_signal=Decimal("0.5"),
                regime_weight=Decimal("1.0"),
                model_weight=Decimal("1.0"),
                liquidity_weight=Decimal("1.0"),
                spread_penalty=Decimal("0.1"),
                volatility_penalty=Decimal("0.1"),
                portfolio_overlap_penalty=Decimal("0.0"),
                execution_cost_penalty=Decimal("0.0"),
                final_score=Decimal("0.6"),
                eligible=True,
                ineligibility_reason="",
            ),
        ),
        selected_symbol="SPY",
        decision="selected",
        decision_reason="Top-ranked eligible opportunity.",
    )
    fake_service = FakeRuntimeService()
    activation_kwargs: list[dict[str, object]] = []

    def fake_activation_gateway(**kwargs):
        activation_kwargs.append(kwargs)
        return FakeRuntimeActivationGateway(activation, snapshot)

    monkeypatch.setattr(
        cli,
        "build_market_data_gateway_for_mode",
        lambda config, *, broker_mode=None: object(),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "LocalActivationGateway",
        fake_activation_gateway,
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "HistoricalWarmupService",
        lambda market_data_gateway: FakeRuntimeWarmupService(warmup),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "build_trading_client_for_mode",
        lambda config, decision: object(),
    )
    monkeypatch.setattr(
        cli,
        "AlpacaPortfolioGateway",
        lambda trading_client: FakeRuntimePortfolioGateway(),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "RuntimeOpportunityPlanner",
        lambda market_data_gateway: FakeRuntimeOpportunityPlanner(selection),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "build_runtime_host_trading_service",
        lambda config: fake_service,
        raising=False,
    )

    exit_code = cli.main(
        [
            "runtime-start",
            "--env-file",
            str(env_file),
            "--symbols",
            "SPY,QQQ",
            "--quantity",
            "1",
            "--interval-seconds",
            "300",
            "--max-cycles",
            "1",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["runtime_state"]["status"] == "halted"
    assert (
        payload["runtime_state"]["last_error"] == "Warmup incomplete for symbols: QQQ"
    )
    assert (
        Path(payload["runtime_state_path"])
        == tmp_path / "artifacts" / "operator_platform" / "runtime_host" / "state.json"
    )
    assert payload["service_result"] is None
    assert fake_service.called_with is None
    assert activation_kwargs
    assert activation_kwargs[0]["legacy_non_authority_mode"] is True
    assert "promotion_decision_provider" not in activation_kwargs[0]
    assert "required_promotion_state" not in activation_kwargs[0]


def test_main_prints_live_disable_status(tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        "TRADINGX_BROKER_MODE=paper\n"
        "TRADINGX_LIVE_CONFIG_ENABLED=false\n"
        "TRADINGX_MANUAL_KILL_SWITCH=true\n",
        encoding="utf-8",
    )

    exit_code = cli.main(["live-disable-status", "--env-file", str(env_file)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["manual_kill_switch_active"] is True
    assert payload["paper_only_mode"] is True
    assert payload["live_trading_enabled"] is False
    assert "broker_mode_not_live" in payload["disable_reasons"]


def test_main_runs_gate_report_command(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        "TRADINGX_SYMBOL_UNIVERSE=SPY,QQQ\n",
        encoding="utf-8",
    )
    benchmark_stack_file = tmp_path / "benchmark-stack.json"
    benchmark_stack_file.write_text(
        json.dumps(
            {
                "hurdle_returns": ["0.0001", "0.0001", "0.0001"],
                "opportunity_cost_returns": ["0.0002", "0.0002", "0.0002"],
                "opportunity_cost_weights": [
                    {"symbol": "SPY", "weight": "0.6"},
                    {"symbol": "AGG", "weight": "0.4"},
                ],
                "operating_constraint": {
                    "max_drawdown_design": "0.15",
                    "max_drawdown_halt": "0.25",
                    "cdar_threshold": "0.08",
                    "cdar_confidence": "0.95",
                },
            }
        ),
        encoding="utf-8",
    )
    fake_controller = FakeGateValidationController()
    monkeypatch.setattr(
        cli,
        "build_default_gate_validation_controller",
        lambda config, artifact_root: fake_controller,
    )

    exit_code = cli.main(
        [
            "gate-report",
            "--env-file",
            str(env_file),
            "--gate",
            "1",
            "--benchmark-stack-file",
            str(benchmark_stack_file),
            "--window-start",
            "2026-04-01",
            "--window-end",
            "2026-04-17",
            "--artifact-root",
            str(tmp_path / "validation"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert fake_controller.called_with == {
        "gate_id": "1",
        "benchmark_stack_payload": BenchmarkStackPayload(
            hurdle_returns=(Decimal("0.0001"), Decimal("0.0001"), Decimal("0.0001")),
            opportunity_cost_returns=(
                Decimal("0.0002"),
                Decimal("0.0002"),
                Decimal("0.0002"),
            ),
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
        "window_start_utc": datetime(2026, 4, 1, tzinfo=UTC),
        "window_end_utc": datetime(2026, 4, 17, tzinfo=UTC),
        "universe": ("SPY", "QQQ"),
        "metric_visibility_context": None,
        "dataset_manifest_id": None,
    }
    assert payload["gate_assessment"]["status"] == "pass"


def test_gate_report_cli_threads_registered_metric_visibility_context(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    from tradingx.experiments import ExperimentLedger

    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        "TRADINGX_DATA_ROOT=data\n"
        "TRADINGX_ARTIFACT_ROOT=artifacts\n"
        "TRADINGX_SYMBOL_UNIVERSE=SPY,QQQ\n",
        encoding="utf-8",
    )
    benchmark_stack_file = tmp_path / "benchmark-stack.json"
    benchmark_stack_file.write_text(
        json.dumps(
            {
                "hurdle_returns": ["0.0001", "0.0001", "0.0001"],
                "opportunity_cost_returns": ["0.0002", "0.0002", "0.0002"],
                "opportunity_cost_weights": [
                    {"symbol": "SPY", "weight": "0.6"},
                    {"symbol": "AGG", "weight": "0.4"},
                ],
                "operating_constraint": {
                    "max_drawdown_design": "0.15",
                    "max_drawdown_halt": "0.25",
                    "cdar_threshold": "0.08",
                    "cdar_confidence": "0.95",
                },
            }
        ),
        encoding="utf-8",
    )
    fake_controller = FakeGateValidationController()
    monkeypatch.setattr(
        cli,
        "build_default_gate_validation_controller",
        lambda config, artifact_root: fake_controller,
    )
    ledger = ExperimentLedger(ledger_root=tmp_path / "experiments")
    registration = json.loads(
        Path(
            "tests/fixtures/experiments/experiment_registration_pre_result.json"
        ).read_text(encoding="utf-8")
    )
    completed_run = json.loads(
        Path("tests/fixtures/experiments/experiment_run_completed.json").read_text(
            encoding="utf-8"
        )
    )
    started_run = dict(completed_run)
    started_run["lifecycle_status"] = "started"
    started_run["termination_reason_code"] = "started"
    ledger.append_registration(registration)
    ledger.append_run_record(started_run)
    ledger.append_run_record(completed_run)

    exit_code = cli.main(
        [
            "gate-report",
            "--env-file",
            str(env_file),
            "--gate",
            "1",
            "--benchmark-stack-file",
            str(benchmark_stack_file),
            "--window-start",
            "2026-04-01",
            "--window-end",
            "2026-04-17",
            "--experiment-id",
            "exp-001",
            "--run-id",
            "run-001",
            "--promotion-decision-scope",
            "scope-prod-001",
            "--metric-release-token",
            "sha256:" + "b" * 64,
            "--dataset-manifest-id",
            "dataset-spy-v1",
            "--experiment-ledger-root",
            str(tmp_path / "experiments"),
            "--dataset-manifest-file",
            "tests/fixtures/data_fingerprints/dataset_manifest_complete.json",
        ]
    )

    assert exit_code == 0
    _ = json.loads(capsys.readouterr().out)
    context = fake_controller.called_with["metric_visibility_context"]
    assert context.experiment_id == "exp-001"
    assert context.is_released is True
    assert fake_controller.called_with["dataset_manifest_id"] == "dataset-spy-v1"


def test_gate_report_cli_fake_metric_context_fails_closed(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        "TRADINGX_SYMBOL_UNIVERSE=SPY,QQQ\n",
        encoding="utf-8",
    )
    benchmark_stack_file = tmp_path / "benchmark-stack.json"
    benchmark_stack_file.write_text(
        json.dumps(
            {
                "hurdle_returns": ["0.0001"],
                "opportunity_cost_returns": ["0.0002"],
                "opportunity_cost_weights": [
                    {"symbol": "SPY", "weight": "0.6"},
                    {"symbol": "AGG", "weight": "0.4"},
                ],
                "operating_constraint": {
                    "max_drawdown_design": "0.15",
                    "max_drawdown_halt": "0.25",
                    "cdar_threshold": "0.08",
                    "cdar_confidence": "0.95",
                },
            }
        ),
        encoding="utf-8",
    )
    fake_controller = FakeGateValidationController()
    monkeypatch.setattr(
        cli,
        "build_default_gate_validation_controller",
        lambda config, artifact_root: fake_controller,
    )

    exit_code = cli.main(
        [
            "gate-report",
            "--env-file",
            str(env_file),
            "--gate",
            "1",
            "--benchmark-stack-file",
            str(benchmark_stack_file),
            "--window-start",
            "2026-04-01",
            "--window-end",
            "2026-04-17",
            "--experiment-id",
            "exp-fake",
            "--run-id",
            "run-fake",
            "--promotion-decision-scope",
            "scope-prod-001",
            "--metric-release-token",
            "sha256:" + "9" * 64,
            "--dataset-manifest-id",
            "dataset-fake",
        ]
    )

    assert exit_code == 0
    _ = json.loads(capsys.readouterr().out)
    context = fake_controller.called_with["metric_visibility_context"]
    assert context.is_released is False
    assert "trial_lineage_contaminated" in context.blocker_codes
    assert "point_in_time_data_incomplete" in context.blocker_codes


def test_compare_dataset_cli_marks_manual_review_when_old_raw_unavailable(
    tmp_path,
    capsys,
) -> None:
    old_manifest = json.loads(
        Path(
            "tests/fixtures/data_fingerprints/dataset_manifest_complete.json"
        ).read_text(encoding="utf-8")
    )
    new_manifest = dict(old_manifest)
    new_manifest["dataset_id"] = "dataset-spy-v2"
    new_manifest["normalized_frame_hashes"] = ["sha256:" + "b" * 64]
    old_path = tmp_path / "old.json"
    new_path = tmp_path / "new.json"
    old_path.write_text(json.dumps(old_manifest), encoding="utf-8")
    new_path.write_text(json.dumps(new_manifest), encoding="utf-8")

    exit_code = cli.main(
        [
            "compare-dataset",
            "--old",
            str(old_path),
            "--new",
            str(new_path),
            "--old-raw-unavailable",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["manual_review_required"] is True
    assert payload["required_action"] == "replay_required"


def test_experiment_run_cli_appends_started_then_completed_lifecycle(
    tmp_path,
    capsys,
) -> None:
    completed_run = json.loads(
        Path("tests/fixtures/experiments/experiment_run_completed.json").read_text(
            encoding="utf-8"
        )
    )
    started_run = dict(completed_run)
    started_run["lifecycle_status"] = "started"
    started_run["termination_reason_code"] = "started"
    started_path = tmp_path / "run-started.json"
    completed_path = tmp_path / "run-completed.json"
    started_path.write_text(json.dumps(started_run), encoding="utf-8")
    completed_path.write_text(json.dumps(completed_run), encoding="utf-8")

    assert (
        cli.main(
            [
                "start-experiment-run",
                "--ledger-root",
                str(tmp_path / "experiments"),
                "--run-file",
                str(started_path),
            ]
        )
        == 0
    )
    _ = capsys.readouterr()
    assert (
        cli.main(
            [
                "complete-experiment-run",
                "--ledger-root",
                str(tmp_path / "experiments"),
                "--run-file",
                str(completed_path),
            ]
        )
        == 0
    )
    _ = json.loads(capsys.readouterr().out)

    rows = [
        json.loads(line)
        for line in (tmp_path / "experiments" / "experiment_run_records.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [row["lifecycle_status"] for row in rows] == ["started", "completed"]


def test_main_prepares_benchmark_closes_artifact(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\nALPACA_PAPER_API_SECRET=sk-paper\n",
        encoding="utf-8",
    )
    output_file = tmp_path / "benchmarks" / "spy-dividend.json"
    fake_gateway = FakeBenchmarkGateway()
    fake_payload = BenchmarkStackPayload(
        hurdle_returns=(Decimal("0.0001"), Decimal("0.0001")),
        opportunity_cost_returns=(Decimal("0.0002"), Decimal("0.0002")),
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
    monkeypatch.setattr(
        cli,
        "build_default_market_data_gateway",
        lambda config: fake_gateway,
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "build_default_risk_free_series",
        lambda config: object(),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "build_default_benchmark_stack",
        lambda config, market_data_gateway, risk_free_series: FakeBenchmarkStack(
            fake_payload
        ),
        raising=False,
    )
    monkeypatch.setattr(
        cli.AlpacaRegularHoursCalendar,
        "session_dates_between",
        lambda self, start_utc, end_utc: (
            start_utc.date(),
            end_utc.date(),
        ),
    )

    exit_code = cli.main(
        [
            "prepare-benchmark-closes",
            "--env-file",
            str(env_file),
            "--window-start",
            "2026-04-01",
            "--window-end",
            "2026-04-17",
            "--output-file",
            str(output_file),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["output_file"] == str(output_file)
    artifact = json.loads(output_file.read_text(encoding="utf-8"))
    assert artifact["hurdle_returns"] == ["0.0001", "0.0001"]
    assert artifact["opportunity_cost_returns"] == ["0.0002", "0.0002"]


def test_main_prints_operator_evidence_report(tmp_path, capsys) -> None:
    artifacts_dir = tmp_path / "artifacts"
    (artifacts_dir / "trade_intents").mkdir(parents=True)
    (artifacts_dir / "trade_intents" / "intent-1.json").write_text(
        "{}",
        encoding="utf-8",
    )

    exit_code = cli.main(["evidence-report", "--artifact-root", str(artifacts_dir)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["trade_intents"] == 1


def test_main_prints_gate_decision_report(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "build_gate_decision_brief",
        lambda *, validation_store, paper_store, gate_id=None: (
            fake_gate_decision_brief()
        ),
        raising=False,
    )

    exit_code = cli.main(
        [
            "decision-report",
            "--gate",
            "1",
            "--validation-artifact-root",
            str(tmp_path / "validation"),
            "--paper-artifact-root",
            str(tmp_path / "paper_loop"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["brief"]["gate_id"] == "1"
    assert payload["alert"]["category"] == "gate"
    assert payload["alert"]["severity"] == "critical"


def test_evidence_report_defaults_to_paper_loop_root() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["evidence-report"])

    assert args.artifact_root == "artifacts/paper_loop"


def test_decision_report_parser_defaults() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["decision-report"])

    assert args.gate is None
    assert args.validation_artifact_root == "artifacts/validation"
    assert args.paper_artifact_root == "artifacts/paper_loop"


def test_run_paper_service_parser_defaults() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["run-paper-service"])

    assert args.symbols is None
    assert args.interval_seconds is None
    assert args.max_cycles is None


def test_gate_report_parser_defaults() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(
        [
            "gate-report",
            "--gate",
            "1",
            "--benchmark-closes-file",
            "closes.json",
            "--window-start",
            "2026-04-01",
            "--window-end",
            "2026-04-17",
        ]
    )

    assert args.env_file == ".env"
    assert args.artifact_root == "artifacts/validation"
    assert args.universe is None
    assert args.benchmark_adjusted is False
    assert args.experiment_id is None
    assert args.run_id is None
    assert args.metric_release_token is None
    assert args.dataset_manifest_id is None
    assert args.experiment_ledger_root is None
    assert args.dataset_manifest_file is None


def test_prepare_benchmark_closes_parser_defaults() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(
        [
            "prepare-benchmark-closes",
            "--window-start",
            "2026-04-01",
            "--window-end",
            "2026-04-17",
        ]
    )

    assert args.env_file == ".env"
    assert args.symbol == "SPY"
    assert args.feed == "iex"
    assert args.adjustment == "dividend"
    assert args.output_file is None


def test_refresh_risk_free_cache_parser_defaults() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["refresh-risk-free-cache"])

    assert args.output_file == "data/reference/risk_free_daily.csv"
    assert args.start == "2000-01-01"
    assert args.end is None
    assert args.max_age_days == 7
    assert args.force is False


def test_main_refreshes_risk_free_cache_when_missing(
    monkeypatch, tmp_path, capsys
) -> None:
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "needs_risk_free_refresh",
        lambda path, *, now_utc, max_age: True,
        raising=False,
    )

    def fake_refresh(
        cache_path: Path,
        *,
        start_date,
        end_date,
        now_utc,
        fetcher=None,
    ) -> Path:
        del fetcher
        calls["cache_path"] = cache_path
        calls["start_date"] = start_date
        calls["end_date"] = end_date
        calls["now_utc"] = now_utc
        return cache_path

    monkeypatch.setattr(cli, "refresh_risk_free_cache", fake_refresh, raising=False)

    exit_code = cli.main(
        [
            "refresh-risk-free-cache",
            "--output-file",
            str(tmp_path / "risk_free_daily.csv"),
            "--start",
            "2026-01-01",
            "--end",
            "2026-04-19",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "refreshed"
    assert payload["output_file"] == str(tmp_path / "risk_free_daily.csv")
    assert str(calls["start_date"]) == "2026-01-01"
    assert str(calls["end_date"]) == "2026-04-19"


def test_main_skips_risk_free_refresh_when_cache_is_fresh(
    monkeypatch, tmp_path, capsys
) -> None:
    cache_path = tmp_path / "risk_free_daily.csv"
    cache_path.write_text("date,annualized_rate,daily_rate\n", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "needs_risk_free_refresh",
        lambda path, *, now_utc, max_age: False,
        raising=False,
    )

    def unexpected_refresh(**kwargs):
        raise AssertionError("refresh_risk_free_cache should not be called")

    monkeypatch.setattr(
        cli,
        "refresh_risk_free_cache",
        unexpected_refresh,
        raising=False,
    )

    exit_code = cli.main(
        [
            "refresh-risk-free-cache",
            "--output-file",
            str(cache_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "fresh"
    assert payload["output_file"] == str(cache_path)


def test_main_runs_local_web_command(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        "TRADINGX_WEB_HOST=127.0.0.1\n"
        "TRADINGX_WEB_PORT=9010\n",
        encoding="utf-8",
    )
    fake_runner = FakeWebRunner()
    monkeypatch.setattr(cli, "run_web_app", fake_runner, raising=False)

    exit_code = cli.main(
        [
            "web",
            "--env-file",
            str(env_file),
            "--host",
            "127.0.0.1",
            "--port",
            "9020",
        ]
    )

    assert exit_code == 0
    assert fake_runner.called_with is not None
    assert fake_runner.called_with["host"] == "127.0.0.1"
    assert fake_runner.called_with["port"] == 9020


def test_main_runs_launch_control_center_command(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        "TRADINGX_WEB_HOST=127.0.0.1\n"
        "TRADINGX_WEB_PORT=9010\n",
        encoding="utf-8",
    )
    fake_launcher = FakeControlCenterLauncher()
    monkeypatch.setattr(
        cli,
        "launch_control_center",
        fake_launcher,
        raising=False,
    )

    exit_code = cli.main(
        [
            "launch-control-center",
            "--env-file",
            str(env_file),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "connected"
    assert payload["dashboard_url"] == "http://127.0.0.1:9010"
    assert fake_launcher.called_with is not None
    assert fake_launcher.called_with["env_file"] == env_file
    assert fake_launcher.called_with["repo_root"] == Path.cwd()


def test_main_reports_launch_control_center_errors(
    monkeypatch, tmp_path, capsys
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\nALPACA_PAPER_API_SECRET=sk-paper\n",
        encoding="utf-8",
    )

    def raise_error(*, config, repo_root: Path, env_file: Path):
        del config, repo_root, env_file
        raise cli.ControlCenterLaunchError("Control center did not become ready.")

    monkeypatch.setattr(
        cli,
        "launch_control_center",
        raise_error,
        raising=False,
    )

    exit_code = cli.main(
        [
            "launch-control-center",
            "--env-file",
            str(env_file),
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert payload["message"] == "Control center did not become ready."


def test_main_runs_replay_slippage_report_command(tmp_path, capsys) -> None:
    paper_store = cli.FilesystemArtifactStore(tmp_path / "paper_loop")
    paper_store.write_execution_lifecycle_record(
        ExecutionLifecycleRecord(
            execution_id="execution-1",
            intent_id="intent-1",
            symbol="SPY",
            side="buy",
            reason_code="baseline_long_entry",
            reference_price=Decimal("500.00"),
            fill_price=Decimal("500.25"),
            filled_qty=Decimal("1"),
            slippage_bps=Decimal("5.0"),
            bid_price=Decimal("499.80"),
            ask_price=Decimal("500.20"),
            average_daily_volume_30d=Decimal("1000000"),
            submitted_at_utc=datetime(2026, 4, 18, 8, 0, tzinfo=UTC),
            filled_at_utc=datetime(2026, 4, 18, 8, 0, tzinfo=UTC),
            recovered=False,
        )
    )

    exit_code = cli.main(
        [
            "replay-slippage-report",
            "--paper-artifact-root",
            str(tmp_path / "paper_loop"),
            "--validation-artifact-root",
            str(tmp_path / "validation"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["matched_execution_count"] == 1


def test_main_runs_market_day_automation_command(monkeypatch, capsys) -> None:
    fake_runner = FakeMarketDayAutomationRunner()
    monkeypatch.setattr(
        cli,
        "build_default_market_day_automation_runner",
        lambda config: fake_runner,
        raising=False,
    )

    exit_code = cli.main(
        [
            "run-market-day",
            "--symbols",
            "SPY,QQQ",
            "--quantity",
            "1",
            "--interval-seconds",
            "300",
            "--max-heartbeats",
            "2",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_record"]["heartbeat_count"] == 2
    assert fake_runner.called_with is not None
    assert fake_runner.called_with["symbols"] == ("SPY", "QQQ")


def test_main_runs_market_day_scheduler_command(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        "TRADINGX_SYMBOL_UNIVERSE=SPY,QQQ\n",
        encoding="utf-8",
    )
    fake_scheduler = FakeMarketDayScheduler()
    monkeypatch.setattr(
        cli,
        "build_default_market_day_scheduler",
        lambda config: fake_scheduler,
        raising=False,
    )

    exit_code = cli.main(
        [
            "run-market-scheduler",
            "--env-file",
            str(env_file),
            "--quantity",
            "1",
            "--interval-seconds",
            "300",
            "--poll-interval-seconds",
            "120",
            "--max-scheduled-days",
            "2",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scheduled_days_completed"] == 2
    assert fake_scheduler.called_with == {
        "symbols": ("SPY", "QQQ"),
        "quantity": Decimal("1"),
        "interval_seconds": 300,
        "poll_interval_seconds": 120,
        "max_scheduled_days": 2,
    }


def test_main_generates_dry_run_report_artifact(tmp_path, capsys) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    snapshot_store = ContentAddressedSnapshotStore(tmp_path / "snapshots")
    journal = SqliteOmsJournal(tmp_path / "journal.db")

    snapshot = DecisionSnapshotV1(
        schema_version=1,
        timestamp_utc=datetime(2026, 4, 20, 13, 45, tzinfo=UTC),
        cycle_correlation_id="cycle-1",
        session_snapshot_id="session-1",
        universe_snapshot_id="week1-spy",
        policy_snapshot_id="policy-1",
        model_snapshot_id="baseline",
        strategy_version="baseline-long-only-v1",
        strategy_config_hash="cfg-1",
        git_sha="abc1234",
        dry_run=True,
        market_data_window_hash="market-1",
        feature_snapshot_id="feature-1",
        session_start_equity=Decimal("100000"),
        candidate_intents=(
            CandidateIntentSnapshot(
                symbol="SPY",
                selected=True,
                terminal_reason="baseline_long_entry",
                base_score=Decimal("1"),
                final_score=Decimal("0.8"),
                eligibility="eligible",
                risk_status="approved",
            ),
        ),
        final_action="dry_run",
        risk_verdict_id="risk-1",
    )
    snapshot_store.write_decision_snapshot(snapshot)
    paper_store.write_service_cycle_snapshot(
        ServiceCycleSnapshot(
            cycle_id="cycle-1",
            started_at_utc=datetime(2026, 4, 20, 13, 45, tzinfo=UTC),
            completed_at_utc=datetime(2026, 4, 20, 13, 45, tzinfo=UTC),
            cycle_status="executed",
            symbols=("SPY",),
            symbol_results=(
                ServiceSymbolResult(
                    symbol="SPY",
                    terminal_state="dry_run",
                    reason_code="baseline_long_entry",
                    recovered=False,
                ),
            ),
            blocked_trade_count=0,
            reconciliation_failure_count=0,
            open_position_symbols=(),
            cash=Decimal("100000"),
            equity=Decimal("100000"),
            buying_power=Decimal("100000"),
        )
    )
    journal.append_event(
        event_type="simulated",
        recorded_at_utc=datetime(2026, 4, 20, 13, 45, tzinfo=UTC),
        decision_snapshot_id=snapshot.decision_snapshot_id,
        cycle_correlation_id="cycle-1",
        client_order_id="cid-1",
        broker_order_id="",
        symbol="SPY",
        side="buy",
        payload={
            "quantity": "1",
            "reason_code": "baseline_long_entry",
            "reference_price": "600.10",
            "would_submit_limit_price": "600.70",
        },
    )

    exit_code = cli.main(
        [
            "dry-run-report",
            "--paper-artifact-root",
            str(tmp_path / "paper_loop"),
            "--snapshot-root",
            str(tmp_path / "snapshots"),
            "--journal-path",
            str(tmp_path / "journal.db"),
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["artifact_path"].endswith(".json")
    assert payload["dry_run"] is True
    assert payload["cycle_count"] == 1


def test_main_reports_gates_0001_status(tmp_path, capsys) -> None:
    dry_run_report_path = tmp_path / "dry-run-report-2026-04-20.json"
    dry_run_report_path.write_text(
        json.dumps(
            {
                "blocked_intents": [{"reason": "daily_entry_cap_reached"}],
                "major_path_coverage": {
                    "entry": True,
                    "exit": True,
                    "halt": True,
                    "reject": True,
                    "recovery": True,
                },
                "anomalies": {
                    "unexpected_log_levels": [],
                    "reconciliation_flags": [],
                    "cycle_overruns": [],
                },
            }
        ),
        encoding="utf-8",
    )
    ops_root = tmp_path / "ops"
    ops_root.mkdir(parents=True, exist_ok=True)
    (ops_root / "operator_control_verification.json").write_text(
        json.dumps({"status": "pass"}),
        encoding="utf-8",
    )
    (ops_root / "premortem_review.json").write_text(
        json.dumps({"reviewers": ["snooze", "solo", "week1"]}),
        encoding="utf-8",
    )
    (ops_root / "sunday_rehearsal.json").write_text(
        json.dumps({"status": "pass"}),
        encoding="utf-8",
    )

    exit_code = cli.main(
        [
            "gates-0001-status",
            "--dry-run-report-path",
            str(dry_run_report_path),
            "--ops-artifact-root",
            str(ops_root),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["gate_id"] == "GATES-0001"
    assert payload["status"] == "pass"


def test_main_runs_week1_rehearsal_command(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=placeholder\nALPACA_PAPER_API_SECRET=placeholder\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli,
        "run_week1_rehearsal",
        lambda *, output_dir, account_state_provider: {
            "status": "pass",
            "artifacts": {"sunday_rehearsal": str(Path(output_dir) / "x.json")},
            "drills": [],
            "paper_account_starting_state": {"status": "skipped"},
        },
        raising=False,
    )

    exit_code = cli.main(
        [
            "week1-rehearsal",
            "--env-file",
            str(env_file),
            "--output-dir",
            str(tmp_path / "ops"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "pass"


def test_gate3_parser_defaults() -> None:
    parser = cli.build_parser()

    report_args = parser.parse_args(["gate3-report"])
    package_args = parser.parse_args(["gate3-package"])
    recovery_args = parser.parse_args(["recovery-drill"])
    alert_args = parser.parse_args(["alert-drill"])
    automation_args = parser.parse_args(["run-market-day"])
    scheduler_args = parser.parse_args(["run-market-scheduler"])

    assert report_args.env_file == ".env"
    assert report_args.paper_artifact_root == "artifacts/paper_loop"
    assert report_args.validation_artifact_root == "artifacts/validation"
    assert package_args.paper_artifact_root == "artifacts/paper_loop"
    assert package_args.validation_artifact_root == "artifacts/validation"
    assert recovery_args.symbol == "SPY"
    assert alert_args.channel == "smtp"
    assert automation_args.interval_seconds is None
    assert automation_args.max_heartbeats is None
    assert scheduler_args.poll_interval_seconds is None
    assert scheduler_args.max_scheduled_days is None


def test_operator_supervisor_parser_defaults() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["run-operator-supervisor"])

    assert args.env_file == ".env"
    assert args.interval_seconds is None
    assert args.poll_interval_seconds is None
    assert args.telegram_poll_seconds is None
    assert args.max_loops is None


def test_main_runs_operator_supervisor_command(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=placeholder\nALPACA_PAPER_API_SECRET=placeholder\n",
        encoding="utf-8",
    )
    fake_supervisor = FakeOperatorSupervisor()

    def _build_fake_supervisor(
        config,
        env_file,
        symbols,
        quantity,
        interval_seconds,
        poll_interval_seconds,
    ):
        del config, env_file, symbols, quantity, interval_seconds, poll_interval_seconds
        return fake_supervisor

    monkeypatch.setattr(
        cli,
        "build_default_operator_supervisor",
        _build_fake_supervisor,
    )

    exit_code = cli.main(
        [
            "run-operator-supervisor",
            "--env-file",
            str(env_file),
            "--max-loops",
            "1",
        ]
    )

    assert exit_code == 0
    assert fake_supervisor.called_with == {
        "poll_interval_seconds": 60,
        "telegram_poll_seconds": 5,
        "max_loops": 1,
    }
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "running"
