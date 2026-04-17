---
id: BRIEF-0001
title: Project brief
version: 3.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: BRIEF-0001@2.2.1
superseded_by: null
author_session: SESS-0000-00-00-000
---

# Project Brief — TradingX

**Purpose of this document.** This is the tech-agnostic source material
the coder AI feeds to `/speckit.specify` during Phase 1 of the project
to generate the initial formal specification. It describes WHAT the bot
is and WHY, in domain terms. It does NOT pin specific libraries,
frameworks, or services — those live in `implementation_constraints.md`,
a separate document that feeds `/speckit.plan`.

This split exists to satisfy Principle IX (Specification Separation) of
the constitution. The split was introduced in v3.0.0 after external
review identified that the earlier combined brief contaminated the
would-be spec with implementation details.

**Authority hierarchy.** When anything in this brief conflicts with
`.specify/memory/constitution.md`, the constitution wins. When anything in
`implementation_constraints.md` conflicts with this brief, the
constitution-mandated pinned choices in the constraints file win on
technical matters; this brief wins on product intent.

---

## What is being built

One autonomous AI-assisted trading bot that grows an allocated capital
budget over time through disciplined, systematic, benchmark-aware
trading.

The bot is a single system that matures through sequential stages:

- **Stage 1:** Paper US equity trading against a large-cap benchmark.
- **Stage 2:** Live US equity trading with capped capital.
- **Stage 3 (future):** Add isolated crypto strategy.
- **Stage 4 (possibly never):** Multi-strategy coordination.

All current work is **Stage 1**. Stage 2 requires Gate 4 sign-off.
Stage 3 requires constitution amendment. Stage 4 is out of scope.

There is no "god mode," no unrestricted multi-market mode, and no plan
to add one.

---

## Why it exists

The operator wants a system that:

1. **Aggressively pursues risk-adjusted outperformance** versus a
   large-cap US equity benchmark. The bot's purpose is to make money,
   and to make meaningfully more of it than passive holding would.
   The target is real outperformance, not a close finish. Hitting
   Gate 1's minimum is the floor, not the ceiling — better is better.

2. **Measures success honestly on a risk-adjusted basis** — Sharpe
   ratio, Sortino, Calmar — not raw return. A bot that returns more
   than the benchmark with materially higher volatility has not
   beaten it; it has just taken more risk. The capital-preservation
   requirements below are what make ambitious returns safe to pursue;
   they are not a substitute for ambition.

3. **Preserves capital through known-worst-case events.** Growth
   compounds; losses compound against you twice — once as the loss
   itself and again as the drawdown you have to climb out of before
   growth can resume. A 50% drawdown requires a 100% gain to recover.
   The hard limits (live hard-halt, daily/weekly/monthly loss caps,
   concentration limits, liquidity floors) are not conservatism —
   they are the only reason aggressive return targets are survivable
   across regimes.

4. **Trades without requiring the operator to monitor markets**, while
   keeping the operator informed and in control of all material
   decisions. The bot should run during regular US market hours,
   handle its own decision loop, and escalate only what genuinely
   needs human input.

5. **Is safe by default** — live trading cannot happen until every
   acceptance gate has passed. This is not caution for its own sake;
   it is the mechanism that lets the operator commit real capital
   without gambling.

6. **Is honest about what it knows and doesn't know** — no claimed
   edge without evidence; no hidden complexity; no hallucinated
   numbers. A bot that pretends to know what it doesn't is the
   fastest path to blowing up an account.

The design philosophy: **be aggressive where the data supports it; be
unforgiving where the data does not.** Every return-seeking choice
must be testable; every risk control must be non-negotiable.

---

## Who operates it

The operator is a private individual with a technical program
management background but limited specialist experience in quantitative
finance, ML research, or market microstructure. The operator is the
executive stakeholder and decision-maker of last resort: they set
goals, approve phase advancement, answer questions only they can
answer (capital size, risk appetite, regulatory choices), and sign off
on live enablement.

The operator is **not** expected to:

- Catch the coder AI's mistakes through code review.
- Make low-level technical choices (library selection, module
  boundaries, test structures).
