---
id: RESEARCH-0002
title: TradingX local control web app research
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-013
---

# Research decisions

## Decision 1: FastAPI plus React SPA

- **Decision**: use FastAPI for the local backend and a minimal React SPA
  for the frontend.
- **Why**: the operator explicitly requested a feature-rich and visually
  pleasant local website, and the constitution allows a minimal SPA for
  the local web app.

## Decision 2: Artifact-driven read models

- **Decision**: derive dashboard and history views from existing artifact
  stores plus current backend summaries.
- **Why**: the repo already persists auditable evidence, so the site
  should surface that truth rather than creating parallel state.

## Decision 3: Write mode must be explicit and off by default

- **Decision**: gate all mutating endpoints behind a dedicated web
  write-mode flag.
- **Why**: this preserves the constitution's read-only-by-default local
  web app posture and keeps safe review separate from deliberate action.

## Decision 4: Config changes are proposals, not live mutations

- **Decision**: config edits in the site create proposal files and diff
  previews under `config/proposals/`.
- **Why**: the constitution forbids bypassing the config-commit-reload
  safety path.

## Decision 5: Service lifecycle control is local and bounded

- **Decision**: if write mode is enabled, the site may start and stop the
  paper service locally, but only in paper mode and only through the same
  backend boundaries the CLI uses.
- **Why**: the operator asked for interaction and control, but the site
  still must not touch live trading or risk-rule mutation.
