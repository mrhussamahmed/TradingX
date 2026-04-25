# TradingX Quant Hardening Execution Plan

Status: locked specification / implementation-planning-ready
Date locked: 2026-04-25

This document is the canonical execution program for hardening TradingX into a replayable, fail-closed, statistically defensible quantitative trading system.

It does not claim that TradingX is production-ready. It defines the program required before production claims can be made.

## Final Standard

"World-class" means:

- every claim has an estimator
- every estimator has an artifact
- every artifact has a replay path
- every promotion has a failure mode
- every live action has a safety override
- every production approval expires unless recertified

"Bulletproof" does not mean "cannot lose money." It means the system cannot pass weak evidence as strong evidence, cannot trade unsupported semantics, cannot silently ignore risk, and fails closed when uncertainty rises.

## Promotion States

Every strategy/configuration lives in exactly one state:

```text
disabled -> research_only -> paper_shadow -> paper_trading -> tiny_live_probe -> production
```

Promotion above `research_only` requires executable semantics. Promotion above `paper_shadow` requires promotion-valid evidence. Promotion to `production` requires complete evidence, live-probe recertification where applicable, capacity inside validated range, and unexpired production approval.

### State Action Contracts

Promotion state is not just a label. Each state has an executable allowed-action contract:

| State | Data / Broker Access | Order Permission | Capital Ceiling | Short Permission | Required Runtime Controls |
|---|---|---|---|---|---|
| `disabled` | No activation; artifact replay only. | None. | None. | None. | Activation refusal. |
| `research_only` | Offline or research data only. | No paper or live orders. | None. | Research simulation only, explicitly labeled. | Research labeling and no activation path. |
| `paper_shadow` | Real-time or historical data may be consumed; no order route. | Shadow decisions only; no broker order submission. | None. | Shadow short signals only if labeled unsupported until short package exists. | Stale-data checks and activation refusal for order-capable routes. |
| `paper_trading` | Paper broker/simulator route only. | Paper orders only. | No real capital. | Paper shorting only when paper/live semantic mismatch is disclosed. | Idempotency, reconciliation, stale-data checks, quote-quality checks, kill switch, and paper/live mismatch labeling. |
| `tiny_live_probe` | Approved live broker route for the approved probe only. | Real orders only within signed probe limits. | Probe plan capital/loss/order/notional limits. | Live shorts only with complete short-side package and locate/financing controls. | Full pre-trade controls, idempotency, reconciliation, stale-data checks, kill switch, clock health, safety drills, rollback/flatten. |
| `production` | Approved live broker route for approved strategy and account use. | Real orders within mandate, allocation, capacity, and recertification limits. | Approved production allocation and capacity range. | Only with production-valid short-side package. | All live controls, pre-trade market-access controls, monitoring, drift checks, incident handling, and unexpired recertification. |

If any module interprets a state more permissively than this contract, activation fails with `state_action_contract_missing`.

## Program-Level Locks

Every milestone must demonstrate:

- one passing case from artifacts alone
- one fail-closed case from artifacts alone
- a migration rule for existing artifacts
- an enforcement point that refuses unsupported promotion or runtime use
- a golden replay that reproduces or invalidates an old decision

Implementation proceeds vertical-slice first:

```text
schema -> artifact -> blocker -> CLI report -> activation refusal -> golden replay
```

Milestone 0 defines the mandate, objectives, constraints, benchmarks, capital roles, and allocation governance. Milestone 1 creates the enforcement spine. Milestones 2-10 attach additional evidence types and blockers to that spine.

## Trust Model Invariant

Activation state is a projection, never a source of truth.

The source of truth for promotion state, evidence classification, approvals, amendments, and recertification is an append-only, content-addressed ledger. Mutable files under `config/` may cache the latest projection for operator readability, but they cannot authorize activation, production, live probe, recertification, or exception handling.

Every authority-bearing artifact must include:

- canonical payload hash
- schema version
- content-addressed artifact URI
- ledger sequence
- previous ledger hash
- writer identity
- role/authority reference
- signature or approval record reference
- timestamp from an auditable clock source
- replay input references

Any missing, invalid, unsigned, tampered, out-of-sequence, or non-replayable authority artifact blocks promotion and runtime activation. A local edit to a projection file must be detected as projection drift, not accepted as a state transition.

The ledger threat model must include signing-key custody, key rotation, key revocation, role-registry versioning, WORM or equivalent immutable backups, restore tests, and quorum/identity rules for key or ledger recovery. Missing key-management or immutable-backup controls produce `ledger_key_worm_controls_missing` and disable authority-bearing promotion until corrected.

Promotion-valid replay requires retained immutable inputs, not hashes alone. If raw data, normalized frames, code versions, configuration, or decision inputs cannot be retrieved from a content-addressed artifact store, the evidence is not replay-valid.

Research registration also has a pre-result boundary: promotion-valid runs must be registered before metrics are visible. Out-of-band exploratory work must be attested, and unregistered work cannot become invisible simply because it was not cited.

## Non-Discretionary Production Blockers

The following caps are deterministic. They are not advisory severity labels and cannot be waived by expert judgment, opportunity-cost pressure, manual approval, or retrospective explanation. The promotion engine must emit the named blocker and cap the state exactly as specified until the missing artifact, invalid assumption, or unsafe condition is corrected through the signed append-only authority model.

| Blocker | Condition | Max State |
|---|---|---|
| `authority_artifact_invalid` | Any authority-bearing artifact is missing, unsigned, tampered, out-of-sequence, unauthoritative, or not replayable from retained immutable inputs. | `disabled` |
| `ledger_key_worm_controls_missing` | Signing-key custody, rotation/revocation, role-registry versioning, immutable backup/WORM retention, restore test, or recovery quorum controls are missing. | `disabled` |
| `state_action_contract_missing` | A promotion state lacks an executable allowed-action contract or any module permits data, broker, order, capital, short, or runtime-control behavior beyond that state's contract. | `disabled` |
| `replay_path_missing` | Raw data, normalized frames, code version, configuration, decision input, or referenced authority input cannot be retrieved from content-addressed storage. | `research_only` |
| `tax_account_financing_unspecified` | Tax mode, account type, financing assumptions, or pre-tax/after-tax status is missing or `unspecified`. | `paper_shadow` |
| `after_tax_edge_missing_for_taxable_account` | Taxable capital lacks after-tax lower-bound net edge evidence and the mandate does not hard-cap the strategy below live capital use. | `paper_trading` |
| `jurisdiction_account_use_unknown` | Jurisdiction, account-use category, regulatory/compliance status, broker permission, margin permission, or instrument/account eligibility is unknown. | `paper_trading` |
| `external_capital_compliance_unknown` | Advisory, client, fund, retirement, or other external-capital use lacks required fiduciary, suitability/IPS, marketing/hypothetical-performance, custody, record-retention, or account-restriction status. | `disabled` |
| `utility_definition_missing` | Portfolio utility, defensive utility threshold, benchmark policy, mandate, capital role, wealth thesis, or allocation policy is missing. | `research_only` |
| `strategy_materiality_policy_missing` | Strategy-scale-aware materiality policy is missing, or fixed defaults are used when turnover, volatility, expected edge, sample length, decision sensitivity, or allocation sensitivity require tighter thresholds. | `paper_shadow` |
| `lower_bound_net_edge_undefined` | Lower-bound net edge lacks a predeclared estimator, confidence/posterior level, horizon, serial-dependence correction, skew/fat-tail treatment, benchmark pairing, prior when Bayesian, and minimum effective sample size. | `research_only` |
| `net_edge_lower_bound_below_threshold` | Capital-bearing promotion has lower-bound net edge below the predeclared threshold after costs, slippage, financing, tax treatment where modeled, benchmark pairing, and capacity stress. | `research_only` |
| `trial_lineage_contaminated` | Prior metric exposure cannot be ruled out, metric vault controls were bypassed, immutable notebook/script/output capture is missing, or selection influence is contradicted by artifacts. | `research_only` |
| `trial_universe_incomplete` | Registered, failed, canceled, related, or selection-influencing trials are missing from the promotion-decision universe. | `paper_shadow` |
| `dsr_pbo_inputs_incomplete` | DSR/PBO/MCS evidence lacks effective independent trial count, trial correlation, selection rule, selected-strategy rank, non-normality inputs, failed-run treatment, or full CPCV/PBO matrix. | `paper_shadow` |
| `point_in_time_data_incomplete` | Point-in-time universe membership, symbol mapping, delisting returns, bitemporal vendor timestamps, or replayable raw/normalized inputs are missing for a data-dependent claim. | `research_only` |
| `execution_semantics_incomplete` | Order type, venue/broker semantics, partial/non-fill behavior, queue/adverse-selection handling, halt/open/close behavior, rate limits, or non-fill opportunity cost is unmodeled for the promoted execution path. | `paper_shadow` |
| `execution_sample_power_missing` | Execution/cost evidence lacks powered bucket-level sample requirements or cannot prove coverage for intended order type, venue, liquidity, spread, volatility, session, and participation buckets. | `paper_shadow` |
| `capacity_lower_bound_missing` | Capacity is a point estimate, extrapolated beyond validated range, or lacks a lower-confidence/posterior-bound capacity curve at proposed scale. | `paper_shadow` |
| `live_sample_requirement_unmet` | Minimum live/probe order count, filled notional, sessions, quote-quality coverage, reconciliation cycles, or adverse-event coverage is not met. | `tiny_live_probe` |
| `pre_trade_control_missing` | Live order entry lacks price collars, fat-finger notional/share limits, max open orders, duplicate prevention, cancel-on-disconnect, self-trade prevention where relevant, or reject-on-missing-control behavior. | `paper_trading` |
| `short_legal_mechanics_missing` | Short-emitting runtime path lacks order marking, locate documentation, locate expiry, threshold-security/close-out handling, recall/forced-buy-in handling, or broker-specific hard-to-borrow semantics. | `research_only` |
| `instrument_package_missing` | Instrument class is not covered by a promotion-valid instrument support package defining data, execution, margin, settlement, corporate-action, tax, and risk semantics. | `research_only` |
| `optimizer_or_sizing_lockbox_missing` | Utility lambdas, baselines, feature sets, sizing caps, optimizer settings, or selection rules were not frozen before OOS evaluation or nested validation/final lockbox is missing. | `paper_shadow` |
| `drift_monitor_spec_missing` | Production candidate lacks drift monitor specification for monitored variables, reference windows, thresholds, regime labels, multiple-testing policy, alert latency, and demotion rules. | `paper_shadow` |

If multiple blockers apply, the strictest cap wins. `research_only` exploration may continue under research labels, but no capital-bearing promotion, live probe, production approval, or allocation increase may rely on evidence capped below the requested state.

## V5 Governance Protocol

### Final Blocking Rule

Evidence cannot support `production` if any of the following are true:

- artifact schema is missing or unversioned
- required artifact field is missing
- data restatement materiality is undefined
- tax/account type is `unspecified`
- financing assumptions are `unspecified`
- capacity evidence is extrapolated beyond validated notional range
- human override authority is undefined
- materiality threshold is undefined
- portfolio utility function is undefined
- replay path is missing
- recertification trigger is undefined

