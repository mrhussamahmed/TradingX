# Adversarial Reviewer Committee Report

## Safety Claims

1. Live trading remains blocked until Gate 4 approval.
   - Supporting evidence: live-disable status reports live disabled; new config
     blockers require operator acknowledgements, Gate 4 checklist
     acknowledgement, and schema-valid durable signed approval evidence.
   - Missing/weak evidence: the audit did not create or approve a real Gate 4
     artifact; it only added validation for one.

2. Local web write actions require authorization.
   - Supporting evidence: POST routes use signed write authorization; unsigned
     POST returned 403 with write mode disabled; idempotency now reserves keys
     before executing actions.
   - Missing/weak evidence: this local `.env` has web write mode enabled, so
     operator posture must be controlled carefully.

3. Duplicate paper submissions are prevented.
   - Supporting evidence: deterministic `client_order_id`, local journal, broker
     lookup recovery paths, and new web idempotency reservation.
   - Missing/weak evidence: real broker duplicate behavior was not verified in
     market hours.

4. Evidence generation is available.
   - Supporting evidence: Gate 3 report/package and replay report commands run.
   - Missing/weak evidence: generated evidence is pending or empty; decision
     report for Gate 3 cannot be generated without validation reports.

5. Recovery and drills exist.
   - Supporting evidence: alert drill command records a pending SMTP drill when
     SMTP is not configured; recovery drill path exists.
   - Missing/weak evidence: recovery drill was not run against real paper broker
     state; SMTP/Telegram delivery not configured.

## Known Failure Modes

- A process crash after web idempotency reservation but before response storage
  may leave a pending key blocked until operator cleanup. Completed writes now
  use atomic replacement, reducing completed-record corruption risk.
- Scheduler-launched market days do not expose a per-day heartbeat cap through
  the CLI.
- Missing Gate 3 validation reports make the decision-report path fail with an
  exception instead of a structured pending packet.
- Local write mode enabled in `.env` increases operational risk even with
  signing.
- Browser visual validation was not completed because in-app browser navigation
  to local HTTP timed out.

## Worst-Case Scenarios

- Without the live Gate 4 fix, a future operator with live credentials and
  technical flags could accidentally reach live mode before documented sign-off.
  This has been fixed.
- Without the idempotency fix, two concurrent signed write requests could trigger
  duplicate local control actions. This has been fixed for same-key in-progress
  writes.
- If local write mode stays enabled and the signing secret is mishandled, a
  local actor could invoke control actions.
- If unattended paper operation runs before Gate 3 evidence exists, the operator
  may over-trust an unproven runtime.

## Live Trading Block

Live trading now requires all of these to be true:

- Broker mode is `live`.
- Real live credentials are configured.
- File-layer live config flag is enabled.
- Process-env live opt-in is enabled.
- Code guard is enabled.
- Web write signing is configured.
- Process-env operator acknowledgement is present.
- Process-env Gate 4 checklist acknowledgement is present.
- Durable signed Gate 4 approval artifact is configured, valid, unexpired, and
  checklist-backed.
- Manual kill switch is not active.
- Dry-run mode is not active.

Current local status: live trading disabled, live credentials absent, broker
mode paper, operator acknowledgement missing, Gate 4 checklist acknowledgement
missing, and durable Gate 4 approval evidence missing.

## Duplicate Paper Order Proof

Evidence is stronger after the fix but still incomplete:

- Web write idempotency now blocks pending duplicates and completes records with
  atomic replacement.
- Paper execution uses deterministic client order IDs and recovery lookup.
- Tests cover web idempotency and live fail-closed logic.
- Real Alpaca paper duplicate handling was not verified during market hours.

## Write Authorization

Write actions require local write mode, signing secret, timestamp, idempotency
key, and HMAC signature. The audit server forced write mode off and confirmed an
unsigned stop action returned 403. The local `.env` itself has write mode
enabled, which should be treated as an operator-controlled risk.

## Recovery And Drills

SMTP alert drill produced a pending record because SMTP is not configured.
Recovery drill was reviewed but not run against broker-backed paths. The recovery
drill should record sanitized failure reasons before it is considered strong
evidence.

## Gate Readiness

Current status is not ready:

- Gate 3 report: pending.
- Gate 3 package: pending.
- Promotion check: max state disabled with `authority_artifact_invalid`.
- Decision report: failed because no validation reports are available.
- Gate 3 duration/trade-count target: 0 trades / 0 days observed.

## Questions Before Further Promotion

- Where is the durable Gate 4 sign-off artifact, who approved it, and how is it
  revoked?
- Why is local web write mode enabled in `.env`, and who controls the signing
  secret?
- Can the team demonstrate no duplicate paper orders against real Alpaca paper
  state during market hours?
- Can the scheduler be run unattended with an operator-visible bounded stop
  condition?
- Can recovery drills produce clear, sanitized root-cause evidence?
- Are Gate 1/2/3 validation reports complete and reproducible?
- Have SMTP/Telegram alerts been verified end to end?
- Has Postgres mode been tested if it will be used for any promoted runtime?
