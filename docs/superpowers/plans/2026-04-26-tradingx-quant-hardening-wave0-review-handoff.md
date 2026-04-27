# TradingX Quant Hardening Wave 0 Review Handoff

Roadmap source: `docs/roadmap/tradingx_quant_hardening_execution_plan.md`

## Baseline

- Initial branch observed: `main`
- Implementation branch created: `codex/tradingx-quant-hardening`
- Initial commit observed: `71ab9c19afa077cdd83dc27742ae67de5f25159f`
- Python version through project environment: `Python 3.12.12`
- Pre-existing dirty file before implementation work: `docs/roadmap/tradingx_quant_hardening_execution_plan.md`
- Pre-existing roadmap diff at baseline: `1186 insertions(+), 17 deletions(-)`

Exact reviewed repository status after Wave 0 report creation:

```text
## codex/tradingx-quant-hardening
 M docs/roadmap/tradingx_quant_hardening_execution_plan.md
?? docs/reports/tradingx_quant_hardening_execution_tracker.md
?? docs/reports/wave0_baseline_audit_implementation_report.md
?? docs/reports/wave0_baseline_audit_review_report.md
?? docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md
```

Exact repository status after Wave 0 review fixes:

```text
## codex/tradingx-quant-hardening
 M docs/roadmap/tradingx_quant_hardening_execution_plan.md
?? docs/reports/tradingx_quant_hardening_execution_tracker.md
?? docs/reports/wave0_baseline_audit_fix_report.md
?? docs/reports/wave0_baseline_audit_implementation_report.md
?? docs/reports/wave0_baseline_audit_review_report.md
?? docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md
```

Exact repository status after Wave 0 re-review fixes:

```text
## codex/tradingx-quant-hardening
 M docs/roadmap/tradingx_quant_hardening_execution_plan.md
?? docs/reports/tradingx_quant_hardening_execution_tracker.md
?? docs/reports/wave0_baseline_audit_fix_report.md
?? docs/reports/wave0_baseline_audit_implementation_report.md
?? docs/reports/wave0_baseline_audit_rereview_report.md
?? docs/reports/wave0_baseline_audit_review_report.md
?? docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md
```

Exact repository status after Wave 0 third-review fixes:

```text
## codex/tradingx-quant-hardening
 M docs/roadmap/tradingx_quant_hardening_execution_plan.md
?? docs/reports/check_wave0_inventory.py
?? docs/reports/tradingx_quant_hardening_execution_tracker.md
?? docs/reports/wave0_baseline_audit_final_review_report.md
?? docs/reports/wave0_baseline_audit_fix_report.md
?? docs/reports/wave0_baseline_audit_handoff.md
?? docs/reports/wave0_baseline_audit_implementation_report.md
?? docs/reports/wave0_baseline_audit_rereview_report.md
?? docs/reports/wave0_baseline_audit_review_report.md
?? docs/reports/wave0_inventory_checker_output.md
?? docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md
```

## Validation Results

| Command | Result |
|---|---|
| `uv run pytest tests/unit/test_activation.py tests/unit/test_live_enablement.py tests/unit/test_risk.py tests/unit/test_pbo_compute.py` | Passed: 30 tests |
| `uv run pytest tests/unit/test_controlplane_repository_contracts.py tests/unit/test_controlplane_runtime_projector.py` | Passed: 21 tests |
| `uv run mypy src/tradingx` | Passed: no issues in 108 source files |
| `uv run ruff check .` | Passed: all checks passed |
| `rg -n -e StructuredRuntimeLogger -e "def write_" -e write_validation_report -e write_evaluation_evidence -e write_pbo_report -e write_gate_assessment src/tradingx` | Passed: non-empty structured log and writer inventory output |
| `rg -n -e generate_gate_report -e generate_decision_report -e generate_gate3_report -e generate_gate3_package -e generate_replay_slippage_report -e evidence-report -e decision-report -e gate-report -e gate3-report -e gate3-package -e replay-slippage-report -e dry-run-report -e gates-0001-status -e live-disable-status -e runtime-plan src/tradingx/web/runtime.py src/tradingx/web/app.py src/tradingx/__main__.py` | Passed: non-empty web runtime, web route, and CLI report surface output |
| `uv run python docs/reports/check_wave0_inventory.py --output docs/reports/wave0_inventory_checker_output.md` | Passed: parsed handoff rows directly; checked 95 blocker rows and 12 metric surfaces without relying on handoff self-matches |

## Current Authority-Like Data Paths