These cases use the deterministic caps in `Non-Discretionary Production Blockers`. No blocker in this list may be escalated by discretionary severity judgment.

### Materiality Defaults

A change is material if any are true:

Default numeric thresholds are maximum tolerances, not safe harbors. A strategy-specific materiality policy must tighten them when turnover, volatility, expected edge, sample length, decision sensitivity, allocation sensitivity, or instrument class makes the default too coarse.

- any split, dividend, or corporate action changes
- any daily return changes by `>= 5 bps`
- cumulative benchmark return changes by `>= 25 bps`
- candidate CAGR changes by `>= 25 bps/year`
- Sharpe changes by `>= 0.05`
- MDD/CDaR changes by `>= 25 bps`
- any gate outcome changes
- any trade decision would have changed
- any production safety rule would have changed
- any strategy-specific materiality threshold would have fired

### Authority Boundary

- Low-risk exception: one operator, max one trading day
- Medium-risk exception: operator plus reviewer, max five trading days
- High-risk exception: two approvers, explicit rollback condition, no auto-renewal
- No exception may disable kill switch, reconciliation, stale-data checks, or idempotency

Approval is not a free-text JSON field. Authority records must be bound to a verifiable operator identity, role registry, approval scope, expiry, canonical payload hash, and signature. Missing identity registry, missing signature, stale role registry, or write authorization failure blocks live probe, production, recertification, and manual exceptions.

### Objective Hierarchy

Portfolio-level objectives dominate sleeve-local objectives:

1. Operational safety
2. Liquidity and execution feasibility
3. Portfolio drawdown/CDaR limits
4. Portfolio-level utility after costs
5. Sleeve-level utility
6. Return maximization

A defensive sleeve can pass by reducing drawdown even if CAGR is lower. A return sleeve cannot pass by raising CAGR while violating portfolio drawdown, liquidity, operational, capacity, or cost constraints.

### Capacity, Tax, And Financing

Every strategy must declare:

- target capital scale
- max participation rate
- max order notional
- liquidity bucket
- instrument support package
- expected cost curve as notional scales
- capacity limit where lower-bound net edge no longer exceeds the predeclared threshold
- lower-bound capacity curve at proposed scale
- whether evidence was generated at intended scale or extrapolated
- account type
- jurisdiction/account-use category
- regulatory/compliance status
- taxable/tax-exempt status
- tax treatment assumption
- dividend treatment
- borrow fee treatment
- financing/cash yield assumption
- short dividend liability assumption
- whether results are pre-tax or after-tax

`capacity_extrapolation_risk` blocks `production`.

`unspecified` tax/account/financing caps evidence at `paper_shadow`.

`jurisdiction_account_use_unknown` blocks live trading and caps evidence at `paper_trading`.

`after_tax_edge_missing_for_taxable_account` blocks live capital use and caps evidence at `paper_trading`.

`instrument_package_missing` caps evidence at `research_only`.

### Production Recertification

Production is temporary, not permanent.

Strategy production approval decays to `paper_shadow` or `research_only` when:

- evidence pack becomes stale
- data vendor changes
- broker API semantics change
- cost model changes materially
- feature/model/optimizer code changes materially
- universe changes
- live drift monitor fails
- quote quality degrades
- performance exits confidence bounds
- emergency control fires
- strategy has not traded for its predeclared inactivity window

Periodic recertification:

- monthly operational review
- quarterly statistical review
- immediate review after any material or critical change

## Milestone Status

| Milestone | Status |
|---|---|
| 0. Investment Mandate & Capital Allocation Governance | Locked specification / planning-ready |
| 1. Governance Spine | Locked specification / planning-ready |
| 2. Experiment Registration & Trial Universe | Locked specification / planning-ready |
| 3. Data Restatement & Fingerprinting | Locked specification / planning-ready |
| 4. Validation Evidence Engine | Locked specification / planning-ready |
| 5. Cost, Quote Quality & Capacity Instrumentation | Locked specification / planning-ready |
| 6. Portfolio Utility & Optimizer Gates | Locked specification / planning-ready |
| 7. Expected Return & Sizing Governance | Locked specification / planning-ready |
| 8. Short-Side Capability & Financing | Locked specification / planning-ready |
| 9. Live Probe & Operational Safety | Locked specification / planning-ready |
| 10. Recertification & Change Control | Locked specification / planning-ready |

These milestones are not instructions to implement all eleven at once. Many referenced modules and schema directories do not exist yet. Milestone 0 defines the mandate and capital allocation policy requirements that later evidence must satisfy. The next architecture work item is still a thin implementation slice for Milestone 1 that creates the trust spine, ledger, artifact store interface, schema validator, CLI report, activation refusal, and golden replay.

## Milestone 0: Investment Mandate & Capital Allocation Governance

### Goal

Define why TradingX exists: to compound capital through controlled exposure to validated positive-edge strategies, while preserving survival, liquidity, and operational control.

### Core Rule

TradingX's mission is capital growth. Governance and statistical validation are filters, not the objective. No strategy receives capital unless it has a falsifiable wealth thesis, mandate-compatible benchmark, capital role, risk budget, and scale-up/down policy.

### Scope Boundary

Milestone 0 defines blockers, objectives, constraints, and allocation policy requirements. It does not prove edge. Milestones 4-9 produce the evidence fields: lower-bound net edge, statistical validity, costs, capacity, attribution confidence, optimizer validity, sizing validity, short-side support, and live readiness.

### Prime Directive

TradingX must:

1. Preserve survival.
2. Generate positive net wealth contribution.
3. Allocate capital to stronger validated opportunities.
4. Scale exposure only when evidence, capacity, and operations support it.
5. Reduce or remove capital from decaying or unproductive strategies.
6. Measure opportunity cost without letting it override governance blockers.

Risk control is the immune system. Capital growth is the mission.

### Trust Model

All Milestone 0 artifacts are authority-bearing and must include:

- `schema_version`
- `artifact_uri`
- `payload_hash`
- `ledger_sequence`
- `approval_record_refs`
- `authority_ref`
- `created_at_utc`
- `replay_input_refs`

Fields like `approved_by` are insufficient unless backed by the signed append-only authority model from Milestone 1.

### Schemas

`investment_mandate` defines account type, base currency, starting capital, target scale, allowed/forbidden instruments, leverage, shorting, liquidity, tax, FX, margin policies, drawdown/CDaR limits, daily/weekly loss limits, ruin threshold, forced de-risking rules, and external cash-flow policy.

`benchmark_policy` defines ex-ante benchmark set, cash/risk-free benchmark, investable market benchmark, 60/40 or mandate-appropriate alternative, no-trade/current-holdings baseline, simple ETF alternative, exclusions, and tax/account/liquidity/instrument compatibility.

`jurisdiction_account_use_manifest` defines jurisdiction, account-use category, account owner/operator role, self-directed proprietary/advisory/client/fund/retirement/margin classification, broker permissions, margin permissions, instrument eligibility, short eligibility, fiduciary-duty status, client suitability/IPS status, marketing/hypothetical-performance status, custody status, record-retention status, account-specific restriction status, applicable compliance review refs, and live-trading ceiling when any status is unknown.

`instrument_support_package` defines instrument class, data semantics, total-return/corporate-action treatment, execution venues/order types, settlement cycle, margin requirements, short/borrow semantics, tax treatment, risk model, operational controls, broker permissions, and promotion ceiling. Any instrument outside a valid package is `instrument_package_missing`.

`strategy_capital_role` defines role as one of: `growth_candidate`, `defensive_candidate`, `diversifier`, `cash_management`, `research_only`, `inactive`.

`wealth_thesis` defines mechanism exploited, persistence reason, beneficiary regime, benchmark it must beat, failure condition, edge decay detector, capacity limit, and kill condition.

`capital_allocation_policy` defines initial allocation, max strategy/sleeve allocation, reserve policy, reinvestment policy, scale-up/down rules, cooldowns, and repeated-look / strategy-churn controls.

`capital_scaling_decision` defines current allocation, proposed allocation, action, lower-bound net edge status, attribution confidence, capacity status, drawdown status, single-period dominance status, cooldown status, and blockers.

`lower_bound_net_edge_spec` defines estimator family, frequentist confidence level or Bayesian posterior credibility level, return horizon, benchmark pairing, serial-dependence/HAC or block-bootstrap correction, skew/fat-tail treatment, minimum effective sample size, prior and prior-sensitivity policy when Bayesian, cost/tax/financing/capacity stress inputs, and pass/fail threshold.

`strategy_materiality_policy` defines strategy-specific materiality thresholds tied to turnover, volatility, expected edge, sample length, decision sensitivity, allocation sensitivity, instrument class, and safety-rule sensitivity.

`performance_attribution_report` defines strategy/sleeve PnL, gross return, net return after costs, financing/borrow drag, dividend/interest effects, realized/unrealized PnL, external cash flows, benchmark-relative return, and unexplained residual.

`opportunity_cost_report` defines idle capital, cash drag, missed benchmark return, blocked strategy opportunity cost, reason blocked, later realized counterfactual where available, and diagnostic recommendation.

### Expected Wealth Rule

Capital-bearing promotion or capital increase requires a lower-confidence-bound or posterior lower-bound net edge above the predeclared threshold after:

- costs
- slippage
- financing
- borrow/dividend effects where applicable
- taxes for taxable accounts
- taxes where modeled for non-taxable or tax-deferred accounts
- capacity stress
- benchmark comparison

The lower-bound method must be predeclared before OOS/live results are visible and must specify estimator family, confidence/posterior level, horizon, benchmark pairing, serial-dependence correction, skew/fat-tail handling, minimum effective sample size, and Bayesian prior/sensitivity when applicable.

For taxable capital, production or live-probe capital use requires after-tax lower-bound net edge evidence unless the mandate explicitly hard-caps the strategy below live capital use. A pre-tax-only positive edge cannot support taxable live promotion.

Failure state:

`net_edge_lower_bound_below_threshold`

`research_only` exploration does not require investment-grade expected-wealth evidence.

### Tax / Modeling Rule

Each mandate and report must declare:

- `tax_modeled`
- `tax_account_type`
- `pre_tax_or_after_tax`
- `taxable_or_tax_exempt_status`
- tax assumptions if modeled
- promotion/allocation ceiling if tax is not modeled

If taxes are not modeled, reports must explicitly declare `pre_tax`, and promotion/allocation ceilings follow the mandate's tax policy.

If capital is taxable and taxes are not modeled, the max state is `paper_trading` unless the mandate explicitly hard-caps the strategy below live capital use. Tax-exempt or tax-deferred accounts must still declare the exemption or deferral basis and any account-specific restrictions.

### Jurisdiction / Account-Use Rule

Each live-capable mandate must declare:

- jurisdiction
- account-use category
- account owner/operator role
- broker permission set
- margin permission set
- instrument eligibility
- short eligibility
- required legal/tax/compliance review refs where applicable
- fiduciary-duty status for advisory/client/fund/retirement use
- client suitability/IPS status for advisory/client/fund/retirement use
- marketing/hypothetical-performance status before any external presentation
- custody status
- record-retention status
- account-specific restrictions

