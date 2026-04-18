---
id: QUICKSTART-0006
title: TradingX replay-slippage evidence quickstart
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-017
---

# Quickstart: TradingX replay-slippage evidence

## Generate replay evidence

```bash
uv run tradingx replay-slippage-report \
  --paper-artifact-root artifacts/paper_loop \
  --validation-artifact-root artifacts/validation
```

## Refresh Gate 3 after replay generation

```bash
uv run tradingx gate3-report \
  --paper-artifact-root artifacts/paper_loop \
  --validation-artifact-root artifacts/validation
```

## Run from the website

1. Start the local site with write mode enabled.
2. Open the `Gate 3 Ops` surface.
3. Trigger the replay-slippage refresh action.
4. Inspect the replay matched count, paper mean, replay mean, and
   divergence ratio.
