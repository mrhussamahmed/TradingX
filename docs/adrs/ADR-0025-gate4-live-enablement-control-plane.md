---
id: ADR-0025
title: Gate 4 live-enablement control plane and signed web writes
version: 1.0.0
status: active
created: 2026-04-23
last_amended: 2026-04-23
supersedes: null
superseded_by: null
author_session: gpt-5-codex-2026-04-23
---

# ADR-0025: Gate 4 live-enablement control plane and signed web writes

## Status

Accepted on 2026-04-23. This ADR becomes operational with the Gate 4
live-enablement implementation that lands alongside it.

## Context

- TradingX already had paper-only runtime, operator, and web control
  surfaces, but generic production entrypoints were still hard-wired to
  `paper=True` and paper market-data credentials.
- Gate 4 acceptance explicitly requires fail-closed live controls plus
  request signing and idempotency on web write endpoints before any
  live-control environment variable is honored.
- The repository also exposes configuration summaries over both CLI and
  web read paths, so any new signing secret must remain invisible on
  every safe-summary surface.

## Decision

1. Generic production entrypoints now resolve broker mode through one
   shared control-plane helper rather than constructing trading clients
   inline.
2. Live enablement is controlled by five explicit conditions:
   - requested broker mode is `live`
   - real live credentials are present
   - file-layer live config is enabled
   - process-env live opt-in is enabled
   - web write signing is configured
   plus the existing manual kill-switch / dry-run fail-closed checks
3. Explicitly paper-named entrypoints remain paper-only wrappers.
4. Market-data credential selection follows the same mode-aware cutover
   as the trading client path; generic live-capable entrypoints must not
   remain paper-bound through the data gateway.
5. Every FastAPI POST endpoint now requires:
   - write mode enabled
   - signed request
   - bounded timestamp freshness
   - idempotency key
6. The shipped browser SPA signs POST requests client-side only after
   the local operator unlocks writes for that browser session by
   entering the signing secret at runtime.
7. The signing secret is sensitive configuration and must never appear
   in:
   - `TradingConfig.to_safe_summary()`
   - `config-summary`
   - `/api/config/summary`
   - readmodels or other GET responses
8. Duplicate signed POSTs replay the first stored response payload;
   same idempotency key plus different fingerprint is a hard conflict.

## Consequences

### Positive

- Live-capable entrypoints now have one auditable mode-selection seam
  instead of scattered inline `paper=True` decisions.
- Web writes satisfy the Gate 4 signed/idempotent control requirement
  without putting the secret into the frontend bundle.
- Operators can inspect live-disable reasons safely from CLI or web
  without secret leakage.

### Negative

- Generic runtime/operator entrypoints now fail closed when live mode is
  requested without the full control posture, which makes partial
  misconfiguration noisier than before.
- Browser write actions now require a local unlock step each session.

## Alternatives considered

- **Keep generic entrypoints paper-bound and add a separate live-only
  command set.** Rejected because it would leave the default runtime
  surface inconsistent and easy to misread.
- **Trust `TRADINGX_WEB_WRITE_MODE_ENABLED` alone for browser writes.**
  Rejected because Gate 4 explicitly requires request signing and
  idempotency, not only a coarse write-mode boolean.
- **Expose the signing secret through config summary so the SPA can read
  it automatically.** Rejected because it would turn a safe GET path
  into a secret-distribution channel.

## Sources

- [Gate 4 live enablement implementation plan](/docs/superpowers/plans/2026-04-23-gate-4-live-enablement-plan.md)
- [GATES-0001 acceptance gates](/docs/validation/acceptance_gates.md)
- [ADR-0010](/docs/adrs/ADR-0010-local-web-app-react-spa.md)
- [ADR-0016](/docs/adrs/ADR-0016-local-trading-appliance-runtime-host.md)