Unknown jurisdiction, account-use, broker permission, margin permission, or instrument eligibility produces `jurisdiction_account_use_unknown` and blocks live trading until resolved.

Unknown advisory, client, fund, retirement, custody, fiduciary, suitability/IPS, marketing/hypothetical-performance, record-retention, or account-restriction status produces `external_capital_compliance_unknown` and disables any external-capital/advice activation until resolved.

### Survival Definition

Survival must be defined by:

- max drawdown limit
- CDaR limit and horizon
- daily loss limit
- weekly loss limit
- liquidity runway
- margin/financing stress
- ruin threshold
- forced de-risking rule

No return target can override survival rules.

### Opportunity Cost Rule

Opportunity-cost reports are diagnostic only.

They may trigger:

- research prioritization
- mandate review
- benchmark review
- capital allocation review

They may not override:

- promotion blockers
- safety controls
- evidence gaps
- stale data
- cost/capacity failures
- live-operational blockers

### Scale-Up Rules

Capital can increase only when all are true:

- minimum OOS/live evidence is met
- lower-bound net edge exceeds threshold
- attribution confidence is sufficient
- profits are not dominated by one lucky period
- drawdown and CDaR remain inside mandate
- capacity is validated at proposed scale
- costs remain inside adverse-cost assumptions
- no unresolved incidents or stale evidence
- cooldown since last allocation increase has passed

### Scale-Down / Kill Rules

Capital must reduce, pause, or halt when:

- lower-bound edge falls below threshold
- benchmark underperformance is material
- cost drag rises materially
- drawdown/CDaR breaches budget
- attribution confidence collapses
- edge decay detector fires
- capacity shrinks below allocation
- operational incident remains unresolved
- strategy churn/repeated-look rules are violated

### Enforcement

Promotion/capital allocation blocks if:

- investment mandate missing
- benchmark policy missing
- wealth thesis missing
- capital role missing
- capital allocation policy missing
- survival definition missing
- tax/modeling status missing
- jurisdiction/account-use status missing or unknown for live trading
- external-capital/advice compliance status missing where applicable
- taxable account lacks after-tax lower-bound evidence for live capital use
- instrument support package missing
- strategy-scale-aware materiality policy missing for production claims
- net edge lower bound below threshold for capital-bearing promotion
- PnL reconciliation residual too high
- opportunity-cost report used to override blockers
- scale-up cooldown violated
- strategy churn controls missing

### Acceptance Criteria

- TradingX has a signed investment mandate.
- Benchmarks are ex-ante, investable, and mandate-compatible.
- Every strategy has a capital role and falsifiable wealth thesis.
- Survival limits are formal.
- Tax/modeling status is explicit.
- Jurisdiction/account-use status is explicit before live trading.
- Taxable capital requires after-tax lower-bound evidence before live capital use.
- External-capital/advice status is explicit and blocks activation when unresolved.
- Instrument support packages exist for every promoted instrument class, including simple equities.
- Strategy-specific materiality policies exist and tighten defaults where needed.
- Scale-up/down rules are predeclared.
- Positive EV is lower-bound based, not point-estimate based.
- Opportunity cost is diagnostic only.
- Attribution reconciles to account evidence.
- Defensive strategies pass only through formal utility.
- Repeated-look and strategy-churn controls exist.

### Final Lock Statement

TradingX exists to compound capital, not merely to pass statistical gates. Milestone 0 defines the mandate, benchmarks, survival limits, wealth theses, capital roles, attribution, opportunity-cost diagnostics, tax/modeling status, and allocation rules. Later milestones must prove whether a strategy deserves capital under that mandate.

## Milestone 1: Governance Spine

### Goal

Create the first enforceable quant-governance spine: append-only decision/evidence ledger, content-addressed artifact store interface, signed approvals, strategy capability manifests, blocker evaluation, artifact classification, CLI report, activation refusal, and golden replay for unsupported or incomplete evidence.

### Core Rule

A malformed manifest or mutable promotion projection cannot suppress blockers.

`config/strategy/promotion/<strategy_id>.json` is a generated projection only. The authoritative state is derived from append-only promotion decision ledger records plus referenced evidence artifacts.

Blockers are recomputed by `src/tradingx/promotion.py` from:

- capability manifest
- append-only promotion decision ledger
- signed approval records
- promotion state projection
- promotion evidence artifacts
- runtime semantics
- replay artifacts
- emitted target weights and sides

### Primary Files

- `src/tradingx/promotion.py`
- `src/tradingx/types.py`
- `src/tradingx/activation.py`
- `src/tradingx/runtime_portfolio.py`
- `src/tradingx/portfolio/live_construction.py`
- `src/tradingx/__main__.py`
- `config/strategy/capabilities/<strategy_id>.json`
- `config/strategy/promotion/<strategy_id>.json`
- `artifacts/quant/ledger/`
- `artifacts/quant/store/`
- `schemas/quant/*.schema.json`
- `tests/fixtures/promotion/`
- `tests/unit/test_promotion.py`
- `tests/integration/test_promotion_activation.py`

### Schemas

- `schemas/quant/strategy_capability_manifest.schema.json`
- `schemas/quant/promotion_evidence.schema.json`
- `schemas/quant/promotion_decision.schema.json`
- `schemas/quant/promotion_decision_ledger_record.schema.json`
- `schemas/quant/content_addressed_artifact.schema.json`
- `schemas/quant/approval_record.schema.json`
- `schemas/quant/operator_identity.schema.json`
- `schemas/quant/ledger_key_management_policy.schema.json`
- `schemas/quant/state_action_contract.schema.json`

`strategy_capability_manifest` declares capabilities, assumptions, limits, and promotion ceiling. It does not contain `blocking_reasons`.

`state_action_contract` records state, data/broker access, order permissions, capital ceiling, short permissions, required runtime controls, route constraints, and disallowed actions. Runtime code may hard-code a safer subset, but no module may permit behavior outside the canonical state-action contract.

`promotion_evidence` governs evidence refs, replay refs, evidence class, schema versions, tax/financing/capacity statuses, and artifact freshness.

`promotion_decision` governs strategy id, current state projection, promotion ceiling, max allowed state, blockers, evidence classification, decision timestamp, and source artifacts.

Promotion decision ledger record governs:

- `ledger_record_id`
- `record_sequence`
- `previous_record_hash`
- `decision_payload_hash`
- `strategy_id`
- `decision_id`
- `approval_record_refs`
- `evidence_artifact_refs`
- `projection_target_ref`
- `created_at_utc`
- `created_by_identity_ref`
- `signature_ref`

Approval records bind reviewer intent to verifiable identity:

- operator identity ID
- role registry version
- authority boundary ref
- approval scope
- risk accepted
- expiry
- canonical payload hash
- signature

`ledger_key_management_policy` records signing-key custody, rotation, revocation, role registry version, recovery quorum, immutable/WORM backup location, restore-test cadence, and last restore-test evidence.

Current promotion state projection:

```text
config/strategy/promotion/<strategy_id>.json
```

It stores derived fields for operator readability:

- `strategy_id`
- `current_state`
- `last_decision_id`
- `last_reviewed_at_utc`
- `reviewed_by`
- `evidence_refs`
- `schema_version`

Milestone 10 later adds production expiry and recertification metadata to the same projection. Activation must verify that this projection matches the append-only ledger and must ignore or block on projection drift.

### Enforcement

- Activation gateway refuses any strategy/blueprint whose evidence state is below required promotion level.
- CLI promotion reports surface exact blockers.
- Local projection edits cannot create promotion state.
- Missing or invalid approval signatures block promotion.
- Ledger sequence gaps, hash mismatches, or projection drift block activation.
- Runtime planner refuses unsupported emitted sides.
- Negative weights require explicit short support or a manifest-declared long-only transform.
- State action contracts are enforced before activation, runtime planning, and order route selection.
- `mean-reversion-v1` is capped at `research_only` until short-side support exists or the strategy is redesigned long-only.

### Migration

Existing evidence is classified as:

- `valid`: schema-complete, replayable, semantically supported
- `legacy`: old artifact missing V5 fields or schema-major mismatch
- `stale`: evidence exists but fails freshness or replay requirements
- `invalid`: contradicts manifest or runtime semantics

No legacy artifact may support production.

### CLI

```bash
uv run tradingx promotion-check --strategy-id trend-following-v1
```

Output includes strategy id, evidence class, promotion ceiling, max allowed state, blockers, manifest path, evidence refs, replay reference, and schema version.

### Acceptance Criteria

- `promotion-check --strategy-id trend-following-v1` produces a reproducible `research_only` decision with exact mandate/utility blockers until signed Milestone 0 placeholder mandate artifacts exist.
- A second fixture that includes signed placeholder mandate, benchmark, wealth-thesis, utility, allocation, tax/account, jurisdiction/account-use, and instrument-package artifacts can become `paper_shadow`-eligible from artifacts alone.
- The same decision can be reproduced from the ledger and content-addressed artifacts without trusting mutable config projection files.
- Editing `config/strategy/promotion/<strategy_id>.json` by hand produces projection drift and cannot activate a higher state.
- Missing/invalid approval identity or signature blocks promotion.
- Missing key-management or immutable-backup policy produces `ledger_key_worm_controls_missing`.
- A state/action mismatch produces `state_action_contract_missing` and blocks activation.
- `mean-reversion-v1` is capped at `research_only` with `unsupported_side` or `short_support_missing`.
- An old evidence pack without V5 fields is classified `legacy`.
- Activation refuses a blocked strategy and prints exact blockers.
- A negative-weight replay cannot be silently clipped and treated as promotable.

## Milestone 2: Experiment Registration & Trial Universe

### Goal

Make data mining visible by requiring promotion-valid evidence to come from an append-only registered experiment/run ledger scoped to the promotion decision.

### Core Rule

Promotion-valid DSR/PBO/MCS evidence must use the registered experiment universe only. Legacy family-wide trials and unregistered experiments are excluded.

### Primary Files

- `src/tradingx/experiments.py`
- `src/tradingx/trials.py`
- `src/tradingx/evaluation.py`
- `src/tradingx/validation.py`
- `src/tradingx/__main__.py`
- `schemas/quant/experiment_registration.schema.json`
- `schemas/quant/experiment_run_record.schema.json`
- `schemas/quant/experiment_amendment_record.schema.json`
- `schemas/quant/trial_universe_manifest.schema.json`
- `tests/fixtures/experiments/`

### Schemas

`experiment_registration` includes:

- `experiment_id`
- `research_program_id`
- `selection_family_id`
- `promotion_decision_scope`
- `study_id`
- `parent_experiment_id`
- `strategy_id`
- `strategy_config_hash`
- `study_definition_hash`
- `feature_set_hash`
- `label_definition_hash`
- `benchmark_family_hash`
- `cost_model_hash`
- `dataset_fingerprint`
- `objective`
- `loss_function`
- `registered_at_utc`
- `registered_by`
- `pre_result_registration_status`
- `metric_visibility_policy`
- `outside_exploration_attestation_ref`
- `code_git_sha`
- `script_or_notebook_hash`
- `immutable_source_artifact_ref`
- `metric_vault_policy_ref`
- `metric_release_token_ref`
- `output_capture_artifact_ref`
- `registration_sequence`
- `selection_influence`

