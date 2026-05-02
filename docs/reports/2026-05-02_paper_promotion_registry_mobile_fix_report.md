# Paper Promotion, Registry Split, and Mobile Shell Fix Report

Review date: 2026-05-02

Scope: committed branch diff `main...HEAD`. This report excludes unstaged
workspace edits.

## Decisions Implemented

- Strategies may be paper-trading ready immediately for local observation.
- Live trading remains disabled until Gate 4.
- `baseline-long-only-v1` is a reference/runtime baseline, not a mandatory
  evaluated candidate.
- Gate 1 marginal/CPCV scope is the explicit trend/vol two-sleeve pair.
- `mean-reversion-v1` does not receive the marginal contribution criterion until
  a future gate amendment defines a 3+ sleeve-backed marginal model.
- Mobile/narrow Control Center layout must keep the operator canvas visible.

## Verification

- Clean detached worktree `./scripts/validate-fast`: passed. Index validation,
  Ruff, Black, and mypy passed; focused backend tests reported 164 passed and
  12 warnings in 3.14s.
- Clean detached worktree `./scripts/validate`: passed. Index validation,
  Ruff, Black, and mypy passed. Unit/integration coverage reported 1459 passed,
  98 skipped, 18 warnings in 450.46s, with coverage 84.66% against the 80%
  threshold.
- Frontend tests inside `./scripts/validate`: passed with 10 test files and 108
  tests.
- Frontend build inside `./scripts/validate`: passed with the existing
  chunk-size warning; the main JS bundle is 732.57 kB, gzip 212.39 kB.
- Smoke gate inside `./scripts/validate`: 1 skipped because regular US market
  hours were closed.
- Browser desktop screenshot:
  `/Users/ahmedabd/Desktop/AI Projects/TradingX/artifacts/verification/2026-05-02-responsive-shell/tradingx-desktop-1440x900.png`.
- Browser mobile screenshot:
  `/Users/ahmedabd/Desktop/AI Projects/TradingX/artifacts/verification/2026-05-02-responsive-shell/tradingx-mobile-390x844.png`.
- Browser interaction verification: Browser Use in-app browser passed nav
  drawer, operator rail drawer, scrim close, and reachable kill/flatten/resume
  controls. Exact 1440x900 and 390x844 screenshots used Chrome/CDP fallback
  because Browser Use exposed no viewport resizing API in this session;
  Playwright MCP was locked by an existing browser profile.

## Adversarial Questions Answered

- Paper trading is allowed; live trading is still fail-closed.
- Baseline is still available to runtime flows but no longer inflates
  validation evidence counts.
- Gate 1 evidence is scoped to the model the code can actually evaluate.
- Mean reversion receives pass-through Gate 1 criteria where appropriate and
  does not receive the trend/vol marginal contribution criterion.
- Backtest reference generation no longer attempts to simulate candidates with
  no allowed instruments.
- Mobile layout no longer hides the main operator surface behind fixed columns,
  and drawer controls do not occlude `.topStrip`.