- Evaluate strategies on mathematical merit alone.

The operator **is** expected to:

- Answer Stop-and-Ask questions within reasonable time.
- Approve or reject ADRs that escalate to them.
- Fund and staff the project (tooling, data subscriptions if needed,
  capital).
- Make the go/no-go call on live enablement.

---

## Success definition

The bot has succeeded when:

1. It has completed a statistically meaningful paper-trading period
   (minimum 180 calendar days OR 100 closed trades, whichever first)
   without bug-induced incidents.
2. Its realized risk-adjusted performance meaningfully exceeds a
   passive large-cap benchmark over the same period, with honest
   cost accounting.
3. Its backtested performance survives adversarial checks
   (out-of-sample, walk-forward, 2× cost sensitivity, ±20% parameter
   perturbation).
4. Its live-halt threshold has never fired during paper trading, and
   its interim halts (daily/weekly/monthly) have fired no more
   frequently than backtest statistics predict.
5. The operator has enough evidence in hand to decide whether to
   deploy real capital with confidence, or to return to the design
   phase with known gaps.

Success is not defined as beating the benchmark by a specific
percentage. Success is defined as being in a state where the
operator's decision about deploying real capital is well-informed.

---

## Open choices (for Phase 1 evaluation and decision)

These are the actual decisions the coder AI must make during Phase 1,
documented in ADRs with evidence. Pinned technical choices (language,
broker, libraries, frameworks) live in `implementation_constraints.md`;
they are not open.

### Strategy candidates

Tiered for focus. The MANDATORY tier is required; the OPTIONAL tier may
be evaluated once the walking skeleton and mandatory baselines are
validated.

**Mandatory candidates (must evaluate):**

1. **Trend following / time-series momentum** on a small basket of
   liquid US equity ETFs or large-cap stocks.
2. **Volatility-targeted allocation** between the benchmark and cash
   (or between the benchmark and a defensive proxy).
3. **Simple mean reversion** on liquid large-caps (e.g., 5-day reversal
   on overreactions).

These three are required because they are simple, robust, and well-
documented in academic literature. They serve both as real strategy
candidates and as baselines against which fancier candidates must
demonstrate edge.

**Optional candidates (may evaluate after mandatory tier):**

4. **Cross-sectional momentum** — rank S&P 500 constituents by
   trailing return, hold top-N, rebalance periodically.
5. **Regime-aware hybrid (switching type)** — one strategy active
   in trending regimes, a different strategy active in mean-
   reverting regimes, with explicit regime detection.
6. **Multi-signal hybrid (composite type)** — combine multiple
   independent signals (momentum + low-volatility + quality + value)
   into a composite score, weighted by historical predictive power.
7. **Sentiment-feature-assisted strategy** — a price-based primary
   strategy enhanced by deterministic sentiment features computed
   once from text sources and used as inputs. Allowed sentiment
   sources: earnings-call tone, analyst revision sentiment, news
   volume indicators, and social-media sentiment computed by a
   deterministic classifier (NOT by LLM prompting).
8. **Congressional trade disclosures as a signal.** A legitimate
   candidate, evaluated under the same adversarial criteria as any
   other. The operator has no prior preference here; the candidate
   must win on its merits against the mandatory baselines.

The AI MAY propose additional candidates it discovers during research,
with an ADR justifying the addition. The AI MUST NOT evaluate
strategies that require latency advantages, options/futures/crypto,
continuous two-sided quoting, or LLM-in-the-live-loop decisioning.

### Adversarial evaluation methodology

Every candidate — mandatory or optional — MUST be evaluated against
the **same** adversarial checklist, documented in an ADR template
(`docs/adrs/templates/strategy_evaluation.md`) created in Phase 1.
The checklist at minimum includes:

- Profitability before AND after realistic costs.
- Out-of-sample performance across ≥ 3 years.
- Walk-forward performance with no single rolling window failing.
- Parameter sensitivity (±20% perturbation).
- Cost sensitivity (slippage × 2, fees × 2).
- Outlier sensitivity (exclude top-3 contributors, confirm signal
  broadness).
