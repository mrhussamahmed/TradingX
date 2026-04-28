# TradingX Tier 0 Wave 0 As-Is Preservation

Generated: 2026-04-28
Source plan: `docs/superpowers/plans/2026-04-27-tradingx-tier0-decision-and-cleaning-plan.md`
Implementation plan: `docs/implementation/2026-04-27-tradingx-tier0-decision-and-cleaning-implementation-plan.md`

## Immutable Reference

- Git commit: `b0154070c802feeb99a22d288258cbe55eb12627`
- Branch at preservation time: `main`
- Preservation mechanism: commit SHA plus dirty executable diff hash.
- Dirty executable diff hash: `46a41c6d602a37805bb5264a636487462787517df8f0c34a88be2ad28055c0f0`
- Dirty executable files included in the hash:
  - `webapp/src/control-center/flavors/EvidenceTimeline.tsx`
  - `webapp/src/control-center/flavors/__tests__/EvidenceTimeline.test.tsx`

Untracked planning, brainstorm, image, and prototype files were present before implementation. They are intentionally not part of the As-Is strategy/runtime behavior definition unless the later same-harness replay contract explicitly needs a non-source artifact.

## Preserved Behavior Contract

The As-Is TradingX replay definition is the executable behavior reachable from commit `b0154070c802feeb99a22d288258cbe55eb12627` plus the dirty executable diff hash above.

The future accepted Tier 0A harness must replay As-Is strategy/runtime decisions through the post-Tier-0B measurement harness. Legacy metrics that depend on look-ahead-only measurement semantics are diagnostic only and must not be used as Tier 0A decision evidence.

Expected preserved pre-fix decisions include:

- regime snapshots using SMA(200) with `min_periods=1`;
- regime classification calls with `vix_close=None`;
- regime classification calls with `yield_curve_spread_bps=None`;
- sleeve evaluation behavior as it existed at the preserved reference, except that decision evidence must satisfy the accepted event-clock contract.

If these decisions cannot be replayed through the accepted harness without using old measurement code, Tier 0A must return `blocked_as_is_unreproducible`.

## Runtime Preflight

Runtime order-submission preflight was run before Tier 0B source edits.

Observed process scan:

- No active `tradingx` paper/live-shadow order-submit process was found.
- Existing matches were Vite development servers, local tooling, and unrelated system/application processes.
- `artifacts/operator_platform/runtime_host/state.json` reported `"status": "halted"` with reason `"Warmup incomplete for one or more configured symbols."`
- `data/runtime.pid` did not contain a usable live process id.

Conclusion: no active order-submit path was verified during the preflight. Wave 4 runtime-safety implementation is not required as a blocker before Waves 1-3, provided order submission remains paused/inactive for the Tier 0A window. If paper/live-shadow order submission is resumed, Wave 4 safety prerequisites must be completed before order submission continues or Tier 0A must return `blocked_measurement_untrusted`.

## Deferred Inputs

The final Tier 0A run still requires operator-provided memo inputs before evidence generation:

- selected 12-month capital tier;
- plausible next-higher capital tiers;
- operator model;
- shorting policy;
- preference/hurdle policy.

Until those are supplied, the harness may be implemented and tested, but final Tier 0A decision evidence cannot be complete.
