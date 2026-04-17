<!--
Sync Impact Report
==================
Version change: 3.0.0 → 3.0.1
Bump rationale: PATCH — addresses 6 findings from the second Codex
  review round of v3.0.0 on 2026-04-17. All changes are clarifications
  or exception additions; no principles added, removed, or inverted.

  - Spec Kit constitution path pinned explicitly to
    `.specify/memory/constitution.md` throughout (six references
    updated). Source citation added to implementation_constraints.
  - Emergency-alert channel gate structure rewritten to remove the
    three-way contradiction between "before Gate 3" / "before Gate 4"
    / "part of Gate 4." Canonical chain: Phase 8 delivers
    implementation, Gate 3 requires initial round-trip, Gate 4
    requires a fresh round-trip within 7 days (to catch credential
    expiry between gates).
  - Principle VIII Rule 6 now explicitly acknowledges the session-
    handover exception to the "INDEX lists every versioned artifact"
    rule. The exception scales: per-session rows in INDEX would
    overwhelm the file; session handovers are tracked as an aggregate
    row plus ground-truth front-matter on each handover file.
  - Phase 0 acceptance text corrected: "five bootstrap files" →
    "seven bootstrap files" (matching the actual file count: 7).

Prior version history:
  2.2.1 → 3.0.0 (MAJOR): addressed 18 findings from first external
    review round (Codex + Claude Desktop); schema collision fix;
    gate split; walking-skeleton Phase 0; PDT update; sourced claims;
    YAML front-matter on constitution itself.
  2.2.0 → 2.2.1 (PATCH): distinguished Stage 1 paper capital ($100k)
    from Stage 2 live capital (≤ $10k).
  2.1.0 → 2.2.0 (MINOR): pinned Alpaca broker, SPY benchmark, Stage
    1–4 progression, secrets management, LLM research policy.
  2.0.0 → 2.1.0 (MINOR): tightened capital-preservation thresholds
    (halt 20% → 15%, Gate 1 max DD 25% → 20%).
  1.0.0 → 2.0.0 (MAJOR): added Principle X, expanded Principle VIII,
    session lifecycle with recovery.

Modified in this bump:
  - Front-matter: version 3.0.0 → 3.0.1; supersedes CONST-0001@3.0.0.
  - Preamble and multiple references: `memory/constitution.md` →
    `.specify/memory/constitution.md`.
  - Principle VIII Rule 6: session-handover exception added.
  - Additional Constraints / Environment: emergency-alert channel
    gate structure rewritten as explicit chain.
  - Development Workflow / Acceptance gates / Gate 3: initial SMTP
    round-trip test added as gate requirement.
  - Development Workflow / Acceptance gates / Gate 4: fresh SMTP
    round-trip test within 7 days clarified as separate from Gate 3.
  - Development Workflow / Phased delivery / Phase 0: "five
    bootstrap files" → "seven bootstrap files."

Added in this bump: session-handover exception to Principle VIII
  Rule 6.
Removed in this bump: nothing.

Templates requiring update (all complete in this bump):
  ✅ docs/INDEX.md — bumped to 1.2.0; new Recovery records section;
     session-handover aggregate row; pre-repository supersession
     section replaces prior "Superseded artifacts" section.
  ✅ docs/operations/session_recovery.md — made explicit that
     RECOVERY-NNNN entries go into INDEX's Recovery records section;
     path reference updated.
  ✅ docs/archive/project_brief.md — path reference updated.
  ✅ docs/archive/implementation_constraints.md — SMTP gate structure
     aligned with constitution; Spec Kit path source citation added.
  ✅ docs/operations/bootstrap_install.md — canonical Spec Kit path
     pinned; stale version numbers updated to 1.2.0/1.1.0.

Follow-up TODOs:
  - Operator to confirm actual Stage 2 live starting capital before
    Gate 4.
  - Operator has confirmed Germany is supported by Alpaca
    (2026-04-17, verbal confirmation in operator channel).
  - Operator to verify emergency-channel SMTP credentials work in
    Phase 8.
  - Stage 3 (crypto) requires constitution amendment and operator
    authorization before any Stage 3 code is written.
-->

---
id: CONST-0001
title: Trading bot constitution
version: 3.0.1
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: CONST-0001@3.0.0
superseded_by: null
author_session: SESS-0000-00-00-000
---

# AI-Assisted Autonomous Trading Bot Constitution

## Preamble

This constitution governs the design, implementation, validation, and
operation of one autonomous AI-assisted trading bot, built by AI coding
agents working in a shared repository under human operator supervision.

It is immutable during any single session. Agents cannot amend it mid-work.
Amendments follow the Governance section and require explicit operator
approval. When any other document, plan, task, or agent reasoning conflicts
with this constitution, the constitution wins.

The bot's mission is to grow a bounded capital budget over time through
disciplined, systematic, benchmark-aware trading, while minimizing
probability of ruin, catastrophic drawdown, and operational failure. Its
secondary benchmark-relative mission is to outperform the S&P 500 (SPY)
on a risk-adjusted basis — higher Sharpe ratio at comparable or lower
volatility — not merely higher absolute return.

The bot is built as ONE coherent system that matures through sequential
stages, NOT as a collection of modes. Each stage is unlocked only when
the previous stage has proven itself against the acceptance gates:

- **Stage 1 — Paper equities on Alpaca (US equities, S&P 500 benchmark).**
  The foundation. All initial design, validation, and learning happen
  here. This is the stage the constitution assumes unless noted
  otherwise. Must pass Gates 0 through 3.
- **Stage 2 — Live equities on Alpaca with small capital (≤ 10% of
  paper-traded notional).** Same bot, same market, real money. Unlocked
  only by Gate 4 sign-off from the operator.
- **Stage 3 (future) — Add crypto as a second isolated strategy.** A
  separate strategy with its own capital allocation, risk limits, and
  benchmark (BTC buy-and-hold). Shared infrastructure with Stage 1/2
  (data pipeline, OMS, risk engine, monitoring), but separate money and
  separate decision logic. Unlocked only after Stage 2 has demonstrated
  stable live operation for at least 6 months AND the operator
  explicitly authorizes the expansion.
- **Stage 4 (possibly never) — Multi-strategy capital allocation.**
  Portfolio-level coordination across Stages 1–3. Only considered if
  Stages 1–3 are genuinely working.

There is no "god mode" or unrestricted multi-market mode. Agents MUST
NOT propose or implement one. Every stage expansion is a deliberate
graduation with its own validation gates, not a configuration flag.

**Walking-skeleton principle.** Phase 0 MUST end with a working
end-to-end paper-trading pipeline (trivial strategy, real Alpaca paper
API, real data, real order, real reconciliation). Governance scaffolding
is validated AGAINST working code, not in the absence of it. If the
governance structure and the walking skeleton cannot coexist inside
Phase 0's time budget, the governance structure is wrong and MUST be
simplified — not the skeleton.

## Core Principles