`experiment_run_record` records every run lifecycle:

- `started`
- `completed`
- `failed`
- `canceled`

Failed and canceled runs remain in the universe.

Each run record also records:

- `metrics_visible_at_utc`
- `metrics_visibility_status`
- `metric_vault_release_status`
- `immutable_stdout_stderr_hash`
- `notebook_output_hash`
- `result_artifact_hash`
- `termination_reason_code`
- `termination_stage`
- `partial_metric_payload_hash`
- `conservative_imputation_policy`
- `cancellation_sensitivity_status`

`experiment_amendment_record` is append-only and records corrections or influence changes. Changing `selection_influence=false` to `true` marks the universe `selection_audit_required`.

`trial_universe_manifest` is scoped by `promotion_decision_scope`, not just `study_id`.

### Universe Definition

`U` is built from all registered experiments and child run records in the same `promotion_decision_scope`, including related `study_id`s when they influenced the same strategy selection.

Changing objective, loss, label, feature set, benchmark family, dataset, or cost model creates a new `study_id`, but does not remove the experiment from the promotion-decision universe if it influenced the same promotion.

### Integrity Rules

- Records are never edited in place.
- Experiment registration and run start records must be committed before metrics are computed or displayed.
- Backtest, validation, and notebook wrappers must obtain a registered run token before computing metrics and a metric-vault release token before displaying, exporting, logging, or persisting metric outputs.
- Notebook/script source, stdout/stderr, rendered notebook outputs, result artifacts, and error artifacts are captured immutably before metric release.
- A run whose metrics were visible before registration is `post_result_registered`, maps to `trial_lineage_contaminated`, and cannot support promotion above `research_only`.
- A run whose prior metric exposure cannot be ruled out is `trial_lineage_contaminated` and cannot support promotion above `research_only`.
- `registration_sequence` is monotonic per `promotion_decision_scope`.
- Duplicate sequence -> `ledger_integrity_violation`
- Sequence gap -> `trial_universe_incomplete`
- Same ID with different payload -> `ledger_integrity_violation`
- Missing metric-vault token -> `trial_lineage_contaminated`
- Missing immutable notebook/script/output capture -> `trial_lineage_contaminated`
- Contradictory selection influence or unexplained influence downgrade -> `trial_lineage_contaminated`
- Registered experiment without run record -> `trial_universe_incomplete`
- Cited unregistered metric-bearing artifact -> `trial_lineage_contaminated`
- Cited unregistered non-metric artifact -> `selection_audit_required` only if prior metric exposure is ruled out by immutable artifacts
- Missing outside-exploration attestation -> `trial_lineage_contaminated`
- Repeated unexplained out-of-band exploration -> `trial_lineage_contaminated`

All hashes use canonical JSON with sorted keys, normalized decimal strings, UTC ISO timestamps, stable enum casing, explicit schema version, and no insignificant whitespace.

### DSR Universe Statistics

`trial_statistics_for_universe(...)` reports:

- `registered_trial_count`
- `metric_bearing_trial_count`
- `effective_independent_trial_count`
- `trial_correlation_estimate`
- `selection_rule`
- `selected_strategy_rank`
- `trial_sharpe_mean`
- `trial_sharpe_variance`
- `trial_return_skewness`
- `trial_return_kurtosis`
- `failed_or_canceled_count`
- `failed_run_treatment`
- `failed_run_effective_trial_penalty`
- `full_cpcv_pbo_matrix_ref`
- `selection_audit_required`

DSR variance uses metric-bearing completed runs. Effective trial count, selected-strategy rank penalty, and audit metadata include all selection-influencing registered attempts, including failed, canceled, and no-metric attempts unless immutable artifacts prove the attempt failed before metric visibility and was non-result-contingent.

Failed and canceled runs require reason codes, cancellation sensitivity, and an effective-trial penalty. Promotion-valid DSR must report whether conservative imputation or rank/trial-count penalization of failed/canceled/no-metric attempts would change the hard-pass conclusion. If the conclusion flips, failure timing is unproven, or reason codes indicate result-contingent cancellation, DSR status becomes `pending_selection_bias` and cannot support promotion above `paper_shadow`.

### Enforcement

- Promotion engine blocks states above `paper_shadow` if trial universe is incomplete.
- Promotion engine blocks states above `paper_shadow` if `selection_audit_required` remains after immutable artifacts rule out prior metric exposure.
- Promotion engine blocks states above `research_only` if any supporting run is post-result registered.
- Promotion engine blocks states above `research_only` if unregistered metric-bearing artifacts, missing outside-exploration attestation, repeated unexplained out-of-band exploration, or any other contaminated lineage is present.
- Promotion engine blocks states above `research_only` if metric-vault enforcement, immutable output capture, or uncontaminated lineage cannot be proven.
- Gate reports intended for promotion require registered experiment context.
- DSR/PBO/MCS readiness fails closed unless the universe is complete and registered.
- Gate reports without `--experiment-id` embed `promotion_valid=false` and `evidence_class=exploratory`.

### CLI

```bash
uv run tradingx register-experiment ...
uv run tradingx start-experiment-run --experiment-id ...
uv run tradingx complete-experiment-run --run-id ...
uv run tradingx trial-universe --promotion-decision-scope ...
uv run tradingx gate-report --experiment-id ...
```

### Migration

Existing `TrialsLedger` rows are classified `legacy_unregistered`, excluded from DSR/PBO/MCS, and allowed only as exploratory historical context.

### Acceptance Criteria

- DSR uses only complete registered trial-universe records, never broad family-wide legacy trials.
- Child parameter and cost perturbation runs are visible in `U`.
- Splitting studies by changing loss/objective/feature set does not evade promotion-decision universe accounting.
- Registered-but-omitted failed experiments make `trial_universe_incomplete`.
- Unregistered metric-bearing notebooks trigger `trial_lineage_contaminated`; unregistered non-metric artifacts trigger `selection_audit_required` only when immutable artifacts rule out prior metric exposure.
- Metric-vault release is required before metrics can be displayed, exported, logged, or persisted.
- Immutable notebook/script/output capture is required for promotion-valid evidence.
- Contaminated lineage caps evidence at `research_only`.
- Out-of-band exploratory work must be attested; missing or contradictory attestation triggers `trial_lineage_contaminated`.
- Post-result registered runs cannot support promotion.
- Failed/canceled runs require reason codes and DSR cancellation sensitivity.
- DSR/PBO inputs include effective independent trial count, trial correlation, selection rule, selected-strategy rank, non-normality inputs, failed-run treatment, and full CPCV/PBO matrix.
- Failed/canceled/no-metric attempts affect effective trial count and rank penalty unless artifacts prove pre-metric, non-result-contingent failure.
- Legacy trials are excluded from DSR/PBO/MCS.
- Trial universe is reproducible from artifacts alone.

## Milestone 3: Data Restatement & Fingerprinting

### Goal

Make promotion-valid evidence dependent on reproducible data provenance, restatement detection, and replay-based invalidation.

### Core Rule

Promotion-valid evidence must be tied to:

- raw vendor payload hashes
- raw vendor payload artifact refs
- normalized research-frame hashes
- normalized research-frame artifact refs
- normalization code/policy hashes
- universe membership hash
- calendar/timezone/session policy
- benchmark/cash curve versions
- point-in-time universe membership
- point-in-time symbol/security identifier mapping
- delisting return policy and retained delisting inputs
- bitemporal vendor observation and availability timestamps
- dependency references from dataset to evidence

Data-level change makes evidence `stale/replay_required`. Replay-proven claim change makes evidence `invalid` for the old claim.

A hash without retained inputs is not replay-valid. Promotion-valid datasets require immutable content-addressed storage of raw payloads when available, normalized frames, normalization code reference, normalization policy, benchmark/cash inputs, and universe membership inputs.

### Primary Files

- `src/tradingx/data_fingerprint.py`
- `src/tradingx/data.py`
- `src/tradingx/historical.py`
- `src/tradingx/benchmark_stack.py`
- `src/tradingx/risk_free.py`
- `src/tradingx/validation.py`
- `src/tradingx/promotion.py`
- `src/tradingx/experiments.py`
- `src/tradingx/__main__.py`
- `schemas/quant/dataset_manifest.schema.json`
- `schemas/quant/data_restatement_report.schema.json`
- `schemas/quant/evidence_invalidation_report.schema.json`
- `schemas/quant/evidence_dependency_index.schema.json`
- `tests/fixtures/data_fingerprints/`

### Schemas

`dataset_manifest` records vendor, pull time, symbols, window, bar frequency, adjustment policy, total-return policy, corporate-action policy, benchmark/cash curve versions, timezone, calendar, session policy, timestamp alignment, missing/stale policies, point-in-time universe membership, point-in-time symbol/security identifier mapping, inception/delisting policy, delisting return inputs, survivorship policy, bitemporal vendor observation/availability timestamps, raw payload hashes, normalized frame hashes, normalization code hash, normalization policy hash, corporate action hash, benchmark hash, and cash curve hash.

`data_restatement_report` records old/new dataset IDs, changed symbols/bars/corporate actions/benchmark/cash values, data-level materiality flags, evidence-level materiality flags, return deltas, raw payload availability, manual review requirement, and summary metrics.

`evidence_dependency_index` maps:

- `dataset_id -> evidence_pack_id`
- `dataset_id -> experiment_id`
- `dataset_id -> gate_report_id`
- `dataset_id -> promotion_decision_id`

`evidence_invalidation_report` records affected evidence refs, old/new dataset IDs, invalidation reason, materiality flags, required action, and timestamp.

### Materiality Split

Data-level materiality:

- split/dividend/corporate-action change
- adjustment policy mismatch
- total-return policy mismatch
- corporate-action policy mismatch
- universe membership change
- missing or changed point-in-time universe membership
- missing or changed symbol/security identifier mapping
- missing or changed delisting return input
- missing or changed vendor availability timestamp
- calendar/timezone/session mismatch
- daily return delta `>= 5 bps`
- cumulative benchmark return delta `>= 25 bps`
- cumulative non-material drift crossing threshold
- cash curve change crossing threshold

Evidence-level materiality after replay:

- candidate CAGR changes by `>= 25 bps/year`
- Sharpe changes by `>= 0.05`
- MDD/CDaR changes by `>= 25 bps`
- any gate outcome changes
- any trade decision would have changed
- any production safety rule would have changed

### Enforcement

- Promotion blocks above `paper_shadow` on missing/stale/materially restated datasets.
- Promotion blocks above `research_only` for data-dependent claims when point-in-time universe membership, symbol mapping, delisting returns, bitemporal vendor timestamps, or replayable raw/normalized inputs are missing.
- Gate reports intended for promotion require dataset manifest.
- DSR/PBO/MCS readiness requires dataset fingerprints through Milestone 2 experiment records.
- Adjustment policy mismatch blocks promotion.
- Universe membership changes cannot masquerade as the same dataset.

### CLI

