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

- Clean detached worktree `./scripts/validate-fast`: pending rerun after the
  code-review correction commits.
- Clean detached worktree `./scripts/validate`: pending rerun after the
  code-review correction commits.
- `npm --prefix webapp run lint`: previously passed on this branch.
- `npm --prefix webapp test`: previously passed with 10 test files and 108
  tests.
- `npm --prefix webapp run build`: previously passed with the existing
  chunk-size warning.
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
- Mobile layout no longer hides the main operator surface behind fixed columns,
  and drawer controls do not occlude `.topStrip`.
