---
id: DESIGN-0013
title: Tranche 1.2 market-state features design
version: 0.1.0
status: draft
created: 2026-04-21
last_amended: 2026-04-21
supersedes: null
superseded_by: null
author_session: claude-opus-4.7-2026-04-21
---

# DESIGN-0013: Tranche 1.2 market-state features design

## Status

Draft on 2026-04-21. Second sub-tranche under
[BRIEF-0002](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
tranche-1 plan. Pending Hussam approval.

## Purpose

Ship the market-state feature layer that sleeves consume in 1.3.
Scope:

1. HAR-RV (Heterogeneous Autoregressive Realized Volatility, Corsi
   2009) as a new forecast method in `features/volatility.py`.
2. Rule-based regime composite — a transparent, auditable classifier
   that emits a `RegimeSnapshot` built from 200-day SMA position,
   VIX level (when available), and Treasury yield-curve shape.
3. Empirical vol-estimator comparison across `realized`, `ewma`,
   `garch`, and `har_rv` on in-repo bars, with the winner recorded.
4. **Trend-family** candidate-default retune in `strategy.py` if
   the trend-sleeve empirical comparison justifies changing the
   trend-family default `forecast_method`. Vol-target and
   mean-reversion defaults stay put pending per-family comparison
   (deferred).

No sleeve logic, no portfolio construction, no runtime wiring — the
features are produced; consumption is 1.3's job.

## Scope

### In scope

- HAR-RV estimator wired into
  [features/volatility.py](/src/tradingx/features/volatility.py) as
  `forecast_method="har_rv"`.
- Treasury 2-year and 10-year yields fetchable via a small extension
  to [risk_free.py](/src/tradingx/risk_free.py) (DGS2, DGS10).
- `features/regime.py` (new module): pure-math classifier producing
  a `RegimeSnapshot` dataclass.
- `scripts/compare_vol_forecasts.py` (already exists, will be
  extended) runs the empirical comparison across all four methods
  and records the winner.
- Candidate-default `forecast_method` tune in
  [strategy.py:34](/src/tradingx/strategy.py:34) if the comparison
  winner differs from the current default (`garch`).

### Explicitly out of scope

- **Sleeve logic** (trend, vol-managed beta). Ships in 1.3.
- **Regime-gated trading** (using the regime composite to skip
  trades). Ships in 1.3 as part of sleeve failure-rule design.
- **HMM or Markov-switching regime models.** Ruled out in SPEC-0013
  §4.A; rule-based only at this universe size.
- **Implied-vol overlay.** Optional per SPEC-0013 §4.A bullet; not
  in this tranche. Returns in tranche 2+ when options data is
  accessible.
- **Live VIX streaming.** Daily closes only for this tranche; any
  intraday regime signal is later-tranche work.

## Prerequisites

- `main` at or beyond the 1.1 validation-infrastructure merge (so
  the validation-stack comparison in W4 has honest cost-aware
  candidate metrics to read).
- Existing primitives already present:
  - `features/volatility.py` with `realized`/`ewma`/`garch`.
  - `risk_free.py` DGS3MO fetcher pattern.
  - `AlpacaMarketDataGateway.get_daily_close_series` for SPY closes
    feeding the SMA-200 indicator.
- No Hussam decisions required for 1.2. D1–D4 remain gated to 1.3
  per BRIEF-0002.

## Architecture overview

### New modules

1. **`src/tradingx/features/regime.py`** — pure-math regime
   classifier. Consumes SPY daily closes, optional VIX closes, and
   optional 2s10s yield spread. Returns `RegimeSnapshot`. No I/O, no
   side effects. Tests mock inputs.

### New dataclass

2. **`RegimeSnapshot`** in `src/tradingx/types.py` — the per-day
   regime classifier output.

### Modifications

3. **`src/tradingx/features/volatility.py`** — add HAR-RV estimator
   branch to `forecast_volatility` dispatch; add `_har_rv_vol`
   helper.
4. **`src/tradingx/risk_free.py`** — parameterize the existing FRED
   fetcher so it can also fetch `DGS2` and `DGS10`. Add a small
   helper `load_treasury_yield_cache` to read individual series.
5. **`scripts/compare_vol_forecasts.py`** — extend to cover all
   four forecast methods, record the winner per a well-defined
   accuracy metric, and emit a short markdown report.
6. **`src/tradingx/strategy.py`** — candidate-registry default
   `forecast_method` updated based on W4's empirical winner. This
   change is conditional on the winner; if `garch` wins, no code
   change here.

## Work items

### W1 — HAR-RV estimator

**Contract:**

```python
# Extension to features/volatility.py

def forecast_volatility(
    returns: pd.Series,
    *,
    lookback_days: int,
    forecast_method: str = "realized",
    ewma_lambda: float = 0.94,
    garch_train_size: int = 252,
    har_rv_components: tuple[int, int, int] = (1, 5, 22),
) -> pd.Series:
    # ...existing realized/ewma/garch branches unchanged...
    if forecast_method == "har_rv":
        return _har_rv_vol(
            returns, components=har_rv_components, lookback_days=lookback_days
        )
    # ...error branch unchanged...


def _har_rv_vol(
    returns: pd.Series,
    *,
    components: tuple[int, int, int],
    lookback_days: int,
) -> pd.Series:
    """HAR-RV forecast: linear regression on daily, weekly, monthly
    realized volatility components, refit incrementally as the window
    grows. Returns the one-step-ahead forecast of annualized vol.
    """
    ...
```

**Design rationale.** Corsi (2009) models realized volatility
`RV_t+1` as a linear combination of `RV_t` (daily),
`mean(RV_{t-5:t})` (weekly), `mean(RV_{t-22:t})` (monthly). We use
`components=(1, 5, 22)` as the default. Fitting is OLS; minimal
dependency footprint (no `arch` import needed for this estimator).

**Acceptance.** `forecast_volatility(returns, ..., forecast_method="har_rv")`
returns a `pd.Series` aligned with the input index, with the first
`max(components) + lookback_days` entries as `NaN` (no forecast
until enough history exists).

### W2 — Treasury 2s10s fetcher

**Contract:**

```python
# Extension to risk_free.py

DEFAULT_TREASURY_YIELD_CACHE_PATH = Path("data/reference/treasury_yields_daily.csv")
TREASURY_SERIES_CODES = ("DGS2", "DGS10")


def refresh_treasury_yield_cache(
    cache_path: Path,
    *,
    start_date: date,
    end_date: date,
    now_utc: datetime,
    fetcher: RiskFreeFetcher | None = None,
) -> Path:
    """Fetch DGS2 and DGS10 daily yields, normalize, and write a
    single CSV cache. Pattern mirrors refresh_risk_free_cache but
    returns two series side-by-side.
    """


def load_treasury_yield_cache(cache_path: Path) -> pd.DataFrame:
    """Columns: date, dgs2, dgs10, spread_2s10s_bps."""


def yield_curve_spread_for_date(cache_path: Path, *, as_of_date: date) -> Decimal:
    """Return 2s10s spread in bps for the most recent date <= as_of_date."""
```

**Design rationale.** The existing `_normalize_risk_free_frame` logic
already handles FRED CSV. We extract and generalize it so DGS2 and
DGS10 can be fetched via the same path, then compute the spread
(`dgs10 - dgs2`) at load time.

**Acceptance.** `yield_curve_spread_for_date` returns a Decimal in
bps for any cached date. Negative = inverted (classic recession
warning signal). Positive = normal curve.

### W3 — Rule-based regime composite

**Contract:**

```python
# New: src/tradingx/features/regime.py

from datetime import date
from decimal import Decimal

from tradingx.types import RegimeSnapshot


def classify_regime(
    *,
    observation_date: date,
    spy_close: Decimal,
    spy_sma_200: Decimal,
    vix_close: Decimal | None,
    yield_curve_spread_bps: Decimal | None,
    vix_elevated_threshold: Decimal = Decimal("25"),
    vix_stress_threshold: Decimal = Decimal("35"),
) -> RegimeSnapshot:
    """Produce a deterministic RegimeSnapshot from three sub-indicators.

    Sub-indicators (each returns a flag; None-valued inputs are skipped):
    - above_sma_200: spy_close > spy_sma_200
    - vix_elevated: vix_close >= vix_elevated_threshold
    - vix_stressed: vix_close >= vix_stress_threshold
    - yield_curve_inverted: yield_curve_spread_bps < 0

    Aggregate regime label rules (evaluated in order):
    1. If vix_stressed OR (yield_curve_inverted AND NOT above_sma_200):
       regime = "stressed"
    2. Else if NOT above_sma_200 OR vix_elevated:
       regime = "risk_off"
    3. Else if above_sma_200 AND NOT vix_elevated:
       regime = "risk_on"
    4. Else:
       regime = "neutral"

    When an input is None, the corresponding sub-indicator is
    reported as None on the snapshot and treated as "not fired" in
    rule evaluation.
    """
```

**`RegimeSnapshot` fields** (in `src/tradingx/types.py`):

- `observation_date: date`
- `regime: str` — one of `"risk_on"`, `"neutral"`, `"risk_off"`,
  `"stressed"`
- `above_sma_200: bool | None`
- `vix_elevated: bool | None`
- `vix_stressed: bool | None`
- `yield_curve_inverted: bool | None`
- `spy_close: Decimal`
- `spy_sma_200: Decimal`
- `vix_close: Decimal | None`
- `yield_curve_spread_bps: Decimal | None`

**Design rationale.** Transparency matters more than sophistication
at this universe size. A sleeve consumer in 1.3 should be able to
read `snapshot.regime == "stressed"` to throttle exposure and also
be able to inspect the sub-indicators to explain *why* the regime
classified that way. No HMMs, no tuning of thresholds per regime —
threshold constants are dataclass arguments with literature-backed
defaults (VIX 25 = elevated, 35 = stress regime).

**Acceptance.** `classify_regime` is pure: same inputs always
produce same output. Handles missing VIX and missing yield-curve
gracefully (None-valued inputs don't crash; snapshot still emits a
regime based on the remaining sub-indicators).

### W4 — Empirical vol-estimator comparison + trend-family candidate retune

**Context.** `scripts/compare_vol_forecasts.py` already exists (see
the checkpoint commit `92375a8` from the benchmark-stack branch) and
compares forecast methods under a **trend-sleeve** configuration. The
`forecast_method` field is consumed by each sleeve family
differently inside
[portfolio_construction.py:395](/src/tradingx/portfolio_construction.py:395):
trend and vol-target use the forecast for position sizing; mean
reversion uses it for z-score normalization. Evidence gathered under
the trend harness is not representative of how the vol-target or
mean-reversion sleeves consume the forecast.

**Scope correction — per-family retune limited to the family actually
evaluated.** This tranche runs the comparison under the existing
trend-sleeve harness only. The automatic default-retune action is
therefore **limited to the `trend-following-v1` candidate**. The
`vol-target-v1` and `mean-reversion-v1` defaults stay at their
current values regardless of the trend-sleeve winner. Running a
per-family comparison (reshaping the harness to a vol-target payoff
and a mean-reversion payoff) is out of scope for 1.2 and belongs to
tranche-2 hardening or a dedicated research lane.

**Metric correction — realized volatility, not realized variance.**
The existing script at
[compare_vol_forecasts.py:200](/scripts/compare_vol_forecasts.py:200)
scores forecasts against one-day realized variance (`pct_change()
** 2`). That target is dimensionally wrong: `forecast_volatility`
produces annualized *volatility* (σ × √252), not variance. The
script must replace its variance target with a realized-vol target
aligned to the forecast horizon:

- **Forecast:** `forecast_volatility(...)[t]` — annualized vol at time `t`.
- **Target:** annualized realized vol over the forward window
  `returns[t + 1 : t + 1 + lookback_days]`, computed as
  `std(returns) * sqrt(252)`.
- **Loss:** `(forecast[t] - realized_vol_forward[t]) ** 2`,
  averaged across valid `t` per symbol.

This is one-step-ahead MSFE in annualized volatility units.

**Behavior change:**

1. **Replace the loss target** in
   [compare_vol_forecasts.py:200](/scripts/compare_vol_forecasts.py:200)
   with the one-step-ahead realized-vol target described above.
2. Extend the script to evaluate all four methods: `realized`,
   `ewma`, `garch`, `har_rv`.
3. Compute MSFE per-symbol across the canonical 8-ETF universe;
   aggregate by mean across symbols.
4. Emit a short markdown report at
   `docs/research/vol_estimator_comparison_2026-04-21.md` with:
   - Per-symbol MSFE per method (in annualized-vol units)
   - Aggregate winner across symbols under the trend-sleeve harness
   - Recommended `forecast_method` **for the trend family only**
   - Explicit note that vol-target and mean-reversion defaults are
     unchanged pending per-family evaluation
5. If the aggregate winner differs from the current trend-family
   default (`garch`), update **only** the `trend-following-v1`
   candidate entry in
   [strategy.py:34](/src/tradingx/strategy.py:34) to use the
   winning `forecast_method`. Document the trend-family-only scope
   explicitly in the commit message.
6. **Regression test for the target fix.** Add a test asserting
   that the script's loss function rejects variance-unit targets
   and accepts volatility-unit targets — e.g., feeding a known
   constant-vol series produces a near-zero MSFE for the `realized`
   method at its own lookback, and feeding the legacy variance
   target produces a detectably different (larger) MSFE value than
   the corrected volatility target.

**Report location** is under `docs/research/` (not
`docs/superpowers/`) because it's an empirical research artifact,
not a governed design document.

**Acceptance.** The script runs clean on in-repo bars with the
corrected realized-vol target. A markdown report is produced and
committed. If the trend-family winner changed, `trend-following-v1`
is updated in the same commit; `vol-target-v1` and
`mean-reversion-v1` stay at `garch`.

## Testing approach

Standard TDD. Each work item produces unit tests before implementation
code. Integration tests exercise the full HAR-RV → regime
classification → candidate-default path only at the script level.

**Regression coverage:**

- Every existing `forecast_volatility` test must still pass.
- Existing candidate-registry tests (cardinality, parameter-set
  shape) must still pass. If `forecast_method` changes for any
  candidate, the expected-default fixtures update in the same
  commit.

## Acceptance criteria

Sub-tranche 1.2 is complete when:

1. `forecast_volatility(..., forecast_method="har_rv")` returns a
   valid forecast series.
2. `refresh_treasury_yield_cache` and `load_treasury_yield_cache`
   round-trip DGS2 + DGS10 data through a single CSV cache.
3. `classify_regime(...)` produces deterministic `RegimeSnapshot`
   objects for both full-input and partial-input cases.
4. The empirical comparison report is committed at
   `docs/research/vol_estimator_comparison_2026-04-21.md`, with a
   clearly stated winner per the MSFE criterion.
5. If the trend-sleeve winner differs from `garch`, **only the
   `trend-following-v1` candidate entry** in `strategy.py` is
   updated. `vol-target-v1` and `mean-reversion-v1` entries remain
   unchanged. All registry tests pass under the new defaults.
6. `uv run pytest -q`, `uv run mypy src/tradingx`, `uv run ruff check`,
   and `python3 scripts/check_index.py` all pass.

## Decisions still open

None block this sub-tranche. D1–D4 from BRIEF-0002 remain gated to
sub-tranche 1.3.

Two implementation-level judgment calls for Codex:

1. **VIX data source.** If Alpaca doesn't provide ^VIX quotes
   cleanly, fall back to a FRED-style fetcher for `VIXCLS` using
   the existing pattern in `risk_free.py`. If neither is reliable,
   ship `classify_regime` with `vix_close=None` paths as the
   primary path for now — the function handles `None` gracefully.
2. **HAR-RV fitting cadence.** Two viable choices:
   (a) one global OLS fit on the full training window; or
   (b) expanding-window refit at each step. The plan proposes (b)
   to avoid look-ahead bias; (a) is acceptable if performance of
   (b) is pathologically slow on the research bars. Flag the
   choice in the commit message.

## Governance impact

- Update `docs/INDEX.md` to register `DESIGN-0013`.
- If W4's empirical comparison changes the `trend-following-v1`
  candidate default, that's a minor strategy-layer change, not an
  architectural one — no ADR needed because
  [ADR-0022](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
  already covers the reframed gate criterion; the choice of vol
  estimator is an implementation detail inside it.
- If W4's comparison recommends a **new** forecast method not
  listed in ADR-0022 (e.g., a HAR-RV-specific parameterization
  that becomes a candidate-family decision), then a small ADR
  follow-on is warranted. BRIEF-0002 can be updated in the same
  session if needed.

## References

### Repo documents

- [BRIEF-0002](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
- [SPEC-0013](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
- [DESIGN-0011](/docs/superpowers/specs/2026-04-21-tranche-1-1-validation-infrastructure-design.md)
- [ADR-0022](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)

### Existing source files

- [src/tradingx/features/volatility.py](/src/tradingx/features/volatility.py) — `realized`/`ewma`/`garch`; HAR-RV extension point
- [src/tradingx/risk_free.py](/src/tradingx/risk_free.py) — FRED
  fetcher pattern to reuse for DGS2/DGS10
- [src/tradingx/strategy.py](/src/tradingx/strategy.py) —
  candidate registry with `forecast_method` defaults
- [src/tradingx/types.py](/src/tradingx/types.py) — location for
  new `RegimeSnapshot` dataclass
- `scripts/compare_vol_forecasts.py` — existing comparison script
  to extend

### External references

- Corsi, F. (2009). "A Simple Approximate Long-Memory Model of
  Realized Volatility." *Journal of Financial Econometrics.*
  https://ideas.repec.org/a/oup/jfinec/v7y2009i2p174-196.html
- Moreira, A., & Muir, T. (2017). "Volatility-Managed Portfolios."
  *Journal of Finance.* (Consumer of HAR-RV-style estimates in
  tranche 1.3.)
- [FRED DGS2](https://fred.stlouisfed.org/series/DGS2) and
  [FRED DGS10](https://fred.stlouisfed.org/series/DGS10) — data
  sources for the yield-curve sub-indicator.
- [FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS) — VIX
  close series (fallback if Alpaca doesn't provide ^VIX).