- Strategy activation records are handled by `LocalActivationGateway` in `src/tradingx/activation.py`.
- Activation and blueprint records are serialized through `src/tradingx/persistence/__init__.py`.
- Approved weight snapshots are loaded from `config/strategy/weights/` through `src/tradingx/weights.py`.
- Runtime portfolio planning consumes activation records and approved snapshots through `src/tradingx/runtime_portfolio.py`.
- The OMS journal is SQLite-backed and lives in `src/tradingx/journal.py`; the roadmap says it is not V5 authority.
- Control-plane Postgres outbox, projection state, runtime projector, document projector, and legacy bridge patterns live under `src/tradingx/controlplane/` and `src/tradingx/persistence/repositories/`.
- Existing live enablement remains fail-closed by default through `src/tradingx/live_enablement.py`, `src/tradingx/config.py`, and pre-trade checks in `src/tradingx/risk.py`.

## Current Metric-Producing And Promotion-Implying Surfaces

| Surface | File | Baseline classification |
|---|---|---|
| `runtime-plan` CLI | `src/tradingx/__main__.py:153`, `src/tradingx/__main__.py:420` | Operational planning readout; can influence runtime decisions but is not V5 authority |
| `live-disable-status` CLI | `src/tradingx/__main__.py:184`, `src/tradingx/__main__.py:660` | Operational control posture report; not V5 authority |
| `evidence-report` CLI | `src/tradingx/__main__.py:187`, `src/tradingx/__main__.py:665` | Metric-bearing legacy evidence surface; not V5 authority |
| `decision-report` CLI | `src/tradingx/__main__.py:190`, `src/tradingx/__main__.py:675` | Promotion-implying decision report surface; not V5 authority |
| `gate-report` CLI | `src/tradingx/__main__.py:231`, `src/tradingx/__main__.py:738` | Metric-producing and promotion-implying legacy validation surface; not V5 authority |
| `gate3-report` CLI | `src/tradingx/__main__.py:246`, `src/tradingx/__main__.py:768` | Promotion-implying readiness report surface; not V5 authority |
| `gate3-package` CLI | `src/tradingx/__main__.py:257`, `src/tradingx/__main__.py:778` | Promotion package generation surface; not V5 authority |
| `replay-slippage-report` CLI | `src/tradingx/__main__.py:276`, `src/tradingx/__main__.py:808` | Execution evidence report surface; not V5 authority |
| `dry-run-report` CLI | `src/tradingx/__main__.py:286`, `src/tradingx/__main__.py:818` | Operational dry-run report surface; not V5 authority |
| `gates-0001-status` CLI | `src/tradingx/__main__.py:304`, `src/tradingx/__main__.py:833` | Operational readiness/status surface; not V5 authority |
| `build_gate_report` | `src/tradingx/validation.py` | Metric-producing validation report builder; not V5 authority |
| `GateValidationController.generate_gate_report` | `src/tradingx/controller.py` | Metric-producing orchestrator and artifact writer caller; not V5 authority |
| Gate report web action `/api/actions/gate-report` | `src/tradingx/web/app.py` | Promotion-implying operator action surface; not V5 authority |
| Web report action routes | `src/tradingx/web/app.py:1193`, `src/tradingx/web/app.py:1209`, `src/tradingx/web/app.py:1268`, `src/tradingx/web/app.py:1274`, `src/tradingx/web/app.py:1281` | Web write routes that generate gate, decision, Gate 3, package, and replay-slippage reports; promotion-implying or metric-bearing but not V5 authority |
| `LocalWebActionRunner.generate_gate_report` | `src/tradingx/web/runtime.py:524` | Web runtime gate report generator; metric-bearing and promotion-implying legacy surface; not V5 authority |
| `LocalWebActionRunner.generate_decision_report` | `src/tradingx/web/runtime.py:575` | Web runtime decision report generator; promotion-implying legacy surface; not V5 authority |
| `LocalWebActionRunner.generate_gate3_report` | `src/tradingx/web/runtime.py:746` | Web runtime Gate 3 readiness report generator; promotion-implying legacy surface; not V5 authority |
| `LocalWebActionRunner.generate_gate3_package` | `src/tradingx/web/runtime.py:760` | Web runtime Gate 3 package generator; promotion-implying legacy package surface; not V5 authority |
| `LocalWebActionRunner.generate_replay_slippage_report` | `src/tradingx/web/runtime.py:776` | Web runtime replay-slippage report generator; execution evidence surface; not V5 authority |
| Web read models | `src/tradingx/web/readmodels.py` | Promotion-implying display surface for gate, runtime, activation, and validation state; not V5 authority |
| Gate decision brief/reporting | `src/tradingx/reporting.py` | Promotion-implying report surface; not V5 authority |
| `EvaluationEvidencePack` and `PBOReport` | `src/tradingx/types.py` | Metric-bearing legacy evidence types; not V5 authority |
| `evaluate_candidate` | `src/tradingx/evaluation.py:406` | Metric-bearing research evaluation surface that computes candidate and benchmark metrics, adversarial checks, deflated Sharpe when available, and recommendation; exploratory legacy evidence, not V5 authority |
| `run_buy_and_hold_smoke_backtest` and `summarize_returns` | `src/tradingx/backtest.py:136`, `src/tradingx/backtest.py:197` | Research backtest metric surface producing strategy, benchmark, active, CAGR, Sharpe, and max-drawdown metrics; exploratory legacy evidence, not V5 authority |
| `scripts/run_backtest.py` | `scripts/run_backtest.py:44`, `scripts/run_backtest.py:54` | Report-like CLI script that prints backtest metric JSON; exploratory metric output, not V5 authority |
| `scripts/compare_vol_forecasts.py` forecast metrics | `scripts/compare_vol_forecasts.py:199`, `scripts/compare_vol_forecasts.py:290`, `scripts/compare_vol_forecasts.py:522` | Research comparison script producing forecast metrics, backtest metrics, material winner fields, JSON/Markdown artifacts, and printed JSON; exploratory artifact writer, not V5 authority |
| `TrialsLedger` | `src/tradingx/trials.py` | Existing SQLite trial statistics source; legacy until registered experiment universe exists |
| `StructuredRuntimeLogger.log` | `src/tradingx/runtime_logging.py` | Structured JSONL runtime log producer; operational surface that can carry metric or blocker fields; not V5 authority |
| Benchmark close and stack writers | `src/tradingx/validation.py` | Metric/input artifact writers; legacy inputs until V5 replay artifacts exist |
| Decision snapshot writer | `src/tradingx/snapshots.py` | Operational decision artifact writer; not V5 authority |
| Backtest and drift reference writers | `src/tradingx/drift/backtest_reference.py`, `src/tradingx/drift/reference.py` | Metric/reference artifact writers; not V5 authority |
| Dry-run report writer | `src/tradingx/dry_run_report.py` | Operational/report artifact writer; not V5 authority |
| Operator offset writer | `src/tradingx/operator_control.py` | Operational state writer; not V5 authority |
| Filesystem trade, order, risk, reconciliation, service-cycle, runtime-plan writers | `src/tradingx/persistence/__init__.py` | Operational artifact writers; not V5 authority |
| Filesystem evidence, validation, gate assessment, CPCV, and PBO writers | `src/tradingx/persistence/__init__.py` | Metric-bearing and promotion-implying artifact writers; not V5 authority |
| Filesystem activation, blueprint activation, model snapshot, opportunity selection, and runtime host writers | `src/tradingx/persistence/__init__.py` | Authority-like mutable artifact writers; must be legacy/projection-only under V5 |
| Filesystem Gate 3, replay slippage, drift verdict, and sleeve attribution writers | `src/tradingx/persistence/__init__.py` | Evidence/operational artifact writers; not V5 authority |