### I. Survival Before Return (NON-NEGOTIABLE)

The bot MUST optimize Tier 1 objectives (survival and integrity) before
Tier 2 (capital growth) and Tier 3 (refinement). A bot that posts high
return by taking reckless risk, hidden leverage, concentration blowups, or
fragile overfit behavior is a failed bot regardless of its P&L curve.

Tier 1 objectives that the bot MUST NOT trade away: avoid ruin; avoid
catastrophic drawdown; avoid invalid trades; avoid uncontrolled leverage;
avoid stale-data trading; avoid state ambiguity; avoid duplicate orders;
avoid broken reconciliation; avoid unbounded tail risk; avoid silent
failures.

**Hard pre-trade constraints (Tier 1 enforcement):** every order MUST
pass all of the following checks before submission, and rejection is
silent for the strategy but logged at WARN or higher:

- **Liquidity filter.** Target symbol's 30-day average daily volume
  (ADV) MUST be ≥ 1,000,000 shares. Rationale: thin-ADV names have
  spreads that destroy retail strategies; this is a hard floor, not
  a strategy parameter.
- **Price floor.** Target symbol's last trade price MUST be ≥ $5.00.
  Rationale: sub-$5 names have outsized relative spreads, higher
  fraud risk, and PDT-equivalent regulatory complexity.
- **Concentration check.** Proposed order MUST NOT push single-symbol
  exposure above the configured cap (default 20% of equity).
- **Intraday-margin check (post-PDT framework).** Proposed order MUST
  NOT violate the broker's real-time intraday margin requirements
  under FINRA Rule 4210 as amended 2026-04-14. The legacy PDT
  designation has been eliminated, but intraday margin still applies.
  See the Regulatory subsection for details.
- **Stale-data check.** Most recent market-data observation for the
  target symbol MUST be within the configured stale-data window
  (default 60 seconds during regular market hours, configurable).
- **Stale-state check.** Most recent broker-state reconciliation MUST
  be within the configured stale-state window (default 5 minutes).
- **Kill-switch check.** No kill-switch flag set.
- **Live-mode check (defense in depth).** If order is live,
  ALL FOUR live-enable layers MUST agree.

These are constraints on the risk module, not suggestions to strategies.
The strategy MUST NOT receive feedback about which filters blocked it
(to prevent the strategy from learning to evade the filters).

**Rationale:** A bot that grows fast and dies is a catastrophic outcome for
the operator. Capital preservation compounds; capital loss is often
unrecoverable. This principle is the root of every other principle.

### II. Edge Is Never Assumed (NON-NEGOTIABLE)

All claimed edge MUST be treated as hypothetical until demonstrated through
leakage-free, cost-aware, out-of-sample validation AND successful paper
trading meeting the acceptance gates defined in the validation documents.

The agent MUST NOT claim a strategy is "profitable" or "working" on the
basis of backtest results alone. A backtest is a hypothesis generator, not
evidence.

Strategies MUST be rejected if any of the following hold: profitable only
before costs; fails out of sample; depends on narrow time windows; collapses
under realistic slippage (2× baseline) or fees (2× baseline); outperforms
only via hidden leverage or concentrated luck; unstable operationally.

**Rationale:** The graveyard of failed trading systems is filled with
backtests that looked excellent. Honest evaluation before capital deployment
is the only defense against self-deception.

### III. Test-Driven Development (NON-NEGOTIABLE)

Every unit of production code MUST be written to satisfy a pre-existing
failing test. The cycle is RED → GREEN → REFACTOR without exception.

Specific requirements:
- Tests MUST be written before the implementation they cover.
- Tests MUST be verified to fail before implementation begins.
- Implementation MUST be the minimum required to pass the test.
- Refactoring happens only after green.
- Every external integration MUST have a smoke test in `tests/smoke/` that
  exercises the real API in paper/sandbox mode.
- Every claim of "feature X works" MUST be backed by an executable test
  the operator can run from a clean checkout.

**Rationale:** Silent failures in trading cost real money. TDD forces
verifiable correctness and prevents the "it compiles so it works" failure
mode characteristic of AI-generated code.

### IV. Evidence Over Claims (NON-NEGOTIABLE)

The agent MUST NOT declare success without verifiable evidence. Every
performance claim MUST be reproducible via a committed script. Every
correctness claim MUST be backed by a passing test. Every API or library
fact MUST cite a source.

**Self-audit limitation.** An agent MUST NOT rely on its own review of
its own artifacts as evidence of consistency or correctness. Self-review
catches obvious errors but systematically misses the kinds of structural
and semantic issues an external reviewer finds in minutes. Whenever
possible, material artifacts (constitution amendments, specs, ADRs,
validation reports) SHOULD be reviewed by a distinct agent instance or
by the operator before being relied upon.

Specific prohibitions:
- No `TODO`, `FIXME`, `XXX`, `HACK`, or similar tags on the main branch.
- No silently-swallowed exceptions (`except: pass` or
  `except Exception: pass` are banned).
- No fake metrics: if a metric cannot be computed, report `N/A`; never
  return placeholder values like `0.0` or `1.0`.
- No mock or stub data in production code paths. Mock data MUST be
  explicitly marked (`FAKE_DATA=True` constant or `@uses_fake_data`
  decorator) and production mode MUST fail to start if any such path is
  reachable.
- No bare numeric literals in `src/` representing market, exchange, or
  regulatory facts without a `# source:` comment citing the authoritative
  reference.
- No production code inside notebooks. Notebooks are research-only and
  MUST NOT be imported by `src/`.
- No confident claims about external systems (APIs, products,
  regulations) without a verifiable source. When the agent cannot
  verify a claim before writing it, the claim MUST be marked
  `[UNVERIFIED]` and logged in `docs/handover/UNVERIFIED_CLAIMS.md`.

**Rationale:** Trading bots that "look right" but were never actually
verified are the primary cause of retail-algo losses. Evidence is the only
acceptable currency. The self-audit limitation is added because the v1.0
through v2.2.1 iteration of this very constitution contained 18 material
issues that the authoring agent's own audits missed and that external
reviewers found in minutes.

### V. Simplicity Earns Its Cost (NON-NEGOTIABLE)

The bot MUST use the simplest approach that meets its requirements.
Complexity MUST be justified in an ADR before introduction.

Specific applications:
- ML is allowed ONLY when it demonstrably beats simpler baselines *net of
  costs* with statistical significance. If the ML component does not beat
  the baseline, it MUST be removed.
- Deep learning MUST NOT be used where a linear or tree-based model
  performs comparably.
- Reinforcement learning MUST NOT be used for alpha generation. It MAY be
  used for execution optimization if justified in an ADR.
- LLM-driven price prediction from raw candles is prohibited.
- The agent MUST NOT introduce libraries, services, or infrastructure
  components not required by the current task.
- Document length is a warning sign. A constitution, spec, or brief that
  grows past ~500 lines is likely accumulating contradictions faster
  than they can be caught. Agents SHOULD push back against length and
  favor splitting into focused documents.

