---
id: CONSTRAINTS-0001
title: Implementation constraints
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-0000-00-00-000
---

# Implementation Constraints

**Purpose.** This document lists the pinned technical choices the coder
AI must honor during Phase 2 (architecture) through Phase 9
(validation). It is the input to `/speckit.plan`, the technical
counterpart to `project_brief.md`.

It exists as a separate document to satisfy Principle IX
(Specification Separation) of the constitution. `project_brief.md`
stays tech-agnostic so it can feed `/speckit.specify` without
contaminating the formal spec with implementation details.

**Authority.** When this document conflicts with the constitution,
the constitution wins. When it conflicts with the project brief on
technical matters, this document wins (both are operator-approved;
this one is the technical source of truth).

**How to change a pinned choice.** Each pinned choice here is "decided
and not open for re-evaluation in Phase 1." Changing any of them
requires an ADR documenting the reason for the change and explicit
operator approval.

---

## Pinned technical choices

### Language and tooling

- **Language:** Python 3.11 or later.
- **Package manager:** `uv` OR `poetry` — the coder AI picks one in
  Phase 0 and documents the choice in an ADR. Mixing is forbidden.
- **Type checking:** `mypy --strict` on `src/`. Enforced in CI.
- **Linting and formatting:** `ruff` plus `black`. Enforced in CI.
- **Test framework:** `pytest`. Coverage ≥ 80% on `src/`. Enforced
  in CI.
- **Container runtime:** Docker. Docker Compose for local dev.
- **CI:** GitHub Actions.
- **OS target:** Linux (Ubuntu LTS). macOS for local development
  only.
- **Timestamps:** all internal timestamps MUST be UTC
  (`datetime.timezone.utc`). Naive datetimes are forbidden.
- **Numeric type:** `decimal.Decimal` for all money, prices, and
  quantities that touch orders. `float` is permitted for statistics
  and ML features only, never for position sizing or order
  submission.

### Broker (Stage 1 and 2)

- **Broker:** Alpaca. The operator has confirmed on 2026-04-17 that
  Germany is a supported country for live accounts.
- **Paper endpoint:** `https://paper-api.alpaca.markets`.
- **Live endpoint:** `https://api.alpaca.markets`.
- **Market data endpoint:** `https://data.alpaca.markets`.
- **SDK:** `alpaca-py` (official Python library), pinned to a
  specific minor version in the project's dependency manifest.
- **Stage 1 credentials:** paper only. Live credentials remain
  absent from the environment until Gate 4.
- **Source for endpoints:** Alpaca paper trading documentation at
  `https://docs.alpaca.markets/docs/paper-trading`, retrieved
  2026-04-17.

### Market data

- **Default data tier:** Alpaca IEX-only feed (free tier).
- **Known limitations of the free tier:** occasional latency spikes
  above 30 seconds during high-volume events; lower-volume symbols
  may show gaps. This is the reason the default stale-data
  threshold is 60 seconds rather than 30.
- **Upgrade path:** Alpaca paid SIP feed. Upgrading requires an ADR
  documenting cost, benefit, and the tightened stale-data threshold
  it unlocks.

### Market hours

- **Stage 1 and Stage 2:** regular US equity market hours only —
  09:30 to 16:00 US Eastern Time, Monday through Friday, excluding
  US market holidays.
- **Extended hours:** OUT OF SCOPE. Enabling pre-market or after-
  hours trading requires an ADR documenting the risk rationale
  and explicit operator approval.

### Benchmark

- **Primary benchmark:** SPY (SPDR S&P 500 ETF).
- **Comparison basis:** risk-adjusted (Sharpe, Sortino, Calmar) is
  primary; absolute return is secondary.
- **Benchmark accounting:** dividend-adjusted SPY returns over the
  identical window with identical cost assumptions. Point-to-point
  unadjusted comparisons are misleading and MUST NOT be used.

### Capital (Stage 1 design default)

- **Paper trading notional:** $100,000 USD. Source: Alpaca paper
  trading documentation, retrieved 2026-04-17. Alpaca provides this
  as the default paper account balance.
- **Live trading starting capital:** to be confirmed before Gate 4.
  Gate 4 caps this at ≤ 10% of paper-traded notional (≤ $10,000 on
  a $100k paper account).