```bash
uv run tradingx dataset-manifest --symbols SPY,QQQ --window-start ... --window-end ...
uv run tradingx compare-dataset --old <dataset-id-or-path> --new <dataset-id-or-path>
uv run tradingx invalidate-evidence --restatement-report <path>
```

### Migration

Existing evidence without a dataset manifest becomes `legacy`.

Existing evidence with a manifest becomes:

- `valid` if no materiality fires
- `stale` if data-level materiality fires and replay is required
- `invalid` if replay proves old metric/gate/trade/safety claim changed
- `manual_review_required` if old raw payload is unavailable and normalized data changed

`manual_review_required` cannot support promotion above `paper_shadow`. If raw or normalized replay inputs are missing and the dataset cannot be reconstructed from immutable artifacts, the evidence is `replay_input_missing` and capped at `research_only` for claims that depend on that dataset.

### Acceptance Criteria

- Promotion-valid evidence references dataset manifests.
- Promotion-valid data-dependent evidence includes point-in-time universe membership.
- Promotion-valid data-dependent evidence includes point-in-time symbol/security identifier mapping.
- Promotion-valid data-dependent evidence includes delisting returns or explicit delisting-return unavailability treatment.
- Promotion-valid data-dependent evidence includes bitemporal vendor observation and availability timestamps.
- Raw/normalized/code/policy hashes are recorded.
- Cumulative small changes can trigger material restatement.
- Unavailable old raw data plus normalized change requires manual review.
- Missing raw/normalized replay inputs cap evidence and cannot satisfy artifact-only replay.
- Dependency index lists affected evidence from `dataset_id`.
- Data-level change makes evidence stale/replay-required.
- Replay-proven claim change makes old evidence invalid.
- Golden replay can reproduce or invalidate old evidence from artifacts alone.

## Milestone 4: Validation Evidence Engine

### Goal

Ensure statistical evidence supports the exact economic promotion claim, not just impressive standalone metrics.

### Core Rule

Statistical evidence can block promotion, but it can support promotion only when the economic claim is:

- powered
- paired against declared baselines
- threshold-justified
- cost-stressed
- universe-aware
- stable across inference settings
- derived from promotion-valid evidence

DSR/PBO/MCS can block promotion. They cannot, by themselves, prove economic edge.

### Primary Files

- `src/tradingx/stats.py`
- `src/tradingx/evaluation.py`
- `src/tradingx/validation.py`
- `src/tradingx/experiments.py`
- `src/tradingx/promotion.py`
- `src/tradingx/pbo.py`
- `src/tradingx/validation_folds.py`
- `src/tradingx/trials.py`
- `src/tradingx/__main__.py`
- `schemas/quant/power_analysis_report.schema.json`
- `schemas/quant/bootstrap_report.schema.json`
- `schemas/quant/paired_benchmark_uncertainty_report.schema.json`
- `schemas/quant/statistical_validation_report.schema.json`
- `schemas/quant/threshold_justification.schema.json`
- `tests/fixtures/validation_evidence/`

### Schemas

`power_analysis_report` includes Gaussian/HAC power, empirical block-bootstrap power when sample permits, `n_eff <= n`, HAC standard error, lag sensitivity, and `pending_power_conflict` if Gaussian/empirical power materially disagree.

`bootstrap_report` uses stationary block bootstrap, default `n_resamples >= 5000`, default block length `ceil(sqrt(n_eff_pre))`, sensitivity grid, fixed seed, tail metric stability check, and pending statuses for short samples or instability.

`paired_benchmark_uncertainty_report` covers cash, 60/40, static sleeve baseline, and no-trade/current holdings where applicable. It reports paired excess return CI, paired excess utility CI, paired cost-stressed CI, material edge threshold, and pass/pending/fail per baseline.

`statistical_validation_report` records dataset, experiment, promotion scope, trial universe hash, power/bootstrap/paired benchmark refs, return edge, risk constraints, cost stress, portfolio contribution, multiple-testing status, effective independent trial count, trial correlation estimate, selection rule, selected-strategy rank, non-normality inputs, failed-run treatment, failed-run effective-trial penalty, full CPCV/PBO matrix ref, DSR/PBO/MCS/SPA statuses, economic edge CI, registered/metric-bearing/failed counts, exploratory/contaminated lineage, promotion validity, and blockers.

`threshold_justification` records threshold value, economic rationale, statistical rationale, strategy type, approval metadata, and version.

### Status Rules

- Missing threshold justification -> `pending_threshold`; no hard pass allowed.
- Underpowered or unstable evidence -> max state `paper_shadow`.
- Evidence derived from exploratory gate report remains non-promotable downstream.
- DSR uses only Milestone 2 registered universe stats.
- DSR requires effective independent trial count, trial correlation estimate, selected-strategy rank, selection rule, sample length, skewness, kurtosis, failed-run treatment, and failed-run effective-trial penalty.
- PBO requires a complete promotion-decision CPCV matrix and cannot rely on summarized fold winners alone.
- MCS/SPA requires predeclared loss and hypothesis family.

### Enforcement

Promotion follows `Non-Discretionary Production Blockers` first. For Milestone 4 statistical evidence, promotion blocks above `paper_shadow` if any are true:

- missing threshold justification
- underpowered evidence
- unstable lag/bootstrap inference
- incomplete trial universe
- exploratory source evidence
- missing paired benchmark uncertainty
- DSR/PBO/MCS not universe-backed
- DSR/PBO inputs incomplete
- failed/canceled/no-metric attempts lack effective-trial penalty
- missing dataset manifest

Promotion blocks above `research_only` if the replay path is missing.

### CLI

```bash
uv run tradingx power-report --experiment-id ...
uv run tradingx bootstrap-report --experiment-id ...
uv run tradingx paired-benchmark-report --experiment-id ...
uv run tradingx statistical-validation-report --experiment-id ...
```

### Migration

Old evidence packs without power, bootstrap, paired benchmark uncertainty, and universe-aware DSR become `legacy_statistical_evidence`. They cannot support promotion above `paper_shadow`.

### Acceptance Criteria

- Every promotion-valid statistical report has power, bootstrap, paired benchmark, dataset, experiment, threshold, and trial-universe references.
- Missing thresholds produce `pending_threshold`.
- Underpowered/unstable evidence caps at `paper_shadow`.
- Paired benchmark uncertainty is required for economic edge claims.
- Exploratory evidence remains non-promotable downstream.
- DSR uses registered universe stats only.
- DSR evidence includes effective independent trial count, trial correlation, selection rule, selected-strategy rank, non-normality inputs, failed-run treatment, and failed-run effective-trial penalty.
- PBO evidence includes the full CPCV/PBO matrix.
- PBO/MCS/SPA fail closed on incomplete universe or missing loss/null definition.
- Old metric-only evidence is legacy.

## Milestone 5: Cost, Quote Quality & Capacity Instrumentation

### Goal

Make economic edge depend on replayable cost evidence, quote-quality state, conservative sparse-bucket handling, and turnover-adjusted capacity at intended scale.

### Core Rule

Promotion-valid cost evidence must:

- use a predeclared arrival timestamp policy
- include clean and all-events estimates
- fall back conservatively for sparse buckets
- model runtime no-trade quote states
- model order type, venue/broker semantics, partial fills, non-fills, halts, open/close auctions, rate limits, queue/adverse-selection effects, and non-fill opportunity cost
- separate paper from live/probe/live evidence
- define powered bucket-level sample requirements for intended order type, venue, liquidity, spread, volatility, session, and participation buckets
- prove lower-bound capacity at intended turnover-adjusted capital scale

Paper fills validate lifecycle/reconciliation. They do not prove real market impact.

### Primary Files

- `src/tradingx/costs.py`
- `src/tradingx/replay_slippage.py`
- `src/tradingx/execution.py`
- `src/tradingx/backtest.py`
- `src/tradingx/validation.py`
- `src/tradingx/promotion.py`
- `src/tradingx/data.py`
- `src/tradingx/experiments.py`
- `src/tradingx/types.py`
- `src/tradingx/__main__.py`
- `schemas/quant/quote_quality_record.schema.json`
- `schemas/quant/execution_cost_observation.schema.json`
- `schemas/quant/cost_model_report.schema.json`
- `schemas/quant/capacity_curve_report.schema.json`
- `tests/fixtures/cost_capacity/`

### Milestone 2 Amendment

Add `arrival_timestamp_policy` to `experiment_registration`. Changing it creates a new `study_id`. If selection-influencing, it remains in the same promotion-decision universe.

### Schemas

`quote_quality_record` records quote timestamps, system receive time, source, bid/ask/mid, spread, locked/crossed/stale flags, quote age, latency, handling policy, outage-adjacent window, trading session, vendor, and quality status.

`execution_cost_observation` records intent/order/execution IDs, symbol, side, order type, time-in-force, venue/broker route, decision/submit/ack timestamps, arrival timestamp policy, arrival mid, fill price, partial-fill quantity, unfilled quantity, non-fill reason, signed slippage, half-spread, queue/adverse-selection marker, halt/open/close state, rate-limit state, quantity, notional, interval volume, participation rate, volatility/spread/time buckets, quote quality ref, paper/live status, and whether an impact claim is allowed.

`cost_model_report` records model version, cost feature hash, bucket assignment policy, training dataset, sample window, bucket definitions, minimum bucket sample size, bucket-level power target, bucket-level confidence, powered bucket coverage, sparse-bucket fallback policy, clean estimate, all-events stress, adverse percentiles, sample sizes, unsupported buckets, non-fill opportunity-cost estimate, queue/adverse-selection estimate, counterfactual quality, paper/live-probe/live counts, minimum live sample requirements, calibration source, impact claim status, and blockers.

`capacity_curve_report` records target capital scale, tested scales, validated range, max participation, expected turnover, orders per day, rebalance frequency, annualized cost drag by scale, capacity under turnover assumption, lower-confidence/posterior-bound capacity curve, expected cost curve, net edge curve, lower-bound net edge by scale, lower-bound capacity limit, extrapolation risk, and blockers.

### Cost Rules

Clean quote estimate can support promotion only if runtime has enforced no-trade rules for stale/crossed/locked/bad-quality quote states. Otherwise promotion uses `all_events_cost_stress`.

If an intended bucket lacks samples, use the worst defensible fallback among parent bucket, liquidity-class bucket, or global adverse p90. If no defensible fallback exists: `unsupported_cost_bucket`.

If powered bucket-level sample requirements are missing or unmet for the intended execution path, promotion uses `execution_sample_power_missing` and cannot claim live impact or production capacity.

If runtime refuses bad quote states and quote-state data exists, backtest replay must model skipped trades under those states.

### Enforcement

Promotion blocks above `paper_shadow` if:

- no quote-quality evidence
- no clean/all-events reports
- sparse bucket has no conservative fallback
- intended bucket unsupported
- execution semantics incomplete
- execution sample power missing
- intended capital scale outside validated range
- lower-bound capacity curve missing
- capacity extrapolation risk is true
- impact claim based only on paper fills
- minimum live/probe sample requirement unmet for live impact or production capacity claims
- clean estimate used without runtime no-trade rules
- cost counterfactual quality is low

Production blocks if target scale is outside validated range or `capacity_extrapolation_risk=true`.

### CLI