**Rationale:** Complexity hides bugs. Every additional component is an
additional failure mode and an additional surface for hallucination.
Simpler systems are auditable; complex ones are aspirational.

### VI. Autonomy Without Self-Modification (NON-NEGOTIABLE)

The bot MUST run its own decision loop, decide when to enter/exit/hold/
abstain, enforce its own rules automatically, and stop itself when
conditions are unsafe. The bot MUST NOT, at runtime:

- Retrain models that affect live positions.
- Adjust risk limits, position sizes, or concentration limits.
- Modify strategy parameters, thresholds, or behavior outside
  version-controlled config changes.
- Invent new objectives or modify its own mission.
- Rewrite its own code or configuration files.

Any change to strategy, risk, or sizing behavior MUST go through a
human-approved config or code change with a corresponding ADR.

**Rationale:** Runtime self-modification eliminates the ability to audit
why the bot did what it did. Every dangerous production outage in
autonomous systems begins with "the system decided to…" An auditable,
static policy is safer than an adaptive one.

### VII. Live Trading Is Disabled By Default (NON-NEGOTIABLE)

Live trading MUST be disabled at every layer: configuration, environment
variable, code-level feature flag, AND broker adapter. All four MUST be
positively enabled for any live order to reach an exchange.

Live mode MUST NOT be enabled until Acceptance Gates 0, 0.5, 1, 2, and 3
have all passed and the operator has explicitly signed off on Gate 4.
Telegram commands and other runtime interfaces MUST NOT be able to enable
live trading.

**Rationale:** The transition from paper to live is the single riskiest
event in a trading bot's lifecycle. Defense in depth across four
independent flags ensures no single mistake (merge conflict, environment
leak, misconfigured secret) can cause unintended live execution.


### VIII. Repo-First Execution and Artifact Versioning (NON-NEGOTIABLE)

Every material decision MUST produce a repository artifact: code,
configuration, test, documentation, ADR, script, or runbook. Decisions
made "in conversation" without corresponding artifacts are not decisions
and are not binding on future sessions.

The session handover files in `docs/handover/` are the source of truth
for project state. The `.specify/memory/constitution.md` file is the source of
truth for policy. The ADRs in `docs/adrs/` are the source of truth for
architectural decisions.

Every session MUST begin by reading the handover files and MUST end by
updating them. Half-finished work MUST be explicitly marked
`IN_PROGRESS` with the exact resume point.

**Artifact versioning (applies to ALL of: ADRs, specs, plans, tasks,
requirements, design docs, runbooks, handover files, configuration
schemas, ML model cards, validation reports, and any document that
another session or agent will read as authoritative):**

Every versioned artifact MUST carry a YAML front-matter header at the
top of the file, immediately after any Sync Impact Report comment and
before any content:

```yaml
---
id: <TYPE>-<NNNN>          # e.g., ADR-0007, SPEC-0012, RUNBOOK-0003
title: <human-readable title>
version: <MAJOR.MINOR.PATCH>
status: active             # draft | active | superseded | deprecated | rejected
created: <YYYY-MM-DD>
last_amended: <YYYY-MM-DD>
supersedes: <id>@<version> | null
superseded_by: <id>@<version> | null
author_session: <SESSION_ID>
---
```

**Schema note: `status` vs `session_status`.**

- `status` is reserved for VERSIONED ARTIFACT LIFECYCLE and takes values
  `draft | active | superseded | deprecated | rejected`.
- `session_status` is reserved for SESSION LIFECYCLE and takes values
  `open | completed | handed_forward | abandoned`.

These two fields MUST NOT be conflated. Session handover files carry
BOTH: a `status` field reflecting whether the handover document itself
is `active` or has been superseded by a later correction, and a
`session_status` field reflecting what the session produced. This split
was introduced in constitution v3.0.0 to resolve a schema collision
identified in external review.

Rules:

1. **At most one `active` version exists per `id`.** All other versions
   of the same `id` MUST carry status `superseded`, `deprecated`, or
   `rejected`. An agent reading an artifact MUST check `status` first
   and MUST NOT act on a non-active artifact without following its
   `superseded_by` pointer.

2. **Superseded documents stay in the repository.** They are NOT
   deleted. Git history preservation is not sufficient — the file must
   remain readable so cross-references and historical reasoning stay
   intact.

3. **Versioning is semantic:**
   - `MAJOR`: change that inverts or removes a previous commitment;
     requires an ADR documenting the inversion.
   - `MINOR`: additive change (new principle, new constraint, expanded
     scope).
   - `PATCH`: clarifications, typos, formatting, non-semantic refinements.

4. **When an artifact is superseded**, the replacement artifact MUST
   set `supersedes: <old_id>@<old_version>`, and the old artifact's
   `status` MUST be flipped to `superseded` with
   `superseded_by: <new_id>@<new_version>`. Both updates happen in the
   same commit.

5. **Every new document is born at version 1.0.0 with status `draft`**.
   It becomes `active` only when the operator or the phase's acceptance
   criteria promote it. A `draft` MUST NOT be relied on by subsequent
   work.

6. **A central index** at `docs/INDEX.md` lists every versioned
   artifact with its current active version, status, and path. Agents
   update this index in the same commit as any status change. The
   index is the fast lookup; the front-matter is the ground truth; on
   conflict, the front-matter wins and the index is corrected.

   **Exception: session handovers.** Session handovers (id pattern
   `SESS-*`) carry full front-matter per this principle but are NOT
   listed as individual rows in INDEX. They are tracked by aggregate
   (one row summarizing the collection) because per-session rows
   would overwhelm INDEX as sessions accumulate. The collection is
   discoverable by directory listing in
   `docs/handover/SESSIONS/`. This exception is documented in
   INDEX.md itself and applies ONLY to session handovers; every
   other artifact type is listed per-row.

7. **Code changes are versioned via git** and via semantic-version
   tags at phase boundaries. No other versioning scheme is needed for
   code. `src/` files do not carry front-matter.

8. **Configuration files** carry a simplified header:
   ```yaml
   # config_version: 1.2.0
   # last_amended: 2026-04-22
   # schema: config/schemas/risk_policy_v1.json
   ```
   Schema changes MUST bump MAJOR; parameter value changes MUST bump
   MINOR or PATCH depending on severity.

9. **Decisions without versioned artifacts do not exist.** If an agent
   makes a decision in chat, that decision is not binding until it
   lands in an ADR with `status: active`. Subsequent sessions MUST NOT
   be expected to honor an unwritten decision.

10. **When a conflict is found** between two artifacts both claiming
    `status: active` for the same `id`, the agent MUST halt and raise
    a Stop-and-Ask. Silent resolution is prohibited.

**Rationale:** AI coding sessions have ephemeral context. Different
agents across different sessions will read these documents. Without
explicit status markers and version tracking, "the latest version"
becomes a detective game that each agent solves differently. Explicit
`status: active` in the front-matter makes the answer unambiguous and
machine-readable.