- Regime behavior (bull/bear/high-vol/low-vol sub-windows).
- Regulatory-risk simulation (signal disappearing at plausible
  future date, for signals with regulatory dependencies).
- Independence check (correlation with simple buy-and-hold of the
  benchmark; a signal highly correlated with the benchmark has no
  independent information).
- Live-tracker sanity check (if publicly-traded products that
  systematize the signal exist, compare the proposed strategy to
  their realized live performance — not just paper backtests).

The checklist is stored as a generic ADR template so NO candidate is
privileged. Congressional trades uses the same template as trend
following; sentiment uses the same template as mean reversion. This
was introduced after external review identified that detailed
adversarial checks documented only under one candidate created
confirmation bias.

---

## Explicit non-goals

The following are explicitly out of scope and MUST NOT be proposed:

- High-frequency trading, sub-minute strategies, or any design that
  competes on latency.
- Market-making (continuous two-sided quoting).
- Co-location, proximity hosting, direct-market-access infrastructure.
- Cryptocurrency trading (deferred to Stage 3, requires constitution
  amendment).
- Options, futures, or derivatives (deferred).
- Forex trading.
- Extended-hours trading (pre-market, after-hours) — Stage 1 and
  Stage 2 are regular-hours only.
- Native mobile applications.
- Native desktop applications.
- Cloud-hosted control planes or public web UIs.
- **LLM-in-the-live-loop decision-making** — calling an LLM API from
  any code path that runs during paper or live trading to analyze
  news/social media/market data and decide trades. This is prohibited
  because it is unauditable, non-deterministic, and hallucination-prone.
  Note: deterministic sentiment features computed once from text and
  used as strategy inputs are NOT prohibited.
- "AI signal" or "AI insights" commercial subscriptions that purport
  to tell the bot what to trade.
- Trading symbols below the liquidity floor (30-day ADV < 1M shares)
  or price floor ($5).
- Anything that requires the operator to watch markets in real time.

---

## Capabilities to implement (Stage 1)

At the capability level (the coder AI decides the technical
implementation in Phase 2), the bot must have:

1. **Capital and policy module** — starting capital, benchmark,
   leverage policy, risk budget, allocation constraints, operating
   mode.

2. **Data module** — ingest historical and real-time market data from
   the broker's data API; validate freshness, completeness, schema;
   detect anomalies; handle corporate actions (splits, dividends,
   mergers, delistings); block trading on integrity failures;
   enforce the liquidity and price universe at intake.

3. **Feature and signal module** — compute indicators, features, and
   any chosen model outputs; preserve feature timing (no lookahead);
   expose explainable intermediate outputs.

4. **Strategy module** — turn features into trade intent (enter /
   exit / hold / reduce / skip); config-driven and testable.

5. **Sizing module** — convert opportunity and risk into position
   size; respect capital, leverage, and concentration rules.

6. **Risk module** — hard pre-trade and post-trade checks per the
   constitution's Principle I; daily, weekly, monthly loss
   enforcement; drawdown controls; concentration limits; liquidity
   and price floors; intraday-margin check; stale-data and stale-
   state stops; kill switch.

7. **Execution module** — submit orders via the broker adapter;
   paper execution only in Stage 1; live adapter interface exists
   but is disabled at all four safety layers until Gate 4; handle
   rejected, cancelled, partial fills; idempotent order submission;
   duplicate prevention.

8. **Portfolio and state module** — track cash, equity, positions,
   open orders, fills, exposure; persist state atomically; recover
   on restart; reconcile with broker.

9. **Monitoring and diagnostics** — structured logs, metrics,
   benchmark-relative reporting.

10. **Operator channels** — real-time primary channel, non-urgent
    secondary channel, emergency fallback channel.

11. **Local control web app** — read-only by default; supports
    configuration viewing, trade history, handover file inspection,
    and composing config changes for operator commit.

12. **Bot controller** — orchestrates the decision loop, manages
    scheduling, enforces order of operations, manages startup and
    shutdown safety.

---

## Execution modes

Four strictly separated modes. The coder AI implements all four in
Phase 7, with live disabled at every layer:

