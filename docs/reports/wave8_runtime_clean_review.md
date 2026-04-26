# Wave 8 Runtime — Clean Adversarial Review (post-Defect 2)

**Date:** 2026-04-26
**Reviewer:** Adversarial review committee, second pass
**Scope:** Wave 8 live-probe runtime route enforcement after the
`adversarial_fixup_Defect_2` commit lands.

## Summary

Wave 8 runtime route enforcement now passes adversarial review. The
production builders no longer default to the legacy non-authority
bypass, the OrderRouteAuthorityGuard is wired with required_state
derived from broker_mode, and the historical paper roundtrip path is
isolated behind a clearly-labeled legacy module.

## Findings remediated

### F8.1 — `legacy_paper_non_authority=True` was the default in production

**Original:** `build_default_paper_trading_controller` and
`build_default_trading_loop_controller` instantiated
`AlpacaPaperExecutionGateway` with `legacy_paper_non_authority=True`,
silently bypassing the V5 OrderRouteAuthorityGuard for every paper
order.

**Fix:** The flag has been removed from both production builders. The
gateways are now wired with `OrderRouteAuthorityGuard(required_state=
_required_state_for_broker_mode(broker_mode))` and a decision provider
sourced from `config.runtime.artifact_root / "promotion"`.

`grep -c "legacy_paper_non_authority=True" src/tradingx/*.py` returns 1,
and that one site is in `src/tradingx/legacy_paper_roundtrip.py`,
which is clearly labeled in its module docstring.

### F8.2 — Supervisor operator class also set the legacy flag

**Original:** `AlpacaPaperBrokerOperator` in `supervisor.py` constructed
its execution gateway with the legacy flag, so any operator-driven
paper trade also bypassed V5.

**Fix:** `AlpacaPaperBrokerOperator.__init__` now accepts an optional
`authority_guard` and `strategy_id`. Without an explicit guard the
gateway is fail-closed.

### F8.3 — No deferred runtime red tests

**Original:** Two runtime red tests were marked deferred during the
Wave 8 milestone:
  - `test_route_authority_token_at_risk_execution_boundary`
  - `test_direct_trading_client_route_blocked_by_default`

**Fix:** Both tests now exist under
`tests/integration/`. The first proves a guard with a stale decision
(capped at PAPER_TRADING with two real-world blockers) refuses a
production live-order route. The second proves a direct gateway
construction without a guard and without the legacy flag refuses every
order-submission method.

## Residual risks

- The default decision provider reads the promotion bundle from
  `config.runtime.artifact_root / "promotion"`. If that directory does
  not exist the guard's `decision_provider` will return
  `_blocked_decision(authority_artifact_invalid)` — fail-closed.
- The `LegacyPaperRoundtripController` subclass exists for the historic
  smoke test only. New runtime code paths must NOT instantiate it.

## Verdict

**Wave 8 runtime is clean.** No new defects raised.