```bash
uv run tradingx quote-quality-report --artifact-root ...
uv run tradingx cost-model-report --sample-window ...
uv run tradingx capacity-curve --strategy-id ... --capital-scales ...
uv run tradingx replay-slippage-report --include-quote-quality
```

### Migration

Existing cost evidence becomes `legacy_cost_evidence` if missing quote-quality or arrival policy. Paper-only evidence supports lifecycle only, not market impact. Placeholder coefficients remain research-only unless tied to a cost-model report.

### Acceptance Criteria

- Every promotion-valid economic report references a cost-model report.
- Arrival policy is predeclared in experiment registration.
- Clean and all-events cost reports are both produced.
- Quote-quality state is recorded for cost observations.
- Paper/live-probe/live samples are split.
- Order type, venue/broker semantics, partial fills, non-fills, queue/adverse selection, halts, open/close behavior, and rate limits are modeled.
- Non-fill opportunity cost is reported.
- Paper fills cannot support market-impact claims.
- Minimum live/probe sample requirements are predeclared before live impact or production capacity claims.
- Powered bucket-level execution sample requirements are predeclared and checked.
- Sparse buckets use conservative fallback or block.
- Bad quote clean-cost promotion requires runtime no-trade rule.
- Backtest replay models no-trade quote states when data exists.
- Capacity includes turnover/order-frequency assumptions and lower-bound capacity curves.
- Capacity extrapolation and target scale outside validated range block production.

## Milestone 6: Portfolio Utility & Optimizer Gates

### Goal

Prevent optimization from becoming a new overfitting engine by requiring governed utility, explicit tail risk, declared baselines, paired OOS evidence, perturbation stability, turnover control, covariance recertification, and auditable fallback.

### Core Rule

An optimizer can support promotion only if:

- utility weights were predeclared and justified
- utility lambdas, baselines, candidate set, constraints, and optimizer settings were frozen before OOS evaluation
- tail risk is explicit
- all applicable baselines are tested or approved for exclusion
- expected-return inputs are promotion-valid or uncertainty-penalized
- covariance regime drift is monitored
- turnover is capped
- cost/capacity evidence is incorporated
- fallback is deterministic and auditable

### Primary Files

- `src/tradingx/portfolio/construction.py`
- `src/tradingx/portfolio/live_construction.py`
- `src/tradingx/portfolio/blueprint.py`
- `src/tradingx/portfolio/optimizer.py`
- `src/tradingx/validation.py`
- `src/tradingx/evaluation.py`
- `src/tradingx/promotion.py`
- `src/tradingx/stats.py`
- `src/tradingx/types.py`
- `src/tradingx/__main__.py`
- `schemas/quant/portfolio_utility_definition.schema.json`
- `schemas/quant/optimizer_input.schema.json`
- `schemas/quant/optimizer_decision.schema.json`
- `schemas/quant/optimizer_validation_report.schema.json`
- `schemas/quant/optimizer_recertification_report.schema.json`
- `schemas/quant/optimizer_fallback_record.schema.json`
- `tests/fixtures/portfolio_optimizer/`

### Schemas

`portfolio_utility_definition` records utility ID, lambda values, lambda justification refs, pre-experiment approval, freeze timestamp, change policy, return/risk/drawdown/tail/cost/capacity/liquidity/constraint components, objective hierarchy, threshold justification, approver, and timestamp.

Tail risk must include at least one of:

- CVaR / expected shortfall
- downside semivariance
- left-tail penalty
- predeclared tail-event stress scenarios

`optimizer_input` records candidate sleeves, expected return estimates and uncertainty, expected return promotion status, penalty policy, covariance estimator, shrinkage method, lookback, effective sample size, condition number, PSD repair policy, cost model, capacity curves, constraints, current positions, baselines, freeze/lockbox refs, and input hash.

`optimizer_decision` records target weights, expected utility/cost/turnover/risk, tail risk estimate, marginal risk contributions, shadow prices, fallback status/reason, and decision hash.

`optimizer_validation_report` records baselines, excluded baselines and approvals, nested validation or final lockbox status, paired OOS utility, cost/capacity/tail/covariance/return/constraint stress, turnover, adjacent decision turnover, smoothing policy, weight and risk-contribution stability, no-alpha full pipeline results, covariance drift, recertification triggers, optimizer status, and blockers.

`optimizer_recertification_report` and `optimizer_fallback_record` make recertification and fallback auditable.

### Required Baselines

- no-trade/current holdings
- static sleeve budget
- equal weight
- inverse volatility
- equal risk contribution
- current non-optimized TradingX allocation

Applicable baseline exclusion blocks unless approved in an artifact.

### Validation Requirements

- Paired OOS utility on the same windows with lower 95% paired CI above threshold.
- Utility lambdas, baselines, candidate set, feature set, constraints, and optimizer settings are frozen before the OOS window or evaluated through nested validation with a final lockbox.
- No-alpha simulation reruns the full optimizer/baseline comparison pipeline under null/permuted returns.
- Perturb covariance, expected return, cost, capacity, constraints, and tail stress.
- Constraint shadow-price instability includes sign flip, order-of-magnitude change, binding set changes, or utility rank flips.
- Adjacent optimizer decisions must obey `max_adjacent_decision_turnover`.

### Enforcement

Promotion blocks optimizer use above `paper_shadow` if:

- lambdas lack prior justification
- optimizer or sizing lockbox is missing
- tail-risk term/stress missing
- applicable baseline excluded without approval
- paired OOS utility fails
- perturbation stability fails
- covariance drift unresolved
- turnover cap exceeded
- expected returns not promotion-valid or penalized
- cost/capacity stress fails
- no-alpha full pipeline fails
- fallback artifact missing when fallback occurs

Runtime must not use stale/invalid optimizer validation. It must emit a fallback record and use static blueprint allocation.

### CLI

```bash
uv run tradingx optimizer-validate --blueprint <path> --experiment-id ...
uv run tradingx optimizer-decision --blueprint <path> --portfolio-state <path>
uv run tradingx optimizer-recertify --optimizer-id ...
uv run tradingx portfolio-baselines --blueprint <path>
```

### Migration

Existing static allocations remain valid baselines. Optimizer evidence without utility governance, baselines, paired OOS validation, perturbation tests, tail stress, or cost/capacity refs becomes `legacy_optimizer_evidence`.

### Acceptance Criteria

- Utility function and lambdas are predeclared, justified, and versioned.
- Utility lambdas, baselines, candidate set, constraints, and optimizer settings are frozen before OOS evaluation or covered by nested validation/final lockbox.
- Tail risk is explicit and stress-tested.
- All applicable baselines are tested or approved for exclusion.
- Optimizer beats baselines on paired OOS utility after costs.
- Covariance/return/cost/capacity/constraint/tail perturbation tests exist.
- No-alpha full pipeline simulation prevents manufactured edge.
- Optimizer evidence references cost/capacity reports.
- Expected returns are promotion-valid or uncertainty-penalized.
- Adjacent turnover is capped.
- Optimizer recertification triggers exist.
- Invalid/stale optimizer evidence blocks runtime optimizer use.
- Fallback to static allocation is deterministic and auditable.

## Milestone 7: Expected Return & Sizing Governance

### Goal

Prevent expected-return models and sizing rules from becoming polished heuristics by requiring registered forecast identity, auditable feature/label timing, calibrated uncertainty, OOS utility improvement, and hard exposure/capacity/drawdown caps.

### Core Rule

Expected returns may affect weights only when:

- forecast identity is registered
- feature set, label definition, sizing caps, and selection rules were frozen before OOS evaluation or covered by nested validation/final lockbox
- feature and label timing is auditable
- uncertainty is calibrated
- OOS utility improves after costs against no-forecast baselines
- sizing is bounded by hard exposure, drawdown, cost, liquidity, and capacity caps

### Primary Files

- `src/tradingx/signals/`
- `src/tradingx/sizing.py`
- `src/tradingx/strategy.py`
- `src/tradingx/evaluation.py`
- `src/tradingx/validation.py`
- `src/tradingx/portfolio/optimizer.py`
- `src/tradingx/promotion.py`
- `src/tradingx/experiments.py`
- `src/tradingx/types.py`
- `src/tradingx/__main__.py`
- `schemas/quant/forecast_model_manifest.schema.json`
- `schemas/quant/feature_manifest.schema.json`
- `schemas/quant/label_definition.schema.json`
- `schemas/quant/expected_return_report.schema.json`
- `schemas/quant/sizing_policy.schema.json`
- `schemas/quant/sizing_decision.schema.json`
- `tests/fixtures/forecast_sizing/`

### Milestone 2 Amendment

Add to `experiment_registration`:

- `forecast_model_hash`
- `feature_manifest_hash`
- `label_definition_hash`
- `sizing_policy_hash`

Changing horizon, label, feature set, model identity, or sizing policy creates a new `study_id`. If selection-influencing, it remains in the same promotion-decision scope.

### Schemas

`forecast_model_manifest` records model identity, hashes, change policy, horizon, target variable, label/feature manifests, training dataset, model class/parameters, prior/shrinkage, uncertainty estimator/version, retraining cadence, regime conditioning, economic rationale, monotonicity constraints, promotion status, and approval timestamp.

`feature_manifest` records feature definitions, source refs, availability timestamp policy, timestamp source, source data arrival timestamp, computation timestamp, decision timestamp, lockbox/freeze ref, lookback windows, lag policy, missing value policy, normalization, hash, leakage audit, and leakage checks.

`label_definition` records target, horizon, return basis, benchmark ref, cost adjustment, overlap policy, purge window, embargo window, overlap status, timestamp alignment, and hash.

`expected_return_report` records `mu_hat`, `sigma_mu`, uncertainty-penalized mu, uncertainty calibration, prediction interval coverage, calibration window/status, forecast decay, OOS utility, no-forecast baseline, simple heuristic baselines, feature ablation, regime split, promotion validity, and blockers.

`sizing_policy` records sizing method, target vol, position/sleeve/gross/net/leverage/order/participation caps, drawdown budget, cost/capacity refs, lockbox/freeze ref, Kelly disablement/gate/variance/tail/estimation-error haircuts, max Kelly multiplier, cap rules, and approval timestamp.

`sizing_decision` records forecast ref, sizing policy, raw signal, mu/sigma/penalized mu, vol, cost/capacity/drawdown adjustment, final target weight, cap bindings, and decision hash.

### Expected Return Rules

Forecasts must beat no-forecast and simple heuristic baselines on OOS utility after costs/capacity. Prediction fit alone cannot support promotion.

If uncertainty is present but uncalibrated:

- blocker: `expected_return_uncertainty_uncalibrated`
- max state: `paper_shadow`

Features must be available before decision time with auditable timestamp source. Label overlap must feed purge/embargo behavior in CV/CPCV.

Feature sets, labels, sizing caps, and selection rules must be frozen before OOS evaluation. If any were adapted after OOS metrics were visible, the evidence is `optimizer_or_sizing_lockbox_missing` unless nested validation or a final lockbox isolates the final evaluation.

### Sizing Rules

Existing heuristic signals remain allowed as inputs, but they are not expected-return forecasts. Production requires governed sizing policy and utility evidence.