- **Backtest mode:** historical data only; no external order
  submission possible by construction.
- **Dry-run mode:** live data, full logic, no orders placed.
- **Paper trading mode:** live data, orders routed to broker's paper
  environment.
- **Live trading mode:** live data, real orders, real capital.
  DISABLED by default at all four safety layers until Gate 4.

---

## Risk requirements (capability level)

The risk engine enforces hard limits (not advisory). Specific numeric
thresholds and their rationale live in the constitution's Capital
model subsection. The capability-level requirements are:

- Pre-trade constraint enforcement per constitution Principle I
  (liquidity, price, concentration, intraday-margin, stale-data,
  stale-state, kill-switch, live-mode defense-in-depth).
- Drawdown-based halts at three scopes: daily, weekly, monthly, and
  high-water-mark-relative.
- Manual kill switch via operator channel with 2-step confirmation.
- Automated kill switch on P1 breaches, unrecoverable state
  mismatches, repeated order rejections, or broker outage.
- Fail-closed behavior: any check that cannot complete (e.g.,
  broker margin policy unreachable) MUST block the trade, not
  permit it.

---

## Required metrics (Stage 1 reporting)

Every validation report must include, at minimum: total return, CAGR,
annualized volatility, Sharpe, Sortino, Calmar, max drawdown, drawdown
duration, turnover, hit rate, average win, average loss, profit
factor, exposure profile, net return after costs, benchmark-relative
return, information ratio, stability across sub-windows, out-of-sample
performance, walk-forward performance, regime-by-regime behavior.

Plus sensitivity tests: slippage (0.5×, 1×, 2×, 5×), fees (same),
missing/delayed data, parameter perturbation (±20%).

Benchmark comparison MUST use dividend-adjusted benchmark returns
over the identical window with identical cost assumptions, to avoid
misleading point-to-point comparisons.

---

## What the operator expects in communication

- Direct, clear conclusions over hedged ones. "I recommend X because
  Y" beats "X might be worth considering."
- Plain-language translation of numbers into capital outcomes. Not
  "Sharpe 1.2" alone but "on $100k, this means roughly $X expected
  per year with a realistic worst case of losing $Y temporarily."
- Short and dense over long and ornamental.
- Cite sources for numeric, regulatory, or API claims. Unsourced or
  unverified claims go in `docs/handover/UNVERIFIED_CLAIMS.md` and
  are reviewed before phase advance.
- Escalate Stop-and-Ask questions with a recommendation, not a menu
  of options without guidance.
- Honest about self-review limitations. The coder AI's own check of
  its own work is not evidence; external or independent review is.

---

## Development phases

Phase 0 through Phase 9 as defined in the constitution, applied to
Stage 1 scope:

- **Phase 0:** repo inspection, scaffolding, pinned-choice ADRs,
  AND a working end-to-end paper-trading pipeline (walking skeleton).
  Ends with Gate 0 AND Gate 0.5 passed.
- **Phase 1:** objective, benchmark, strategy selection (evaluate
  mandatory candidates; evaluate optional candidates if time
  permits; recommend one; write ADRs using the generic adversarial
  template).
- **Phase 2:** bot architecture (module boundaries, data model,
  capital model, risk model, execution model, monitoring model).
- **Phase 3:** full repo structure, packaging, quality tooling, test
  scaffolding, Docker, CI, config skeletons, local web app skeleton
  (read-only).
- **Phase 4:** data and feature foundation (broker data access,
  validation, corporate-action handling, feature pipeline).
- **Phase 5:** backtest foundation (capital-aware, cost-aware,
  benchmark-comparative).
- **Phase 6:** strategy and sizing implementation.
- **Phase 7:** hard risk engine, paper execution, live interface
  (disabled), reconciliation, order tracking.
- **Phase 8:** state persistence, restart recovery, monitoring,
  alerting, operator channels — including emergency channel
  round-trip test.
- **Phase 9:** validation against gates, readiness docs, live
  enablement checklist (live stays disabled).

Architecture details are NOT specified here. The coder AI decides
them in Phase 2 within the constitution's constraints, documented in
ADRs.