### IX. Specification Separation (NON-NEGOTIABLE)

Requirements documents (`spec.md`) MUST remain technology-agnostic: what
the bot does and why, expressed in domain terms. Technical plans
(`plan.md`) contain frameworks, libraries, architecture, and
implementation details.

Technical details in `spec.md` block merge. High-level business content in
`plan.md` is acceptable only for framing. The agent MUST enforce this
separation during the specify and plan phases.

**Bootstrap application of this rule.** The project's initial input
documents mirror this split:

- `project_brief.md` is the tech-agnostic source for `/speckit.specify`.
- `implementation_constraints.md` is the pinned-technical-choices
  document, used as input to `/speckit.plan` and referenced by ADRs.

Both documents exist in `_bootstrap/` before Phase 0 and are moved to
`docs/` during Phase 0 as described in `bootstrap_install.md`.

**Rationale:** Mixing "what" and "how" makes specs un-reviewable by
non-engineers and un-updateable when the tech stack changes. Separation
keeps product intent stable as implementation evolves.

### X. Human-Machine Interfaces (NON-NEGOTIABLE)

The bot has three distinct human interfaces, each with a specific scope.
No interface may exceed its scope, and none may bypass safety controls.

**1. Telegram operator channel** (real-time, bidirectional, narrow).

Purpose: real-time notifications and narrow command vocabulary as
defined in the operator channel specification. Telegram is the hot
path — low-latency, always-on, phone-accessible.

Telegram MUST NOT be used for: rich monitoring dashboards; parameter
editing; viewing historical trade data; configuring the bot.

**2. Observability dashboards** (read-only, continuous).

Purpose: continuous visibility into bot state, P&L, positions,
exposure vs limits, order flow, error rate, data freshness, broker
connectivity. Implementation: Prometheus for metrics collection and
Grafana for visualization, OR an equivalent combination justified in
an ADR.

The dashboards MUST be read-only. They MUST NOT expose any control
surface that could modify bot state, configuration, or positions.

**3. Local control and configuration web app** (read-write, bounded).

Purpose: view and edit configuration, inspect trade history, drill
into signals and features, browse the handover files and session log,
view open Stop-and-Ask questions, and compose config changes for
commit.

Specifications:

- MUST be implemented as a local web application served from the
  machine hosting the bot, bound to `localhost` or the local private
  network only.
- MUST NOT be exposed to the public internet. No cloud hosting. No
  port-forwarding. If remote access is needed, the operator uses a
  VPN or SSH tunnel.
- MUST be built with a lightweight stack — FastAPI plus HTMX, or
  FastAPI plus a minimal SPA — chosen in an ADR. No Electron. No
  cloud-hosted SaaS. No native mobile apps.
- MAY be accessed from any device with a browser (laptop, phone,
  tablet) on the local network.
- MUST support read-only operation by default. Write operations
  (config edits, etc.) MUST be opt-in via a config flag that is off
  by default.
- MUST NOT mutate live configuration directly. Config changes
  composed in the UI are written to disk as proposed diffs, the
  operator reviews them, and they take effect only via an explicit
  commit + config-reload flow — the same path any other config change
  follows.
- MUST NOT enable live trading, change risk limits at runtime,
  bypass acceptance gates, or modify the constitution or ADRs.
- MUST use the same authentication model as the rest of the system —
  no separate password or account system. If remote access is
  enabled, it is authenticated via the OS/SSH layer, not via
  application-level credentials.
- MUST respect all other constitution principles. In particular,
  Principle VI (no runtime self-modification) applies: the UI cannot
  cause the bot to modify itself.

**Prohibited interfaces:**
- Native desktop applications (Electron, Tauri, etc.) unless justified
  in an ADR that demonstrates a specific need the local web app
  cannot meet.
- Native mobile applications — phone access is via browser to the
  local web app on the home network, or via Telegram when remote.
- Public cloud-hosted control planes — the bot's control surface
  stays on the operator's machine.
- Any interface that can bypass the config-commit-reload safety path.

**Rationale:** Three scopes, three tools, no overlap. Telegram is for
the 5% of moments that need immediate attention. Grafana is for the
continuous monitoring that needs visual density. The local web app is
for the reflective sessions where the operator reviews, configures,
and learns. Mixing scopes (e.g., putting trade buttons in Telegram,
or building a cloud dashboard that can change risk limits) creates
attack surface and user-error surface without meaningful benefit.
Keeping the control plane local eliminates an entire category of
remote-compromise risk.

## Additional Constraints

### Environment (pinned; MAY be changed only via ADR)

- Language: Python 3.11 or later for research, backtest, strategy,
  signals, and orchestration.
- Package manager: `uv` OR `poetry`, selected in Phase 0, never mixed.
- Type checking: `mypy --strict` on `src/`; enforced in CI.
- Linting/formatting: `ruff` + `black`; enforced in CI.
- Test framework: `pytest`; coverage ≥ 80% on `src/`; enforced in CI.
- Backtest engine: Nautilus Trader OR VectorBT Pro, selected in Phase 1.
  Building a backtest engine from scratch requires an ADR with evidence
  that both fail to meet requirements.
- Container runtime: Docker; Docker Compose for local development.
- CI: GitHub Actions.
- OS target: Linux (Ubuntu LTS). macOS for local development only.
- Timestamps: ALL internal timestamps MUST be UTC
  (`datetime.timezone.utc`). No naive datetimes anywhere in the code.
- Numeric type: `decimal.Decimal` for all money, prices, and quantities
  that touch orders. `float` is permitted for statistics and ML features
  only, never for position sizing or order submission.
- **Broker (Stage 1 and 2):** Alpaca. Paper trading endpoint
  `https://paper-api.alpaca.markets`, live endpoint
  `https://api.alpaca.markets`, market data endpoint
  `https://data.alpaca.markets`. SDK: `alpaca-py` (official Python
  library), pinned to a specific minor version in the project's
  dependency manifest. Stage 1 uses paper credentials exclusively.
  Source for endpoints: Alpaca paper trading documentation at
  `https://docs.alpaca.markets/docs/paper-trading`, retrieved
  2026-04-17.
- **Benchmark:** SPY (the SPDR S&P 500 ETF) as the primary benchmark
  for Stage 1 and Stage 2. Risk-adjusted comparison (Sharpe, Sortino,
  Calmar) is the PRIMARY success measure. Absolute return comparison
  is a secondary check. A strategy that returns more than SPY but with
  materially higher volatility has NOT beaten the benchmark for
  purposes of this constitution.
- **Market hours (Stage 1 and 2):** regular US equity market hours
  ONLY — 09:30 to 16:00 US Eastern Time, Monday through Friday,
  excluding US market holidays. Pre-market and after-hours trading
  are explicitly OUT OF SCOPE for Stage 1 and Stage 2. Enabling
  extended-hours trading requires an ADR documenting the risk
  rationale (wider spreads, thinner liquidity, different order-type
  semantics) and explicit operator approval.