Kelly is disabled by default. It requires a complete Kelly gate, and full Kelly is never allowed.

Sizing property rules:

- higher cost cannot increase size
- higher uncertainty cannot increase size
- lower capacity cannot increase size
- worse drawdown state cannot increase size
- negative penalized edge cannot produce long exposure unless explicitly allowed

### Enforcement

Promotion blocks above `paper_shadow` if:

- uncertainty is uncalibrated
- forecast fails OOS utility after costs
- hashes missing from experiment registration
- optimizer or sizing lockbox is missing
- feature timestamp source unauditable
- hard exposure caps missing
- heuristic signals lack governed sizing
- Kelly enabled without complete gate

### CLI

```bash
uv run tradingx forecast-report --model-id ...
uv run tradingx sizing-policy-check --strategy-id ...
uv run tradingx sizing-decision --strategy-id ... --forecast-ref ...
```

### Migration

Existing signals remain heuristic signals, not expected-return forecasts. Existing pseudo-Kelly sizing becomes `heuristic_sizing_not_kelly`. Heuristic signals can reach production only through governed sizing and portfolio utility validation after costs/capacity.

### Acceptance Criteria

- Forecast identity, feature manifest, label definition, and sizing policy are registered.
- Feature set, label definition, sizing caps, and selection rules are frozen before OOS evaluation or covered by nested validation/final lockbox.
- Feature timestamp source is auditable.
- Label overlap policy drives purge/embargo.
- Uncertainty is calibrated, not merely present.
- Forecasts improve OOS utility after costs vs no-forecast/simple baselines.
- Optimizer consumes only promotion-valid or uncertainty-penalized returns.
- Pseudo-Kelly is renamed/classified and cannot claim Kelly.
- True Kelly remains disabled unless gate satisfied.
- Hard exposure/cost/capacity/drawdown caps bind.
- Sizing monotonicity/property tests pass.

## Milestone 8: Short-Side Capability & Financing

### Goal

Prevent negative weights from being confused with executable shorting by separating research simulation from runtime capability and requiring broker/mode-specific evidence, fresh borrow data, financing costs, margin stress, corporate-action controls, forced-buy-in handling, and live-probe evidence.

### Core Rule

Short strategies may be researched with modeled financing, but runtime short promotion requires:

- broker/mode-specific short capability
- fresh borrow/locate/fee data
- order marking and locate documentation
- locate expiry, threshold-security, and close-out handling
- ex-dividend and corporate-action controls
- margin stress and portfolio interaction
- forced-buy-in and broker-initiated cover handling
- integration with cost/capacity evidence
- live-probe evidence before production

Mean reversion remains capped until short package exists or the strategy is redesigned long-only.

### Primary Files

- `src/tradingx/risk.py`
- `src/tradingx/runtime_portfolio.py`
- `src/tradingx/portfolio/live_construction.py`
- `src/tradingx/execution.py`
- `src/tradingx/costs.py`
- `src/tradingx/strategy.py`
- `src/tradingx/signals/mean_revert.py`
- `src/tradingx/promotion.py`
- `src/tradingx/types.py`
- `src/tradingx/__main__.py`
- `schemas/quant/short_capability_manifest.schema.json`
- `schemas/quant/borrow_availability_snapshot.schema.json`
- `schemas/quant/short_financing_model.schema.json`
- `schemas/quant/short_risk_report.schema.json`
- `schemas/quant/short_runtime_event.schema.json`
- `tests/fixtures/short_side/`

### Schemas

`short_capability_manifest` separates `short_research_simulation_supported` from `short_runtime_supported` and records broker ID, broker mode, API version, order-marking policy, shortability semantics, paper/live match status, allowed symbols, borrow/shortability sources, locate documentation requirements, locate expiry policy, freshness thresholds, threshold-security handling, close-out handling, broker-specific HTB/fee/recall/forced buy-in/dividend/corporate action/margin policies, exposure caps, live-probe requirement, and approval timestamp.

`borrow_availability_snapshot` records symbol, broker, mode, shortable/easy-to-borrow/hard-to-borrow flags, threshold-security status, borrow rate, fee timestamp, locate ID/ref, locate documentation ref, locate status/expiry, source, and staleness.

`short_financing_model` records borrow fee curve, locate fee policy, dividend liability, margin model, portfolio margin usage, concentration/gross/net policies, stress margin, cash collateral, fee stress, close-out cost policy, recall cost policy, forced-buy-in slippage, financing drag, and version.

`short_risk_report` records broker/mode, symbols tested, borrow coverage, historical borrow coverage, order-marking status, locate documentation coverage, locate expiry coverage, threshold-security status, close-out handling status, fee/margin/portfolio margin/recall/dividend/ex-dividend/corporate action/forced buy-in stress, paper/live semantics, live-probe refs, constraint status, and blockers.

`short_runtime_event` includes order marking rejected, locate missing/expired, threshold-security status changed, close-out required, borrow unavailable, fee spike, recall, forced buy-in, margin breach, dividend liability, short rejected, shortability changed, broker-initiated cover detected, ex-dividend risk, and corporate-action risk.

### Runtime Rules

- Negative target weights require short capability manifest.
- Sell-short intents require correct order marking and fresh broker/mode-specific borrow/locate snapshot.
- Stale borrow/locate/fee data blocks new shorts.
- Missing locate documentation or expired locate blocks new shorts.
- Threshold-security and close-out policies run before opening and while holding shorts.
- Policy defines whether stale data also forces reduction.
- Shortability changes produce event and apply policy.
- Ex-dividend/corporate-action checks run before opening and while holding shorts.
- Broker-initiated covers must reconcile and emit runtime event.
- Margin stress includes portfolio-level gross/net/concentration interaction.

### Historical Backtest Rules

Short backtests require a historical borrow availability path or are classified research-only. Backtests cannot assume every symbol was shortable for promotion-valid evidence.

Borrow fees, locate fees, dividend liability, forced-buy-in slippage, and short financing drag must feed Milestone 5 cost/capacity reports.

### Enforcement

Promotion blocks:

- above `research_only` if runtime short support is incomplete
- above `research_only` if short legal mechanics are missing
- above `paper_shadow` if broker/mode behavior is unverified
- above `tiny_live_probe` if live-probe short evidence is missing
- production if paper/live semantics mismatch or live-probe evidence is absent

Runtime blocks short target/order if manifest missing, runtime support false, order marking unsupported, symbol not shortable, locate missing/expired/undocumented, borrow/fee snapshot stale, threshold-security/close-out policy blocks, margin insufficient, ex-dividend/corporate-action policy blocks, or broker constraint is unknown.

### CLI

```bash
uv run tradingx short-capability-check --strategy-id mean-reversion-v1
uv run tradingx borrow-snapshot --symbol QQQ
uv run tradingx short-risk-report --strategy-id ...
```

### Migration

Existing short-emitting strategies are capped at `research_only`. Existing short backtests without borrow/financing/corporate-action/margin model become `legacy_short_evidence`.

### Acceptance Criteria

- Negative target weights cannot be silently clipped or ignored.
- Research short simulation is separate from runtime short support.
- Short-emitting strategies require broker/mode-specific capability for runtime promotion.
- Borrow/locate/fee freshness is enforced.
- Order marking, locate documentation, locate expiry, threshold-security handling, and close-out handling are enforced.
- Ex-dividend and corporate-action controls exist.
- Margin stress includes portfolio interaction.
- Broker-initiated covers reconcile and emit events.
- Short costs feed Milestone 5 evidence.
- Live-probe evidence is required before production short exposure.
- Mean reversion remains capped until short package exists or long-only redesign lands.

## Milestone 9: Live Probe & Operational Safety

### Goal

Make live-probe trading a bounded operational experiment with role-bounded approval, minimum real activity, fresh safety drills, broker-timeout state transitions, idempotent/reconciled order flow, rollback behavior, and post-probe recertification.

### Core Rule

Live probe can validate operational readiness only if it is:

- preapproved by role-bounded authority
- constrained by explicit capital/loss/activity limits
- protected by approved pre-trade market-access controls
- backed by fresh safety drills
- governed by a broker-timeout state machine
- fully idempotent and reconciled
- ended with post-probe recertification
- free of unresolved incidents

Live probe does not prove durable edge.

### Primary Files

- `src/tradingx/live_enablement.py`
- `src/tradingx/operator_control.py`
- `src/tradingx/runtime_host.py`
- `src/tradingx/runtime_portfolio.py`
- `src/tradingx/execution.py`
- `src/tradingx/risk.py`
- `src/tradingx/promotion.py`
- `src/tradingx/types.py`
- `src/tradingx/__main__.py`
- `schemas/quant/live_probe_plan.schema.json`
- `schemas/quant/live_probe_run_record.schema.json`
- `schemas/quant/live_probe_recertification_report.schema.json`
- `schemas/quant/authority_boundary.schema.json`
- `schemas/quant/broker_timeout_state_transition.schema.json`
- `schemas/quant/operational_safety_drill.schema.json`
- `schemas/quant/pre_trade_control_manifest.schema.json`
- `schemas/quant/runtime_override_event.schema.json`
- `schemas/quant/reconciliation_incident.schema.json`
- `tests/fixtures/live_probe/`

### Schemas

`authority_boundary` records approval type, identity provider, operator identity IDs, role registry version, role, scope, write authorization status, max exception duration, second approver requirement, approvers, canonical approval payload hash, signatures, approval time, and expiry.

`live_probe_plan` records strategy, broker, mode, symbols, capital/order/loss/order-count/participation/spread limits, duration, minimum order count, minimum filled notional, minimum reconciliation cycles, minimum sessions, no-signal outcome policy, start/success/rollback criteria, flatten policy, kill switch requirement, pre-trade control manifest ref, authority ref, approval, and expiry.

`live_probe_run_record` records status, orders, fills, filled notional, sessions, reconciliation cycles, slippage, quote quality, reconciliation, limit breaches, rollback, success criteria, minimum activity, and evidence refs.

`live_probe_recertification_report` records run refs, incidents, unresolved incidents, minimum activity, drill status, broker-timeout status, idempotency, reconciliation, cost observations, production eligibility, blockers, and approval.

`operational_safety_drill` records drill type, expected/observed behavior, pass/fail, freshness window, valid-until timestamp, staleness, evidence refs, and execution time.

`pre_trade_control_manifest` records price collars, fat-finger notional/share limits, max open orders, max order rate, duplicate prevention, idempotency key policy, cancel-on-disconnect behavior, self-trade prevention where relevant, broker buying-power/margin precheck, locate precheck for shorts, reject-on-missing-control behavior, control owner, drill refs, and expiry.

`runtime_override_event` records event type, priority, action, scope, reason, operator, authority ref, disabled controls requested, expiry, and timestamp. `disabled_controls_requested` must be empty.

`broker_timeout_state_transition` records order/intent/idempotency identifiers, retry sequence, dedupe window, state transition, trigger, reconciliation requirement, retry permission, and timestamp.

Timeout states:

- `submit_unknown`
- `ack_unknown`
- `fill_unknown`
- `cancel_unknown`
- `reconcile_required`
- `safe_halted`
- `recovered`

### Override Hierarchy

