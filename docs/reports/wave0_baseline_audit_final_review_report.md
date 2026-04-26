# Wave 0 Fresh Adversarial Review Report

## W0-FR-001

- Severity: high
- Affected file or component: `docs/superpowers/plans/2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md`
- Roadmap requirement involved: Wave 0 must inventory blocker-like strings in roadmap, code, tests, fixtures, CLI outputs, and web/report payloads, and record deterministic-cap gaps.
- Exact issue: The blocker inventory is still materially incomplete.
- Evidence from code, diff, tests, or validation output: Handoff lines 111-138 list selected blocker-like strings, but omit live-disable/web blockers emitted in `src/tradingx/config.py:433-450` and surfaced in `src/tradingx/web/app.py:425-441`, `1372-1383`, including `broker_mode_not_live`, `missing_live_credentials`, `config_layer_disabled`, `env_layer_disabled`, `code_layer_disabled`, `web_write_signing_unconfigured`, `operator_signoff_missing`, and `gate4_checklist_missing`. It also omits pre-trade and execution blocker/rejection codes emitted as runtime artifacts: `src/tradingx/risk.py:110-154`, `170-188`, `195-240` emits `non_positive_quantity`, `invalid_symbol`, `live_mode_disabled`, `liquidity_filter`, `price_floor`, `single_symbol_concentration`, `intraday_margin`, `stale_market_data`, `stale_broker_state`, and `kill_switch`; `src/tradingx/controller.py:465-527`, `653-680`, `950-980` persists `operator_halt`, `outside_regular_hours`, and broker rejection `reason_code`; `src/tradingx/execution.py:63-77` emits `insufficient_buying_power`, `restricted_symbol`, `symbol_halted`, `after_hours`, `market_closed`, `malformed_payload`, and `broker_rejected`. Tests assert several omitted strings, e.g. `tests/unit/test_live_enablement.py:47-69`, `132-146`.
- Why it matters: Wave 1's blocker registry and runtime refusal mapping can start from a false baseline. These omitted codes are exactly order-route, live-enable, web, and risk-control blockers that must not become unregistered promotion/runtime authority.
- Required fix: Expand the handoff blocker table to include all current live-disable, web governance, policy, pre-trade risk, controller, execution rejection, and report payload blocker-like strings, with source, emitting surface, current meaning, deterministic cap status, and registry/migration treatment.
- Required test or validation to prove the fix: Add a repeatable inventory check that extracts blocker-like literals from `src`, `tests`, `config`, CLI/web/report payloads, and excludes the handoff's own validation-command text; fail if any extracted code is absent from the handoff table or lacks an explicit exclusion reason.

## W0-FR-002

- Severity: high
- Affected file or component: Wave 0 metric-producing and promotion-implying surface inventory
- Roadmap requirement involved: Wave 0 must inventory current metric-producing and promotion-implying surfaces.
- Exact issue: The metric inventory remains gate-centric and omits non-gate research/backtest surfaces that produce quantitative metrics, recommendations, and artifacts.
- Evidence from code, diff, tests, or validation output: Handoff lines 73-109 do not mention `src/tradingx/evaluation.py`, `src/tradingx/backtest.py`, `scripts/run_backtest.py`, or `scripts/compare_vol_forecasts.py`. `src/tradingx/evaluation.py:406-515` computes candidate and benchmark metrics, adversarial checks, DSR, and `recommendation`. `src/tradingx/backtest.py:136-178` returns strategy/benchmark/active metrics, and `197-222` computes `total_return`, `cagr`, `sharpe_ratio`, and `max_drawdown`. `scripts/run_backtest.py:44-55` prints the backtest summary JSON. `scripts/compare_vol_forecasts.py:199-271`, `290-362`, and `522-555` computes forecast/backtest metrics, material winner fields, writes JSON/Markdown artifacts, and prints JSON.
- Why it matters: These surfaces can leak metrics, imply research selection, or be mistaken for promotion evidence without V5 labels. Missing them defeats the Wave 0 baseline goal and weakens later metric-vault, trial-lineage, replay, and non-authority-labeling work.
- Required fix: Add explicit rows for these research/backtest/evaluation scripts and functions, classify each as metric-bearing, promotion-implying, artifact-writing, exploratory, or legacy/non-authority, and update the V5 gap map where needed.
- Required test or validation to prove the fix: Run a source inventory for metric producers and artifact outputs across `src/tradingx` and `scripts`, including `sharpe`, `cagr`, `max_drawdown`, `forecast_metrics`, `backtest_metrics`, `recommendation`, `write_text`, and `print(json`, then verify every matched surface is represented or explicitly excluded.

## W0-FR-003

- Severity: medium
- Affected file or component: Wave 0 validation commands in the handoff
- Roadmap requirement involved: Wave 0 handoff must record validation command results; inventories must be reviewable from repeatable evidence.
- Exact issue: The added inventory validation commands are not strong enough to prove completeness and can self-match the handoff text.
- Evidence from code, diff, tests, or validation output: Handoff line 59 records a whitelist `rg` command over `docs src tests config`; because `docs` includes the handoff itself, the command can match its own pattern list. Handoff line 61 searches both the roadmap and the handoff for roadmap blocker codes, while the roadmap itself contains those codes and the handoff line itself contains the entire pattern list. The recorded result only says "non-empty" or "every ... appeared," not that every code has a handoff table row with classification.
- Why it matters: A future reviewer can get a passing validation trail even when rows are absent or classifications are incomplete. That is the same class of traceability weakness Wave 0 is supposed to eliminate.
- Required fix: Replace these with validation that parses or checks the handoff table rows directly, excludes the validation-command lines, and checks each expected code/surface independently.
- Required test or validation to prove the fix: Produce a saved command output or small checker result showing all expected codes/surfaces, their matched table row, deterministic-cap field, and explicit pass/fail counts.