## Current Blocker-Like Strings And Gaps

| String | Source path | Emitting surface | Current meaning | Deterministic V5 cap at baseline | Required registry or migration treatment |
|---|---|---|---|---|---|
| `missing_requirements` | `src/tradingx/controlplane/projections.py`; tests | Control-plane projection readiness | Domain has no registered source requirements | No | Register as non-promotion operational readiness blocker or map to V5 authority registry if reused in promotion output |
| `outbox_dedupe_constraint_missing` | `src/tradingx/controlplane/projections.py`; tests | Control-plane projection readiness | Outbox dedupe constraint is not confirmed | No | Keep operational or map to ledger/outbox integrity blocker if promotion output consumes it |
| `missing_sources` | `src/tradingx/controlplane/projections.py`; tests | Control-plane projection readiness | Required source status row is missing | No | Keep operational or map to replay/source availability blocker if reused |
| `initial_import_incomplete` | `src/tradingx/controlplane/projections.py`; tests | Control-plane projection readiness | Initial import evidence is missing | No | Keep operational or map to replay/source readiness blocker if reused |
| `write_path_inactive` | `src/tradingx/controlplane/projections.py`; tests | Control-plane projection readiness | Active bridge or dual-write evidence is missing | No | Keep operational; do not treat as promotion authority |
| `unprojected_sources` | `src/tradingx/controlplane/projections.py`; tests/docs | Control-plane projection readiness | Projected watermark has not caught source watermark | No | Keep operational; mark read-model projection status as non-authority |
| `stale_sources` | `src/tradingx/controlplane/projections.py`; tests | Control-plane projection readiness | Mutable source freshness window failed | No | Keep operational or map to stale evidence blocker when V5 evidence freshness consumes it |
| `lagging_sources` | `src/tradingx/controlplane/projections.py`; tests | Control-plane projection readiness | Source lag exceeds readiness limit | No | Keep operational; do not use as promotion cap without registry row |
| `not_ready_sources` | `src/tradingx/controlplane/projections.py`; tests | Control-plane projection readiness | Source status row is explicitly not ready | No | Keep operational; do not use as promotion cap without registry row |
| `blocked` | `src/tradingx/controlplane/projections.py` | Control-plane projection readiness summary | Fallback status when no higher-priority readiness code applies | No | Keep as generic operational status; do not emit as V5 blocker |
| `operator_hold` | `tests/unit/test_controlplane_repository_contracts.py`; integration tests | Runtime control posture fixture | Operator posture blocker | No | Register as operational-only or V5 manual/operator blocker if promotion output consumes it |
| `requested_mode_unknown` | `src/tradingx/controlplane/projectors.py` | Runtime projector control posture | Requested broker/runtime mode is unknown | No | Map to V5 state-action/runtime-mode blocker if order-capable routes consume it |
| `dry_run_enabled` | `src/tradingx/config.py`; `src/tradingx/controlplane/projectors.py`; web | Live-disable/control posture | Dry-run mode remains active | No | Keep as live disablement operational blocker; do not authorize promotion |
| `live_enable_evidence_missing` | `src/tradingx/controlplane/projectors.py`; tests | Runtime projector control posture | Required live enablement evidence is missing | No | Later Wave 8 should map to live authority/pre-trade evidence blockers |
| `manual_kill_switch_active` | `src/tradingx/config.py`; `src/tradingx/controlplane/projectors.py`; web/tests | Live-disable/control posture | Manual kill switch is active | No | Keep highest-priority operational runtime blocker; never waivable by promotion |
| `market_data_degraded` | `src/tradingx/controlplane/projectors.py` | Runtime projector control posture | Market data posture degraded | No | Later data/runtime waves should map to stale or degraded data controls |
| `insufficient_bars` | `src/tradingx/historical.py`; tests | Historical warmup/runtime host | Symbol lacks enough bars for warmup | No | Keep operational/data readiness; map to replay/data completeness only if promotion uses it |
| `cpcv_insufficient_history` | `src/tradingx/validation.py`; tests/docs | Validation CPCV orchestration | Candidate lacks enough history for CPCV | No | Wave 4 should register as statistical validation blocker or pending status if emitted in promotion output |
| `halt_by_operator` | `src/tradingx/types.py`; tests/docs | Sleeve failure reason | Sleeve halted by operator control | No | Operational-only unless used as runtime refusal; if reused, register with runtime enforcement mapping |
| `drift_alarm_live` | `src/tradingx/types.py`; tests/docs | Sleeve failure reason | Live drift alarm blocks sleeve | No | Later drift/change-control waves should map to drift monitor blocker |
| `sleeve_sharpe_below_threshold_6m` | `src/tradingx/types.py`; tests/docs | Sleeve failure reason | Six-month live sleeve Sharpe below threshold | No | Later recertification/statistical waves should map to evidence decay or drift blocker |
| `regime_stressed` | `src/tradingx/types.py`; docs | Sleeve failure reason | Regime stress blocks sleeve | No | Operational strategy runtime status; not promotion authority |
| `regime_stressed_liquidate` | `src/tradingx/sleeves/regime_gate.py`; tests/docs | Sleeve trade rationale | Regime stress liquidation rationale | No | Trade rationale, not a V5 blocker unless runtime refusal consumes it |
| `insufficient_history` | `src/tradingx/types.py`; sleeve tests/docs | Sleeve failure reason/trade rationale | Sleeve lacks enough history | No | Runtime/data readiness status; Wave 3 or 4 should register only if promotion output emits it |
| `broker_mode_not_live` | `src/tradingx/config.py:435`; `src/tradingx/web/app.py:1373` | Live-disable and web control posture | Requested broker mode is not live | No | Keep operational live-disable blocker; map to V5 state-action/runtime-mode blocker if live authority consumes it |
| `missing_live_credentials` | `src/tradingx/config.py:437`; tests | Live-disable, data, and web control posture | Real live broker credentials are absent | No | Keep operational live-disable blocker; never treat missing credentials as promotable state |
| `config_layer_disabled` | `src/tradingx/config.py:439`; tests | Live-disable control posture | Live config layer opt-in is disabled | No | Keep operational live-disable blocker; map to Wave 8 live enablement authority checks |
| `env_layer_disabled` | `src/tradingx/config.py:441`; tests | Live-disable control posture | Environment live opt-in is disabled | No | Keep operational live-disable blocker; map to Wave 8 live enablement authority checks |
| `code_layer_disabled` | `src/tradingx/config.py:443` | Live-disable control posture | Code-level live guard is disabled | No | Keep operational live-disable blocker; map to Wave 8 live enablement authority checks |
| `web_write_signing_unconfigured` | `src/tradingx/config.py:445`; `src/tradingx/web/app.py:1378` | Live-disable and web write posture | Signed web writes are not configured | No | Keep web governance blocker; Wave 1 trust roots must avoid treating unsigned web writes as authority |
| `operator_signoff_missing` | `src/tradingx/web/app.py:436`; tests | Web control posture | Operator sign-off is missing | No | Treat as legacy web governance blocker until approval identity/signature records exist |
| `gate4_checklist_missing` | `src/tradingx/web/app.py:437` | Web control posture | Gate 4 checklist is incomplete | No | Treat as legacy web governance blocker; do not map to V5 authority without signed approval artifacts |
| `non_positive_quantity` | `src/tradingx/risk.py:132` | Pre-trade risk control | Order quantity is not positive | No | Keep pre-trade risk blocker; Wave 1 order-route guard must not bypass it |
| `invalid_symbol` | `src/tradingx/risk.py:134` | Pre-trade risk control | Symbol format is invalid | No | Keep pre-trade risk blocker; map as operational order refusal if surfaced in V5 reports |
| `live_mode_disabled` | `src/tradingx/risk.py:136` | Pre-trade risk control | Live order attempted while live mode remains disabled | No | Keep live pre-trade blocker; Wave 1/Wave 8 authority guard must fail closed here |
| `liquidity_filter` | `src/tradingx/risk.py:138`; tests | Pre-trade risk control | Average daily volume is below minimum | No | Keep pre-trade risk blocker; later capacity/liquidity evidence may map it into V5 execution feasibility |
| `price_floor` | `src/tradingx/risk.py:140`; `src/tradingx/opportunity.py:59` | Pre-trade risk and opportunity filter | Last trade price is below minimum | No | Keep operational market-quality blocker; register if emitted by promotion/report outputs |
| `single_symbol_concentration` | `src/tradingx/risk.py:196`; `src/tradingx/risk.py:207` | Pre-trade risk control | Resulting exposure breaches single-symbol concentration cap | No | Keep pre-trade risk blocker; later allocation governance should map to portfolio mandate constraints |
| `intraday_margin` | `src/tradingx/risk.py:230` | Pre-trade risk control | Incremental exposure exceeds buying power | No | Keep pre-trade risk blocker; later financing/account governance should map to account constraints |
| `stale_market_data` | `src/tradingx/risk.py:235`; tests | Pre-trade risk and service cycle control | Market data timestamp is stale | No | Keep runtime data-readiness blocker; Wave 3/Wave 8 should map to replay/data freshness controls |
| `stale_broker_state` | `src/tradingx/risk.py:240`; tests | Pre-trade risk and reconciliation control | Broker state timestamp is stale | No | Keep runtime state-readiness blocker; Wave 8 should map to live reconciliation controls |
| `kill_switch` | `src/tradingx/risk.py:154`; tests | Pre-trade risk control | Kill switch blocks order | No | Keep highest-priority runtime blocker; V5 authority must never waive kill switch |
| `operator_halt` | `src/tradingx/controller.py:467`; tests | Trading loop manual control | Operator halt blocks entry | No | Keep runtime/manual blocker; map to scoped operator authority only if signed exception flow exists |
| `outside_regular_hours` | `src/tradingx/controller.py:526`; `src/tradingx/policy.py:236` | Trading loop and policy control | New entry attempted outside regular session | No | Keep operational session blocker; map to execution semantics if promotion route depends on sessions |
| `insufficient_buying_power` | `src/tradingx/execution.py:66`; tests | Broker rejection classifier | Broker rejected order for buying power | No | Keep broker rejection code; Wave 5/Wave 8 should map to financing and reconciliation evidence |
| `restricted_symbol` | `src/tradingx/execution.py:68` | Broker rejection classifier | Broker rejected restricted symbol | No | Keep broker rejection code; later instrument package should map restricted instruments to eligibility blockers |
| `symbol_halted` | `src/tradingx/execution.py:70` | Broker rejection classifier | Broker rejected halted symbol | No | Keep broker rejection code; map to execution semantics and market halt controls if promoted |
| `after_hours` | `src/tradingx/execution.py:72` | Broker rejection classifier | Broker rejected after-hours order | No | Keep broker rejection code; map to session execution semantics if promoted |
| `market_closed` | `src/tradingx/execution.py:74`; `src/tradingx/service.py:163` | Broker rejection and service cycle status | Market is closed | No | Keep operational session status; do not treat as V5 blocker unless emitted in promotion/runtime refusal |
| `malformed_payload` | `src/tradingx/execution.py:76` | Broker rejection classifier | Broker rejected malformed or invalid payload | No | Keep execution error code; V5 order guard should fail before malformed payload reaches broker |
| `broker_rejected` | `src/tradingx/execution.py:77` | Broker rejection classifier | Fallback broker rejection reason | No | Keep generic execution rejection; later reports should preserve broker message without implying promotion authority |
| `kill_switch_active` | `src/tradingx/policy.py:234` | Entry policy control | Policy kill switch blocks entry | No | Keep policy blocker; align with runtime kill-switch semantics before V5 authority can route orders |
| `daily_drawdown_halt_sticky` | `src/tradingx/policy.py:242` | Entry policy control | Sticky drawdown halt from prior trigger blocks entry | No | Keep policy blocker; later mandate/allocation governance should map to drawdown halt controls |
| `daily_drawdown_halt` | `src/tradingx/policy.py:248` | Entry policy control | Current drawdown trigger blocks entry | No | Keep policy blocker; later mandate/allocation governance should map to drawdown halt controls |
| `close_window_entry_blocked` | `src/tradingx/policy.py:254` | Entry policy control | Close-window ladder blocks new entry | No | Keep policy blocker; map to execution/session constraints if promoted |
| `stale_quote` | `src/tradingx/policy.py:255`; `src/tradingx/service.py:498` | Entry policy and service cycle control | Quote age exceeds staleness threshold | No | Keep quote-quality blocker; Wave 5/Wave 8 should map to quote-quality and stale-data controls |
| `spread_absolute_cap` | `src/tradingx/policy.py:257` | Entry policy control | Absolute spread exceeds cap | No | Keep execution quality blocker; Wave 5 should map to cost/quote-quality evidence |
| `spread_relative_cap` | `src/tradingx/policy.py:259` | Entry policy control | Relative spread exceeds cap | No | Keep execution quality blocker; Wave 5 should map to cost/quote-quality evidence |
| `daily_entry_cap_reached` | `src/tradingx/policy.py:261` | Entry policy control | Daily new-entry cap is reached | No | Keep operational risk blocker; later allocation governance should map to mandate limits |
| `per_symbol_entry_cap_reached` | `src/tradingx/policy.py:264` | Entry policy control | Per-symbol daily entry cap is reached | No | Keep operational risk blocker; later allocation governance should map to symbol-level limits |
| `max_concurrent_positions_reached` | `src/tradingx/policy.py:268` | Entry policy control | Max concurrent position count is reached | No | Keep operational risk blocker; later allocation governance should map to portfolio constraints |
| `same_session_reentry_cooldown` | `src/tradingx/policy.py:272` | Entry policy control | Same-session re-entry cooldown blocks symbol | No | Keep operational execution blocker; map to state-action contract only if promotion uses it |
| `total_deployed_cap_reached` | `src/tradingx/policy.py:283` | Entry policy control | Total deployed capital cap is reached | No | Keep allocation/risk blocker; Wave 2 should map to capital allocation governance |