- Operator channel (primary, real-time): Telegram, via the official
  `python-telegram-bot` library. Used for all alerts, Stop-and-Ask
  questions, and the narrow command vocabulary defined in Principle X.
- Operator channel (secondary, non-urgent): ClickUp, via the ClickUp
  API. Used only for non-urgent reporting such as weekly performance
  summaries or Stop-and-Ask items that have explicit "no time
  pressure" status. ClickUp MUST NOT be on the hot path for alerts,
  risk events, or kill-switch notifications.
- **Emergency-alert channel: SMTP email, pinned as default.** Used
  ONLY for CRITICAL events when the primary Telegram channel is
  unreachable. Gate structure:
    - **By end of Phase 8:** SMTP sender implementation exists in
      `src/` and is wired into the alert pipeline.
    - **As part of Gate 3 (paper-trading acceptance):** an initial
      end-to-end round-trip test (bot composes alert → SMTP send
      → operator inbox delivery confirmed) MUST pass. Without a
      passing round-trip at Gate 3, Gate 3 is NOT passed.
    - **As part of Gate 4 preflight:** a FRESH round-trip test
      (within 7 days of the Gate 4 live-enablement decision) MUST
      pass, to catch credential expiry or config drift between
      Gate 3 and Gate 4.
  The operator MAY override the default channel to Twilio SMS or a
  secondary Telegram bot via ADR, but the default is SMTP.
- Local web app framework: FastAPI for the HTTP layer plus HTMX for
  interactivity, OR FastAPI plus a minimal single-page React
  application, selected in a Phase 3 ADR. No Electron, no Tauri, no
  cloud-hosted control plane.
- Metrics and dashboards: Prometheus for metrics collection plus
  Grafana for dashboards, unless an equivalent combination is justified
  in an ADR.
- Secrets management: `python-dotenv` for loading environment variables
  from `.env` files. Never hardcoded. Never committed. See the
  "Secrets and credentials" subsection below for full rules.
- External LLM use (research only, never in the live loop): the coder
  AI MAY call OpenAI, Google Gemini, Anthropic, or similar LLM APIs
  during research, development, debugging, and design work. LLM APIs
  MUST NOT be called from any code path in `src/` that can influence a
  live trading decision. See the "External LLM usage policy"
  subsection below.

### Secrets and credentials

- Real secrets MUST live only in local `.env` files that are excluded
  by `.gitignore`. The `.gitignore` MUST block `.env` and `.env.*`
  but permit `.env.example`.
- `.env.example` MUST exist in the repository root, MUST list every
  required variable with a placeholder value (e.g.,
  `ALPACA_PAPER_API_KEY=your-paper-key-here`), and MUST include an
  inline comment on each line explaining what the variable is and
  where to obtain it.
- Trading credentials and LLM/research credentials MUST live in
  SEPARATE files:
  - `.env` — trading, broker, notification channels, core runtime.
  - `.env.research` — LLM API keys used during development and
    research.
  This separation ensures the research environment cannot
  accidentally have trading credentials loaded and vice versa.
- On bot startup, configuration loading MUST fail closed if any
  required variable for the active mode is missing or malformed. The
  bot MUST NOT silently default to a safe-looking but unconfigured
  state.
- API keys MUST be the minimum scope required for the task. Trading
  keys for Alpaca MUST NOT include withdrawal permissions. Read-only
  keys MUST be used wherever trading permissions are not required.
- The coder AI MUST NOT paste real credential values into any
  commit, issue, log output, test fixture, error message, or
  documentation file. If the coder AI detects that real credentials
  have been exposed (including in prior commits), it MUST halt and
  raise a Stop-and-Ask with CRITICAL severity and recommend
  immediate key rotation.
- During Phase 0 scaffolding, the coder AI creates the structure of
  `.env` and `.env.research` as empty placeholder files with
  explanatory comments, alongside `.env.example`. The operator then
  fills in the real values locally, outside any AI-assisted session.

### External LLM usage policy

- **Research use (allowed):** looking up library documentation,
  summarizing academic papers, generating draft code, reviewing
  designs, explaining concepts, helping debug error messages, drafting
  ADRs, generating test cases. All such use happens during development
  or in offline analysis, with outputs reviewed by the coder AI and
  validated against real tests before merging.
- **Live-loop use (prohibited):** LLM APIs MUST NOT be called from
  any path in `src/` that runs during paper trading, live trading, or
  any decision loop that produces orders or changes risk state. No
  LLM in the signal path. No LLM in the risk-decision path. No LLM
  parsing market data or news to decide what to trade.
- **Operator communication (allowed with caution):** LLM APIs MAY be
  used to translate alerts or reports from technical to plain
  language for operator consumption — but only as a presentation
  layer, never as a decision layer. Any LLM-assisted message MUST be
  labeled as such so the operator knows a model was in the loop.
- **Separation of concerns:** the process that runs trading logic MUST
  NOT hold LLM credentials. LLM-using processes run in separate
  environments with separate `.env.research` configuration. A
  compromised research environment therefore cannot affect trading.
- **Rate-limit awareness:** all external LLM calls MUST implement
  exponential backoff on rate-limit responses and MUST respect
  per-provider quotas. Infinite retry loops on 429 responses are
  prohibited.

### Regulatory and tax context (operator is a German resident; broker is US-based)

Stage 1 and Stage 2 trade US equities via Alpaca, a US-regulated
broker. This means:

- The bot does NOT operate on a German or EU trading venue. German
  HFT classification rules under the KWG and the High Frequency
  Trading Act are therefore NOT directly triggered by this
  architecture. However, prudent design still avoids patterns that
  would resemble HFT under any jurisdiction.
- The bot MUST NOT use co-location, proximity hosting, or any other
  latency-minimizing infrastructure.
- The bot MUST have a bounded, configurable message rate. The default
  MUST be documented in an ADR and MUST be consistent with a
  low-frequency discretionary-style bot (measured in
  messages-per-minute, not messages-per-second).
- The bot MUST NOT engage in market-making behavior (continuous
  two-sided quoting).
- The operator (German resident) is responsible for German tax
  treatment of gains and losses realized through a US broker. Foreign
  broker gains are taxable in Germany and reporting obligations
  apply. The bot's documentation MUST note that the operator is
  responsible for verifying their own legal and tax position before
  live enablement. This is not legal advice.