- **Design range:** $1,000 to $1,000,000 USD. The bot MUST work for
  any reasonable capital in this range; $100,000 MUST NOT be
  hardcoded in `src/`.
- **Operating currency:** USD. The operator's EUR-denominated costs
  and FX gains/losses are OUT OF SCOPE.

### Operator channels

- **Primary (real-time):** Telegram, via the `python-telegram-bot`
  library. Used for all alerts, Stop-and-Ask questions, and the
  narrow command vocabulary.
- **Secondary (non-urgent):** ClickUp, via the ClickUp API. Used
  for weekly performance summaries and non-urgent Stop-and-Ask
  items. ClickUp is NOT on the hot path.
- **Emergency-alert channel:** SMTP email. Gate structure:
  - By end of Phase 8: SMTP sender implementation exists in `src/`
    and is wired into the alert pipeline.
  - As part of Gate 3: initial round-trip test (bot composes →
    SMTP delivers → operator inbox confirms) MUST pass.
  - As part of Gate 4 preflight: a fresh round-trip test within
    7 days of the Gate 4 decision MUST pass.
  Operator MAY override to Twilio SMS or a secondary Telegram bot
  via ADR; default is SMTP.

### Secrets and environment files

Two separate `.env` files enforce separation of concerns:

- **`.env`** — trading, broker, notification channels, core runtime:
  - `ALPACA_PAPER_API_KEY`
  - `ALPACA_PAPER_API_SECRET`
  - `ALPACA_PAPER_ACCOUNT_ID`
  - `ALPACA_LIVE_API_KEY` (empty until Gate 4)
  - `ALPACA_LIVE_API_SECRET` (empty until Gate 4)
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_ALLOWED_CHAT_IDS`
  - `CLICKUP_API_TOKEN`
  - `CLICKUP_WORKSPACE_ID`
  - `CLICKUP_LIST_ID`
  - `SMTP_HOST`
  - `SMTP_PORT`
  - `SMTP_USERNAME`
  - `SMTP_PASSWORD`
  - `SMTP_FROM_ADDRESS`
  - `SMTP_TO_ADDRESS`

- **`.env.research`** — LLM API keys used during research only:
  - `OPENAI_API_KEY`
  - `GOOGLE_GEMINI_API_KEY`
  - `ANTHROPIC_API_KEY` (if used)

Both files have `.example` counterparts in the repo root. Real
values never commit. `.gitignore` blocks `.env` and `.env.*` but
permits `.env.example` and `.env.research.example`.

### Backtest engine

- **Allowed options:** Nautilus Trader OR VectorBT Pro.
- **Selection point:** Phase 1, in an ADR.
- **Prohibited:** building a backtest engine from scratch, unless
  an ADR demonstrates that both options fail to meet requirements.

### Observability

- **Metrics collection:** Prometheus.
- **Dashboards:** Grafana.
- **Logs:** structured (JSON) to stdout, shipped to a log store to
  be selected in Phase 3 ADR.
- **Equivalent substitution:** permitted only with an ADR
  documenting why Prometheus + Grafana is inadequate.

### Local control web app

- **Framework:** FastAPI for the HTTP layer, plus HTMX OR a minimal
  single-page React application for interactivity.
- **Selection point:** Phase 3, in an ADR.
- **Binding:** localhost or local private network only. Never
  exposed to the public internet.
- **Default mode:** read-only.
- **Write operations:** opt-in via config flag (off by default), and
  even when on, the app produces proposed diffs — it does NOT mutate
  live config directly. Operator commits the diff, then config
  reload applies it.
- **Forbidden frameworks:** Electron, Tauri, any native desktop or
  mobile framework, any cloud-hosted control plane.

### Risk-module pinned thresholds

These are the default numeric thresholds. They are configurable in
`config/risk/` but the defaults here reflect current design intent.
All are enforced at the risk-module boundary per Principle I of the
constitution.

- Max risk per trade: 1% of equity.
- Max gross exposure: 100% of equity.
- Max net exposure: 100% of equity.
- Max leverage: 1.0× (no leverage by default).
- Max single-symbol concentration: 20% of equity.
- Max sector concentration (if sector classification is used):
  40% of equity.
- Max open positions: 10.
- Max daily loss: 3% of equity — halt new trades, allow exits.
- Max weekly loss: 6% of equity — halt all trading for the week.
- Max monthly drawdown: 10% — halt and require operator
  intervention.
- Max drawdown from high-water mark (live hard halt): 20% — kill
  switch, full operator intervention required before resume.
- Backtest-acceptability max drawdown ceiling (Gate 1): 15%. A
  strategy whose honest backtest shows worst-case drawdown above
  15% is REJECTED at Gate 1. This leaves a 5-percentage-point
  buffer before the 20% live halt.
- Design-target max drawdown (Phase 1 strategy-selection criterion):
  10%. Strategy selection prefers strategies whose backtest DD is
  at or below 10%.
- Liquidity filter: 30-day ADV ≥ 1,000,000 shares.
- Price floor: last trade price ≥ $5.00.
- Stale-data stop: > 60 seconds during regular market hours
  (configurable; default tuned to Alpaca IEX free tier).
- Stale-state stop: reconciliation > 5 minutes old.
- Manual kill switch: Telegram command with 2-step confirmation
  using a challenge code.
- Automated kill switch triggers: P1 breaches, unrecoverable state
  mismatches, repeated order rejections, broker outage,
  intraday-margin-policy-unreachable.

### Data module pinned requirements

- **Corporate actions:** the data module MUST handle stock splits,
  reverse splits, dividends (cash and stock), mergers, spin-offs,
  ticker changes, and delistings. Historical backtest data MUST be
  split-adjusted and dividend-adjusted.
- **Paper-mode dividend caveat:** Alpaca paper does NOT simulate
  dividends (source: `https://docs.alpaca.markets/docs/paper-trading`).
  Paper-mode P&L MUST be reconciled against a dividend-adjusted
  benchmark during Gate 3 evaluation.
