## ADDED Requirements

### Requirement: Market-day workflows are bounded for audit
Market-day automation SHALL run with explicit heartbeat or scheduled-day limits
when exercised during audit.

#### Scenario: Bounded market-day flow runs
- **WHEN** pre-open, heartbeat, closeout, and Gate 3 refresh are exercised
- **THEN** the workflow exits under its configured bound and writes evidence for
  each stage

### Requirement: Scheduler launches at most one workflow per trading day
The recurring market-day scheduler SHALL prevent duplicate market-day launches
for the same trading day.

#### Scenario: Scheduler polls repeatedly
- **WHEN** the scheduler observes the same eligible trading day more than once
- **THEN** it records one durable schedule artifact and avoids launching a
  duplicate workflow

### Requirement: Scheduler respects market calendars
The scheduler SHALL use regular-hours US equities calendar authority rather
than local wall-clock guesses.

#### Scenario: Non-trading day is observed
- **WHEN** the scheduler runs on a closed market day
- **THEN** it does not launch a paper trading workflow