### Roadmap-Defined Deterministic V5 Blockers

| String | Source path | Emitting surface | Current meaning | Deterministic V5 cap at baseline | Required registry or migration treatment |
|---|---|---|---|---|---|
| `authority_artifact_invalid` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:99` | Roadmap requirement | Authority-bearing artifact missing, unsigned, tampered, out-of-sequence, unauthoritative, or not replayable | `disabled` | Seed Wave 1 canonical registry with disabled cap and enforce before any authority-bearing artifact can authorize state |
| `ledger_key_worm_controls_missing` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:100` | Roadmap requirement | Signing-key custody, role registry, immutable backup/WORM, restore, or recovery quorum controls missing | `disabled` | Seed Wave 1 canonical registry with disabled cap; legacy filesystem authority cannot bypass it |
| `state_action_contract_missing` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:101` | Roadmap requirement | Promotion state lacks allowed-action contract or modules exceed the state contract | `disabled` | Seed Wave 1 canonical registry and require runtime refusal for disallowed state-action pairs |
| `replay_path_missing` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:102` | Roadmap requirement | Raw data, normalized frames, code, configuration, decision input, or authority input cannot be retrieved from content-addressed storage | `research_only` | Seed registry and cap affected evidence to research-only until replay refs are complete |
| `tax_account_financing_unspecified` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:103` | Roadmap requirement | Tax mode, account type, financing assumptions, or pre-tax/after-tax status is missing or unspecified | `paper_shadow` | Seed registry and require mandate/account evidence before capital-bearing state |
| `after_tax_edge_missing_for_taxable_account` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:104` | Roadmap requirement | Taxable capital lacks after-tax lower-bound net edge evidence without a hard mandate cap | `paper_trading` | Seed registry and require after-tax lower-bound evidence or mandate cap |
| `jurisdiction_account_use_unknown` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:105` | Roadmap requirement | Jurisdiction, account-use category, broker permission, margin permission, or eligibility unknown | `paper_trading` | Seed registry and require account/jurisdiction eligibility evidence |
| `external_capital_compliance_unknown` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:106` | Roadmap requirement | External-capital fiduciary, suitability, marketing, custody, retention, or account restriction status missing | `disabled` | Seed registry with disabled cap; external-capital paths remain unavailable without compliance evidence |
| `utility_definition_missing` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:107` | Roadmap requirement | Portfolio utility, defensive threshold, benchmark policy, mandate, capital role, thesis, or allocation policy missing | `research_only` | Seed registry and require signed mandate/utility artifacts before promotion beyond research |
| `strategy_materiality_policy_missing` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:108` | Roadmap requirement | Strategy-scale-aware materiality policy missing or fixed defaults are used where tighter thresholds are required | `paper_shadow` | Seed registry and require materiality policy before promotion beyond paper shadow |
| `lower_bound_net_edge_undefined` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:109` | Roadmap requirement | Lower-bound net edge estimator, confidence/posterior level, horizon, dependence correction, tail treatment, pairing, prior, or sample size undefined | `research_only` | Seed registry and require declared lower-bound methodology before promotion-valid evidence |
| `net_edge_lower_bound_below_threshold` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:110` | Roadmap requirement | Capital-bearing promotion has lower-bound net edge below declared threshold after costs, financing, tax where modeled, benchmark pairing, and capacity stress | `research_only` | Seed registry and enforce cap from evidence evaluator output |
| `trial_lineage_contaminated` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:111` | Roadmap requirement | Prior metric exposure, metric-vault bypass, missing immutable capture, or contradicted selection influence | `research_only` | Seed registry and require clean registered lineage before promotion-valid statistics |
| `trial_universe_incomplete` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:112` | Roadmap requirement | Registered, failed, canceled, related, or selection-influencing trials missing from decision universe | `paper_shadow` | Seed registry and require complete trial universe evidence |
| `dsr_pbo_inputs_incomplete` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:113` | Roadmap requirement | DSR/PBO/MCS inputs or full CPCV/PBO matrix incomplete | `paper_shadow` | Seed registry and require full statistical input matrix before promotion-valid DSR/PBO |
| `point_in_time_data_incomplete` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:114` | Roadmap requirement | PIT universe membership, symbol mapping, delisting returns, vendor timestamps, or replay inputs missing | `research_only` | Seed registry and require PIT replay artifacts before data-dependent claims promote |
| `execution_semantics_incomplete` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:115` | Roadmap requirement | Order, venue, partial/non-fill, queue/adverse-selection, halt/open/close, rate limit, or opportunity-cost semantics unmodeled | `paper_shadow` | Seed registry and require execution semantics package before execution-dependent promotion |
| `execution_sample_power_missing` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:116` | Roadmap requirement | Cost/execution evidence lacks powered bucket-level samples for intended route | `paper_shadow` | Seed registry and require powered execution sample evidence |
| `capacity_lower_bound_missing` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:117` | Roadmap requirement | Capacity is point estimate, extrapolated beyond validated range, or lacks lower-bound capacity curve | `paper_shadow` | Seed registry and require lower-bound capacity evidence |
| `live_sample_requirement_unmet` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:118` | Roadmap requirement | Minimum live/probe orders, notional, sessions, quote-quality coverage, reconciliation cycles, or adverse events unmet | `tiny_live_probe` | Seed registry and cap until Wave 8 live/probe sample evidence exists |
| `pre_trade_control_missing` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:119` | Roadmap requirement | Live order entry lacks required price, notional/share, open-order, duplicate, disconnect, self-trade, or missing-control rejects | `paper_trading` | Seed registry and require runtime pre-trade enforcement before live orders |
| `short_legal_mechanics_missing` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:120` | Roadmap requirement | Short runtime path lacks locate, marking, expiry, threshold/close-out, recall/buy-in, or hard-to-borrow semantics | `research_only` | Seed registry and require short capability package before negative exposures |
| `instrument_package_missing` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:121` | Roadmap requirement | Instrument class lacks support package for data, execution, margin, settlement, corporate actions, tax, and risk semantics | `research_only` | Seed registry and require instrument support package |
| `optimizer_or_sizing_lockbox_missing` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:122` | Roadmap requirement | Utility lambdas, baselines, feature sets, sizing caps, optimizer settings, or selection rules were not frozen before OOS/nested validation | `paper_shadow` | Seed registry and require lockbox evidence before optimizer/sizing promotion |
| `drift_monitor_spec_missing` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:123` | Roadmap requirement | Drift monitor variables, windows, thresholds, regimes, multiple-testing policy, latency, or demotion rules missing | `paper_shadow` | Seed registry and require drift monitor spec before production candidate promotion |

### Roadmap-Defined Provisional Registry Seed Codes

| String | Source path | Emitting surface | Current meaning | Deterministic V5 cap at baseline | Required registry or migration treatment |
|---|---|---|---|---|---|
| `capacity_extrapolation_risk` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2023`, `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2035` | Roadmap Wave 1 seed requirement | Target scale is outside validated capacity range or relies on unsupported extrapolation | `paper_shadow` | Seed Wave 1 registry with paper-shadow cap and require lower-bound capacity evidence or scale reduction |
| `unsupported_side` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2024`, `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2036` | Roadmap Wave 1 seed requirement | Strategy emits unsupported side or exposure sign | `research_only` | Seed Wave 1 registry; legacy negative-side artifacts remain diagnostic until state-action/instrument support exists |
| `short_support_missing` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2024`, `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2037` | Roadmap Wave 1 seed requirement | Negative or short exposure lacks complete short capability, locate, borrow, financing, and broker semantics | `research_only` | Seed Wave 1 registry and map to Wave 7 short-side capability package |
| `pending_threshold` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2024`, `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2038` | Roadmap Wave 1 seed requirement | Required threshold justification is absent or declared after metric exposure | `paper_shadow` | Seed Wave 1 registry and require signed pre-metric threshold or clean lockbox rerun |
| `legacy_statistical_evidence` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2025`, `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2039` | Roadmap Wave 1 seed requirement | Old evidence lacks registered trial universe, power, bootstrap, paired benchmark, or full PBO artifacts | `paper_shadow` | Seed Wave 1 registry and treat old evidence as diagnostic until rerun through registered validation |
| `unsupported_cost_bucket` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2025`, `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2040` | Roadmap Wave 1 seed requirement | Intended execution bucket lacks powered samples and no defensible fallback exists | `paper_shadow` | Seed Wave 1 registry and require bucket evidence, conservative fallback, or route exclusion |
| `unrecorded_material_change` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2026`, `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2041` | Roadmap Wave 1 seed requirement | Current approved code, data, config, schema, broker, or evidence hash differs without change-control record | `paper_shadow` | Seed Wave 1 registry and require change-control record plus recertification |
| `dependency_scope_unresolved` | `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2026`, `docs/roadmap/tradingx_quant_hardening_execution_plan.md:2042` | Roadmap Wave 1 seed requirement | Change or restatement cannot be mapped to affected evidence and decisions | `paper_shadow` | Seed Wave 1 registry and require dependency index coverage before approval remains valid |