- **Paper-mode fill realism caveat:** Alpaca paper fills orders at
  NBBO price but does NOT check NBBO quantity (source: same).
  This means orders larger than actual market liquidity can appear
  to fill in paper, and partial fills occur only 10% of the time
  randomly. Gate 3 MUST include a replay-simulator cross-check
  that injects quantity-aware slippage; if paper slippage and
  replay slippage diverge by more than 2×, Gate 3 is NOT passed.
- **Paper-mode intraday-margin caveat:** Alpaca paper still
  simulates the legacy PDT check (rejecting 4th day trade within 5
  business days if net worth < $25k) as of 2026-04-17. The live
  environment no longer has this rule after the 2026-04-14 SEC
  approval of FINRA's PDT elimination (SR-FINRA-2025-017, SEC
  Release No. 34-104572), but has new intraday-margin rules under
  amended Rule 4210. The bot's risk module MUST handle both the
  legacy PDT-rejection response (paper) and the new intraday-margin-
  rejection response (live), with a fail-closed path if policy
  cannot be retrieved.
- **Wash-sale handling:** out of scope (operator is not a US tax
  resident). Per-trade records MUST be emitted in a format suitable
  for German tax reporting.

---

## Sourced external claims

All externally-verifiable technical facts in this document trace to:

- **Spec Kit constitution path:** `.specify/memory/constitution.md`.
  Source: Spec Kit source code
  (`src/specify_cli/__init__.py` lines 1035-1068, retrieved
  2026-04-17 via `https://deepwiki.com/github/spec-kit/4.1-specify-init`):
  "Copies constitution-template.md to
  `.specify/memory/constitution.md`." Also confirmed by Spec Kit
  documentation and the `/speckit.constitution` command reference.
- Alpaca paper trading documentation:
  `https://docs.alpaca.markets/docs/paper-trading`, retrieved
  2026-04-17. Source for: $100k paper default, PDT simulation in
  paper, no-dividend-simulation, quantity-unchecked NBBO fills,
  random 10% partial fills, paper endpoint URL.
- FINRA PDT elimination:
  `https://www.federalregister.gov/documents/2026/01/14/2026-00519/`
  for the filing; SEC approval confirmed 2026-04-14 via multiple
  sources including FINRA's own notice. Source for: PDT elimination,
  amended Rule 4210, intraday margin framework.
- Alpaca country availability: operator confirmation 2026-04-17
  that Germany is supported. Primary source per Alpaca support is
  to contact `[email protected]` for a specific country;
  operator has done this.

Claims in this document that are NOT yet sourced are tagged
`[UNVERIFIED]` and logged in `docs/handover/UNVERIFIED_CLAIMS.md`.
There should be none in this file; every factual claim above has a
source.