- **Pattern Day Trader rule — eliminated 2026-04-14.** On
  2026-04-14 the SEC approved FINRA's rule change (SR-FINRA-2025-017,
  SEC Release No. 34-104572) eliminating the Pattern Day Trader
  designation and the $25,000 minimum equity requirement that had
  applied since 2001. The legacy rules are replaced by new intraday
  margin standards under amended FINRA Rule 4210. Source:
  `https://www.federalregister.gov/documents/2026/01/14/2026-00519/`
  for the original filing; approval confirmed by multiple 2026-04-14
  and 2026-04-15 sources. The rules take effect 45 days after FINRA
  publishes the Regulatory Notice, with an 18-month phase-in period.
  Implications for this bot:
    - The $25k account minimum for day trading is GONE. A Stage 2
      ≤ $10,000 account is no longer barred from intraday trading
      on that basis alone.
    - Real-time intraday margin monitoring now applies. Accounts
      that repeatedly breach intraday margin face a 90-day freeze.
    - The bot's risk module MUST implement an intraday-margin check
      as a hard pre-trade constraint (Principle I) that respects
      whatever the broker's current real-time margin policy
      specifies. The check MUST fail-closed if margin policy cannot
      be retrieved.
    - Alpaca's paper-trading environment still simulates the legacy
      PDT check as of 2026-04-17 (source:
      `https://docs.alpaca.markets/docs/paper-trading`). The bot's
      paper-mode code path MUST therefore handle both the legacy
      PDT-rejection response and the new intraday-margin-rejection
      response during the transition period.
- For Stage 3 (future crypto expansion), additional regulatory review
  MUST be performed at that time; German law treats crypto
  differently from equities and the constitution MUST be amended
  before Stage 3 begins.

### Data handling (market data, corporate actions, FX)

- **Market-data source.** Alpaca market data via `https://data.alpaca.markets`.
  Default (free) tier provides IEX-only data with documented
  limitations: occasional latency spikes, lower-volume name gaps.
  The stale-data threshold (default 60 seconds) reflects this tier;
  tightening to sub-30-second thresholds MUST be accompanied by an
  ADR that documents the upgrade to a paid SIP feed.
- **Corporate actions.** The data module MUST explicitly handle
  stock splits, reverse splits, dividends (cash and stock), mergers,
  spin-offs, ticker changes, and delistings. Backtests MUST use
  split-adjusted and dividend-adjusted data for historical
  comparisons. Live trading MUST detect and pause around events
  that could confuse position tracking (e.g., the bot holds a
  position on the day of a 2:1 split).
- **Dividends.** Alpaca paper trading does NOT simulate dividends
  (source: `https://docs.alpaca.markets/docs/paper-trading`).
  Strategy design and P&L attribution MUST account for this in paper
  mode: returns will diverge from a dividend-reinvested benchmark.
  Gate 3 evaluation MUST reconcile paper P&L against a
  dividend-adjusted SPY benchmark.
- **Wash-sale considerations.** For German tax reporting, the bot
  MUST emit per-trade records sufficient for the operator's
  accountant to compute taxable gains. The bot does NOT need to
  enforce US-style wash-sale rules (the operator is not a US tax
  resident), but MUST log trade timestamps, execution prices,
  symbol, side, and quantity in a format compatible with standard
  tax-software import.
- **FX treatment.** All bot-side accounting is in USD (Alpaca's
  operating currency). The operator's EUR-denominated cost basis
  and FX gains/losses are OUT OF SCOPE for the bot; the operator
  handles these separately. The bot MUST emit a monthly report of
  realized USD P&L that the operator can reconcile externally.
- **Liquidity universe.** The eligible trading universe is
  constrained by the Principle I hard filters (30-day ADV ≥ 1M
  shares; last price ≥ $5). This filter MUST be applied at the
  data-intake layer so that no strategy ever sees ineligible
  symbols in its feature space.

### Capital model

- **Paper trading capital (Stage 1):** $100,000 USD. Alpaca provides
  this as the default paper account balance (source:
  `https://docs.alpaca.markets/docs/paper-trading`, retrieved
  2026-04-17). All Stage 1 backtests, design, and paper-trading
  validation operate on this notional. Configurable via
  `config/capital/` but the default MUST reflect Alpaca's default.
- **Live trading starting capital (Stage 2):** to be confirmed with
  the operator before Gate 4. Constrained by Gate 4 to ≤ 10% of
  paper-traded notional. For a $100,000 paper account, Stage 2 live
  capital will therefore be ≤ $10,000 USD at the start.
- Design MUST work for any reasonable capital in the $1,000 to
  $1,000,000 USD range. Agents MUST NOT hardcode $100,000 anywhere
  in `src/` — the number comes from configuration.
- The operator's actual capital is held in EUR locally; currency
  conversion cost and timing is the operator's concern and is NOT
  modeled by the bot. The bot operates entirely in USD on the
  Alpaca side.
- **Drawdown thresholds and their reconciliation.**
  - **Design-target max drawdown:** 10% of high-water mark. Strategy
    selection in Phase 1 MUST prefer strategies whose honest
    backtest worst-case drawdown is at or below 10%.
  - **Backtest-ceiling max drawdown:** 15%. A strategy whose honest
    backtest (with realistic costs) shows a worst-case drawdown
    above 15% is REJECTED at Gate 1. This leaves a meaningful
    buffer before the live halt.
  - **Live hard-halt threshold:** 20% of high-water mark. (Raised
    from the prior 15% after external review identified that 5
    percentage points of margin above a 20% backtest ceiling
    produced halts on statistically normal behavior.) At 20%, new
    trades stop, the kill switch fires, and operator intervention
    is required before trading can resume.
  - **Interim halt thresholds** (configurable):
    - Daily loss: 3% of equity — halt new trades, allow exits.
    - Weekly loss: 6% of equity — halt all trading for the week.
    - Monthly drawdown: 10% of equity — halt and require operator
      intervention.
- Leverage policy default: 1.0× (no leverage). Any leverage MUST require
  an ADR and explicit config change.
- Compounding: profits reinvested by default; losses reduce position
  sizing proportionally via volatility or risk-budget scaling.
- Actual Stage 2 live starting capital MUST be confirmed with the
  operator via Stop-and-Ask before Gate 4.

## Development Workflow

### Phased delivery

Work proceeds through phases 0 through 9 as defined in the project
specification. A phase is complete ONLY when all of the following hold:
code committed; tests passing; documentation updated; configuration
updated; ADR(s) written for material decisions; acceptance criteria
verified; `docs/handover/STATE.md` updated.

No phase advances while `docs/handover/UNVERIFIED_CLAIMS.md` contains
unreviewed entries relevant to that phase.

**Phase 0 — walking-skeleton deliverable.** Phase 0 is not complete
until ALL of the following are true:

1. Repo scaffolding in place (directory structure, packaging,
   lint/type/test tooling, CI, Docker).
2. All seven bootstrap files moved from `_bootstrap/` to their final
   locations per `bootstrap_install.md`.
3. `scripts/check_index.py` and `./scripts/validate` exist and pass.
4. All initial ADRs written (Python version, package manager, broker,
   benchmark, stage progression).