Runtime precedence:

1. Operator kill
2. Broker anomaly
3. Duplicate order or idempotency failure
4. Reconciliation mismatch
5. Stale/invalid market data
6. Drawdown/loss-limit breach
7. Model signal

Higher priority overrides lower priority. No exception may disable core controls.

### Runtime Rules

- Live probe requires approved, unexpired authority and plan.
- Live order entry requires approved, unexpired pre-trade control manifest.
- Safety drills must be fresh.
- Minimum activity must be met; otherwise status is `inconclusive`.
- No-signal outcome cannot be marked pass unless predeclared policy permits extension, not promotion.
- Idempotency key and broker client order ID are required.
- Timeout triggers reconcile before retry unless idempotency proves retry safe.
- Clock health is required.
- Stale data blocks orders.
- Missing price collar, fat-finger limit, open-order cap, duplicate prevention, cancel-on-disconnect policy, or required self-trade prevention blocks orders.
- Runtime must reject orders when any required pre-trade control is unavailable or indeterminate.
- Reconciliation is required before and after trading cycles.
- Rollback/flatten follows plan.
- Unresolved incidents block production eligibility.

### CLI

```bash
uv run tradingx live-probe-plan-check --probe-id ...
uv run tradingx run-live-probe --probe-id ...
uv run tradingx safety-drill --type kill_switch
uv run tradingx reconcile-live-state
uv run tradingx live-probe-recertify --probe-id ...
```

### Migration

Existing live/paper evidence is `legacy_live_probe_evidence` unless it has approved plan, authority boundary, pre-trade control manifest, limits, success criteria, rollback criteria, minimum activity record, reconciliation artifacts, drill evidence, and recertification report.

### Enforcement

Promotion follows `Non-Discretionary Production Blockers` first. Missing pre-trade controls cap at `paper_trading`. Promotion blocks above `tiny_live_probe` if minimum activity is not met, probe inconclusive, drill evidence stale, authority boundary missing, broker-timeout state machine missing, post-probe recertification missing, unresolved incident exists, idempotency/reconciliation evidence missing, or broker anomaly unresolved.

Runtime blocks live probe if authority approval invalid, plan expired, clock health invalid, kill switch unavailable, pre-trade controls unavailable, idempotency unavailable, stale-data checks unavailable, or reconciliation unavailable.

### Acceptance Criteria

- Live-probe plans define limits, activity, success, rollback, and authority.
- Pre-trade controls define price collars, fat-finger limits, open-order caps, duplicate prevention, cancel-on-disconnect behavior, self-trade prevention where relevant, and reject-on-missing-control behavior.
- Safety drills have freshness windows.
- Minimum activity gates pass/fail/inconclusive.
- Broker-timeout state machine is defined and tested.
- Idempotency spans intent hash and broker client order ID.
- Reconciliation incidents are artifacted.
- Manual exceptions are signed, scoped, expiring, and cannot disable core controls.
- Flatten behavior is explicit.
- Clock health is enforced.
- Post-probe recertification is required for production eligibility.
- Unresolved incidents block production.

## Milestone 10: Recertification & Change Control

### Goal

Make production approval expiring, evidence-bound, dependency-aware, and invalidated by unknown, unrecorded, material, critical, or breaking changes until replay equivalence or full recertification succeeds under role-bounded authority.

### Core Rule

Production approval is expiring evidence, not a permanent state. Any unknown, unrecorded, material, critical, dependency-unresolved, or breaking-schema change blocks production until resolved.

### Primary Files

- `src/tradingx/change_control.py`
- `src/tradingx/promotion.py`
- `src/tradingx/activation.py`
- `src/tradingx/runtime_strategy_registry.py`
- `src/tradingx/live_enablement.py`
- `src/tradingx/validation.py`
- `src/tradingx/experiments.py`
- `src/tradingx/data_fingerprint.py`
- `src/tradingx/drift/`
- `src/tradingx/__main__.py`
- `config/strategy/promotion/<strategy_id>.json`
- `schemas/quant/change_control_record.schema.json`
- `schemas/quant/evidence_invalidation_report.schema.json`
- `schemas/quant/replay_equivalence_report.schema.json`
- `schemas/quant/recertification_report.schema.json`
- `schemas/quant/drift_monitor_spec.schema.json`
- `schemas/quant/drift_monitor_report.schema.json`
- `schemas/quant/production_decay_event.schema.json`
- `tests/fixtures/change_control/`

### Milestone 1 Amendment

Promotion state projection gains:

- `production_approved_at_utc`
- `production_expires_at_utc`
- `last_recertification_report_id`
- `next_operational_review_due_utc`
- `next_statistical_review_due_utc`

These fields are derived from the append-only decision/recertification ledger. They are not an approval source of truth.

### Schemas

`change_control_record` records change ID, type, scope, unknown-scope flag, affected strategies, affected evidence refs, dependency index refs, materiality class, automatic classification, manual classification, confidence, classifier version, change hash, git SHAs, creator, replay requirement, recertification requirement, schema compatibility, and approval ref.

Automatic git diff classification is advisory only. Manual classification overrides it. Low confidence requires review. Unknown scope defaults to `critical`.

`replay_equivalence_report` records old/new artifacts, metric deltas, decision deltas, trade deltas, safety rule deltas, equivalence status, and blockers. Replay equivalence fails if any V5 materiality default fires.

`recertification_report` records production state before/after, reason, authority ref, risk accepted, evidence refs, freshness/statistical/cost-capacity/optimizer/live-probe/drift/incident statuses, approval status, approval, production expiry, next review due dates, and blockers.

`drift_monitor_spec` records monitored variables, reference windows, live windows, thresholds, regime labels, multiple-testing policy, alert latency, missing-data policy, minimum sample requirement, demotion rules, operator notification path, and expiry.

`drift_monitor_report` records monitored values, threshold results, regime classification, missing-data status, multiple-testing adjustment, alert time, demotion recommendation, and evidence refs.

Critical recertification requires two approvers through Milestone 9 authority boundary semantics.

`production_decay_event` records strategy, decay reason, previous/new state, triggering artifact, timestamp, and operator notification.

### Materiality Classes

Minor:

- docs-only
- UI-only display
- non-semantic refactor with replay equivalence

Material:

- strategy/model/feature/label code change
- data vendor/restatement
- cost/capacity model change
- optimizer/utility/lambda change
- broker API behavior change
- calendar/session logic change
- risk control change
- schema migration required

Critical:

- unknown change scope
- live incident
- reconciliation mismatch
- duplicate order
- unresolved broker anomaly
- kill-switch failure
- safety-control regression
- production safety rule change
- breaking schema change without migration

### Bypass Detection

If current code/data/config/schema hash differs from the last approved artifact and no `change_control_record` exists:

- blocker: `unrecorded_material_change`
- production blocked

Change impact must be resolved through the Milestone 3 dependency index, not only manual lists. If affected evidence cannot be enumerated:

- blocker: `dependency_scope_unresolved`
- production blocked

### Recertification Triggers

Immediate recertification or demotion when:

- production expiry passed
- operational/statistical review due date passed
- evidence stale
- data restatement affects evidence
- vendor/broker/API/schema changes
- model/feature/optimizer/risk/cost/capacity changes
- utility/lambda changes
- universe changes
- live drift monitor fails
- drift monitor spec missing or expired
- quote quality degrades
- strategy inactive beyond window
- live probe incident unresolved
- emergency control fires
- unrecorded material change detected

Periodic:

- monthly operational review
- quarterly statistical review
- immediate review after material/critical change

### Inactivity Decay

Production decays to `paper_shadow` if:

- no trades for predeclared inactivity window
- cost evidence stale
- borrow/shortability evidence stale
- live regime materially differs from last active period
- venue/broker behavior changed

### Enforcement

Production blocks if:

- current hash differs from approved hash and no change record exists
- change scope unknown
- dependency scope unresolved
- production expiry passed
- operational/statistical review due date passed
- recertification authority invalid
- breaking schema change lacks migration
- required replay missing or failed
- drift monitor spec missing, expired, or failed
- stale evidence
- inactive beyond window
- unresolved incident

Runtime live path checks approval freshness before each cycle and before order submission.

### CLI

```bash
uv run tradingx change-record --type code --scope ...
uv run tradingx replay-equivalence --change-id ...
uv run tradingx recertify-strategy --strategy-id ...
uv run tradingx drift-monitor-report --strategy-id ...
uv run tradingx production-decay-check --strategy-id ...
```

### Manual Exception Rule

Manual exceptions:

- expire
- cannot extend production indefinitely
- cannot bypass critical safety invalidation
- cannot disable kill switch, reconciliation, stale-data checks, idempotency, or dependency-scope resolution

### Migration

Existing production/paper approvals without recertification metadata become `legacy_approval`. They cannot support ongoing production until recertified. Breaking schema changes invalidate dependent artifacts until migrated.

### Acceptance Criteria

- Every material/critical change gets a `change_id`.
- Unknown scope defaults critical.
- Unrecorded hash differences block production.
- Dependency index resolves affected evidence.
- Replay-equivalence uses V5 materiality defaults.
- Material/critical changes invalidate or recertify affected evidence.
- Production approval expires without recertification.
- Operational/statistical due dates are enforced.
- Inactive strategies decay.
- Drift monitor specs define variables, reference/live windows, thresholds, multiple-testing policy, regime labels, alert latency, and demotion rules.
- Missing, expired, or failed drift monitors block production or trigger demotion.
- Unresolved incidents block production.
- Activation/runtime enforce approval freshness every cycle and before orders.
- Monthly/quarterly recertification artifacts exist.
- Golden replay reproduces valid, stale, invalidated, unrecorded, and recertified outcomes from artifacts alone.

## Initial Implementation Order

Milestone 0 is the policy layer that capital-bearing promotion must satisfy. Its authority-bearing artifacts depend on the Milestone 1 trust spine, so technical bootstrapping starts with Milestone 1.

The first technical implementation slice is Milestone 1 only, and it must include the full enforcement chain:

```text
schema -> artifact -> blocker -> CLI report -> activation refusal -> golden replay
```

For Milestone 1 specifically, that means:

```text
ledger schema -> signed decision/evidence fixture -> blocker evaluator -> promotion-check CLI -> activation refusal -> projection-drift and replay fixtures
```

Recommended execution waves:

1. Trust spine foundation: Milestone 1.
2. Mandate and allocation governance: Milestone 0.
3. Evidence provenance: Milestones 2 and 3.
4. Statistical and economic evidence: Milestones 4 and 5.
5. Portfolio and sizing: Milestones 6 and 7.
6. Runtime semantics and operations: Milestones 8 and 9.
7. Production lifecycle: Milestone 10.

Every wave must leave the system safer than it found it. A partially implemented milestone should add blockers and classification before adding any new pathway to promotion.

## Non-Goals

This plan does not:

- promise profitability
- claim any current strategy has production-grade edge
- authorize live shorting
- authorize production optimizer use
- authorize Kelly sizing
- replace human approval for production decisions
- replace legal, tax, compliance, or broker-specific review

It defines the evidence, artifacts, replay paths, blockers, and operational controls required before those claims can be responsibly made.