No `src/tradingx/promotion.py`, `src/tradingx/authority.py`, `schemas/quant/`, `artifacts/quant/ledger/`, or `artifacts/quant/store/` implementation exists at baseline.

## Gap Map To V5 Authority

| Existing Path | Baseline Status | V5 Gap |
|---|---|---|
| Activation records | Mutable filesystem artifacts | Must become projections from append-only ledger decisions, not authority |
| Approved weight snapshots | Config-backed operator artifacts | Must be classified as legacy unless ledger-authorized |
| OMS journal | Append-only SQLite operational log | Must not be reused as authority ledger |
| Postgres outbox/projectors | Operational control-plane projection pattern | Must not imply quant promotion authority without V5 ledger/artifact refs |
| Gate reports and validation evidence | Metric-bearing research evidence | Must be labeled exploratory or legacy until registered, replayable, and promotion-valid |
| Evaluation candidate evidence | Metric-bearing research evidence with recommendations | Must be tied to registered trials, metric-vault/lineage controls, replay refs, and non-authority labels before promotion use |
| Backtest scripts and smoke reports | Research and diagnostic metric output | Must be labeled exploratory and replay-bound; printed JSON or Markdown artifacts cannot authorize promotion |
| Volatility forecast comparison script | Research model-selection metric output and artifact writer | Must be registered before metric exposure and tied to lockbox/change-control evidence before any model selection can promote |
| PBO/CPCV evidence | Existing statistical machinery | Must be tied to registered trial universe and full matrix refs in later waves |
| Web read models/actions | Operator display/action surfaces | Must label non-V5 artifacts as non-authority and avoid implied promotion |
| Live enablement and risk controls | Disabled/fail-closed default | Must add V5 order-route authority guard before any order-capable route can imply authorization |

## Notes For Review

- The roadmap file was dirty before this work began and has not been staged.
- No production or runtime authority was added in Wave 0.
- The branch switch required elevated filesystem permission to create the local git ref.
- Fresh review loops are capped at three iterations per wave by user instruction; the third-review findings were fixed and validated with `docs/reports/check_wave0_inventory.py`.