5. **A working end-to-end paper-trading pipeline exists**, exercised
   by a smoke test runnable via `./scripts/validate`:
   - Reads Alpaca paper credentials from `.env`.
   - Authenticates to Alpaca paper API.
   - Fetches a live quote for SPY.
   - Submits a 1-share SPY paper buy order.
   - Waits for fill.
   - Submits a 1-share SPY paper sell order.
   - Reconciles final state against expected (flat, minor cash delta).
   - Persists all of the above to a structured log.
   - The entire round-trip MUST complete in a single Python process
     and MUST be re-runnable cleanly.
6. Gate 0 AND Gate 0.5 both passed.

If Phase 0 runs past three weeks of calendar time without producing
the walking skeleton, the coder AI MUST raise a Stop-and-Ask rather
than continuing to elaborate scaffolding. The failure mode being
guarded against is "governance eats implementation."

### Acceptance gates

Gates are divided into two tracks to prevent strategy-quality
requirements from blocking operational maturity (and vice versa):

**Operational gates** — tested on ANY strategy, including trivial ones
like SPY buy-and-hold. These gates prove the system works; they do NOT
prove any edge exists.

- **Gate 0 — Repo hygiene:** CI green; coverage ≥ 80%; no TODO/FIXME
  on main; configs validated on startup; all secrets properly scoped;
  all bootstrap scripts (`check_index.py`, `validate`) present and
  passing.

- **Gate 0.5 — Walking skeleton:** End-to-end paper-trading pipeline
  operational per the Phase 0 deliverable spec above. The bot can
  authenticate, fetch data, place orders, receive fills, reconcile
  state, and emit metrics — all via the real Alpaca paper API with
  a trivial strategy. No strategy-quality claim is made or
  required at this gate; only operational correctness.

**Strategy-quality gates** — tested on the specific candidate
strategy selected in Phase 1. These gates prove the strategy has
evidence-backed edge worth deploying.

- **Gate 1 — Backtest acceptability:** Net CAGR > SPY CAGR + 2%
  absolute OR (Sharpe ≥ 1.0 AND Sharpe ≥ SPY Sharpe × 1.3); max
  drawdown ≤ 15% (backtest ceiling; design target is 10%);
  Calmar ≥ 0.5; ≥ 3 years OOS with metrics within 30% of in-sample.
  Risk-adjusted outperformance is the primary criterion; absolute
  outperformance alone is insufficient if volatility is materially
  higher than SPY's. SPY benchmark comparison MUST use dividend-
  adjusted SPY returns over the identical OOS window with identical
  cost assumptions.

- **Gate 2 — Robustness:** Net profitable at slippage × 2 AND fees × 2;
  parameter sensitivity ±20% degrades Sharpe ≤ 30%; walk-forward Sharpe
  ≥ 0.5 on every rolling window ≥ 1 year.

- **Gate 3 — Paper trading:** Minimum 180 calendar days OR 100 closed
  trades, whichever comes first; no P1 incidents (from bugs, not market
  events); realized slippage within 1.5× backtest assumption; hit rate
  within 20% of backtest; realized Sharpe ≥ 0.5× backtest Sharpe; all
  state-recovery scenarios exercised; **initial SMTP emergency-channel
  round-trip test passed** (bot composes an alert, SMTP delivers it,
  operator inbox receipt confirmed). **Paper-fill realism
  adjustment:** because Alpaca paper fills orders against NBBO price
  without checking NBBO quantity (source:
  `https://docs.alpaca.markets/docs/paper-trading`), Gate 3 realized
  slippage MUST also pass a replay-simulator check that injects
  realistic quantity-aware slippage. If the paper-fill slippage and
  the replay-simulator slippage diverge by more than 2×, Gate 3 is
  NOT passed regardless of the paper-only number.

- **Gate 4 — Live enablement:** Gates 0, 0.5, 1, 2, and 3 all passed;
  operator signed off on `docs/operations/live_enablement_checklist.md`;
  starting live capital ≤ 10% of paper-traded notional; kill-switch
  tested in live-paper within 7 days; monitoring confirmed for ≥ 7
  days; **fresh** SMTP emergency-channel round-trip test passed within
  7 days of the Gate 4 decision (separate from the Gate 3 initial
  round-trip, to catch credential expiry or config drift).

Detailed numeric thresholds and validation scripts live in
`docs/validation/acceptance_gates.md`, created during Phase 1.

### Session handover and session lifecycle

**Session IDs.** Every coder session MUST generate a unique session ID at
the moment work begins and record it in `docs/handover/SESSION_LOG.md`.
The format is `SESS-<YYYY-MM-DD>-<NNN>` where NNN is a zero-padded
incrementing counter for that date.

**Session handover lifecycle.** Every session produces exactly one
handover record in `docs/handover/SESSIONS/<SESSION_ID>.md` at the end of
the session, with front-matter:

```yaml
---
id: SESS-2026-04-22-001          # the session ID; serves as artifact id
title: Session handover — SESS-2026-04-22-001
version: 1.0.0
status: active                   # artifact lifecycle, per Principle VIII
created: 2026-04-22
last_amended: 2026-04-22
supersedes: null
superseded_by: null
author_session: SESS-2026-04-22-001

# Session-specific fields below (session lifecycle, distinct from status):
session_status: open             # open | completed | handed_forward | abandoned
agent: <model name or identifier>
started: <YYYY-MM-DD HH:MM:SS UTC>
ended: <YYYY-MM-DD HH:MM:SS UTC>
phase: <phase number and name>
branch: <git branch name>
predecessor: <SESSION_ID> | null
successor: <SESSION_ID> | null
resume_point: <file:line or task id>   # required when session_status != completed
---
```

**session_status meanings:**
- `open` — session ended with work not yet finished; the next session
  picks it up. Resume point required.
- `completed` — all work from this session's plan is finished AND all
  tests pass AND there is no half-finished work. This is the only
  session_status that closes a session cleanly.
- `handed_forward` — session ended and the work was explicitly passed
  to a successor session (which has a `predecessor` pointer back to
  this one). Resume point required.
- `abandoned` — session was interrupted unexpectedly (crash, timeout,
  context loss) before the end protocol could run. The next session
  MUST run the recovery procedure in
  `docs/operations/session_recovery.md` before starting new work.

**Exactly one session MAY be active at a time on any given branch.**
`docs/handover/STATE.md` records the currently-active session ID, branch,
and started-at timestamp. A new session attempting to start on a branch
with an active session whose timestamp is less than 2 hours old MUST
halt and raise a Stop-and-Ask.

**Picking up interrupted work.** When an agent starts a new session and
finds prior handovers with session_status `open`, `handed_forward`, or
`abandoned`, it MUST:

1. Identify the most recent such handover on its target branch.
2. Read the `resume_point`, the referenced files, and any
   `WIP` commit markers (`# SESSION_HANDOFF`).
3. Read all prior handovers in the chain via `predecessor` pointers
   until reaching the most recent `completed` boundary — the chain of
   in-progress work.
4. In its Session Start Report, explicitly state which prior
   session(s) it is resuming and what was left unfinished.
5. On successful completion, flip the prior open handovers'
   session_status to `completed` AND set this session's handover to
   `completed`. All predecessor handovers in the chain move to
   `completed` together.
6. If this session also ends with work unfinished, the predecessor
   chain stays `open` and this session's handover is appended as the
   new `open` entry.

**Abandonment detection.** If the active session marker in `STATE.md`
has a timestamp older than 2 hours with no corresponding `ended`
entry in a session handover, the session is considered `abandoned`. The
next session MUST mark the prior session's session_status as
`abandoned`, run recovery, and record what was done in its own session
log.

**Completion criterion.** A session may only close with session_status
`completed` if: all tests pass; all work planned for the session is
done; no `IN_PROGRESS` markers remain in modified files; no new
`WIP` commits are left uncompleted; `docs/handover/UNVERIFIED_CLAIMS.md`
has no new unreviewed entries from this session; and
`docs/handover/STATE.md` reflects the completed state. If any of these
fail, session_status MUST be `open` or `handed_forward` and a resume
point MUST be recorded.

**Session start ritual (mandatory, no exceptions):**
1. Read `.specify/memory/constitution.md`.
2. Read `docs/INDEX.md` for active document versions.
3. Read `docs/handover/STATE.md`.
4. Read the last 3 session handovers in
   `docs/handover/SESSIONS/`.
5. Read `docs/handover/OPEN_QUESTIONS.md` and
   `docs/handover/UNVERIFIED_CLAIMS.md`.
6. Check for any open, handed_forward, or abandoned predecessor
   session(s) on the target branch and trace the chain.
7. Run `./scripts/validate` to establish a baseline.
8. Produce a Session Start Report with explicit statements of:
   phase, current task, session ID, predecessor (if resuming), what
   is being carried forward, and any contradictions found.

**Session end ritual (mandatory, no exceptions):**
1. Run `./scripts/validate`. Resolve what is resolvable.
2. Decide session_status (`completed` / `open` / `handed_forward` /
   `abandoned`). If unsure, default to `open`.
3. Write the session handover file in
   `docs/handover/SESSIONS/<SESSION_ID>.md` with full front-matter
   (including both `status` and `session_status`).
4. Update predecessor session_statuses if this session completed their
   work.
5. Update `docs/handover/STATE.md` to reflect new active state (or
   lack thereof).
6. Update `docs/INDEX.md` if any artifact status changed this session.
7. Append a one-line summary to `docs/handover/SESSION_LOG.md`.
8. Commit everything. No uncommitted work between sessions.

**Branching rules.** One active phase equals one active branch/worktree.
Only one agent may hold the active branch at a time (tracked in
`STATE.md`). Branches for different phases may proceed in parallel only
if their changesets do not overlap. Merges between phase branches
require: CI green, phase acceptance criteria met, automated and operator
code review complete. No fast-forward merges of unreviewed work.

### Stop-and-Ask

Agents MUST halt and ask the operator (via the Telegram operator channel
and `docs/handover/OPEN_QUESTIONS.md`) in these situations:
1. Setting or changing actual starting capital for live.
2. Any trade-off where one option reduces safety.
3. Any design choice that would cross into HFT classification.
4. Library or API with unspecified hidden cost or licensing restriction.
5. Paper trading results close to but not clearly passing Gate 3.
6. About to disable or weaken a risk control.
7. Advancing from Stage 2 to Stage 3 (adding crypto). Stage 3 requires
   explicit operator authorization and a constitution amendment before
   any Stage 3 code is written.
8. Phase 0 has not produced a walking skeleton within 3 weeks.

Agents MUST NOT disable or weaken any risk control, safety flag, or
acceptance gate to "make something work." Such situations are always
Stop-and-Ask.

### Commits and branches

- Every completed task (e.g., T001, T002) gets its own commit.
- Commit messages follow conventional commits and reference the phase
  and task ID.
- Merges between phase branches require CI green, acceptance criteria
  met, and code review (automated and operator).
- No fast-forward merges of unreviewed work.

### Anti-hallucination

- Every numeric constant representing a market, exchange, regulatory, or
  fee fact MUST have a `# source:` comment with a URL and retrieval date.
- Every external API call MUST cite the documentation URL and have a
  smoke test in `tests/smoke/`.
- Every regulatory, academic, or fee claim in docstrings or comments
  MUST cite a source or be marked `[UNSOURCED]` (for agent-internal
  use) or `[UNVERIFIED]` (for claims requiring operator verification).
- Every unverified claim MUST be logged in
  `docs/handover/UNVERIFIED_CLAIMS.md` and reviewed before phase advance.
- Every money-math function MUST include sanity assertions (non-negative
  sizes, positive prices, bounded leverage).

## Governance

This constitution supersedes all other practices, prompts, conversations,
and agent reasoning. When agents find a conflict between this constitution
and any other source, this constitution wins. When agents find a conflict
between two parts of this constitution, they MUST halt and raise a
Stop-and-Ask; they MUST NOT choose a side silently.

### Amendments

Amendments require:
1. A written proposal in the session log identifying the principle or
   clause to change and the rationale.
2. Explicit operator approval.
3. A version bump following semantic versioning:
   - **MAJOR:** backward-incompatible principle removal, redefinition, or
     relaxation of a NON-NEGOTIABLE.
   - **MINOR:** new principle added, or material expansion of guidance.
   - **PATCH:** clarifications, wording, typos, non-semantic refinements.
4. A Sync Impact Report prepended as an HTML comment at the top of this
   file, documenting what changed.
5. Propagation to dependent templates (plan, spec, tasks) and
   documentation.
6. **External review before activation.** Any MAJOR amendment (including
   this one) SHOULD be reviewed by a distinct agent instance or a human
   reviewer who did not author the amendment, before the amendment is
   treated as active. This reflects the self-audit limitation in
   Principle IV.

Agents MUST NOT amend this constitution directly. Agents MAY propose
amendments via Stop-and-Ask. Only the operator may enact them.

### Compliance review

All pull requests, code reviews, and phase advancements MUST verify
compliance with the principles above. Deviations require an explicit ADR
documenting the deviation, its scope, its rationale, and its expiration
condition. Deviations MUST NOT be permanent.

Complexity that violates Principle V MUST be justified in an ADR or
removed. Violations of Principles I, II, III, IV, VI, VII, VIII, IX,
or X are blockers; no phase advances while any such violation is
outstanding.

### Operator role

The operator is the sole human authority. The operator:
- Approves all phase advancements.
- Answers all Stop-and-Ask questions.
- Signs off on Gate 4 live enablement.
- Approves all amendments to this constitution.
- Holds the only credentials for live trading.

Agents MUST NOT assume operator approval from absence of response; if the
operator does not respond within a question's default timeout, agents
execute the conservative default defined in the question and log the
decision at ALERT severity.

---

**Version:** 3.0.1
**Ratified:** 2026-04-17
**Last Amended:** 2026-04-17
