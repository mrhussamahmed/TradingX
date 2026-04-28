import { describe, expect, it } from 'vitest'

import {
  describeTradePermission,
  deriveCombinedGateTone,
  deriveDecisionEvidenceTimestamp,
  deriveGateEvidenceTimestamp,
  deriveRequiredSafetyEvidence,
  latestSourceEvidenceTimestamp,
} from '../OperatorMissionControlModel'

describe('describeTradePermission', () => {
  it('does not report a good safety verdict when runtime is failed in paper mode', () => {
    const verdict = describeTradePermission({
      liveTradingEnabled: false,
      paperOnlyMode: true,
      killSwitchActive: false,
      gateTone: 'good',
      runtimeStatus: 'failed',
      evidenceStale: false,
    })

    expect(verdict.value).toBe('Runtime unhealthy')
    expect(verdict.tone).toBe('risk')
  })

  it('degrades the safety verdict when source evidence is stale or missing', () => {
    const verdict = describeTradePermission({
      liveTradingEnabled: false,
      paperOnlyMode: true,
      killSwitchActive: false,
      gateTone: 'good',
      runtimeStatus: 'running',
      evidenceStale: true,
    })

    expect(verdict.value).toBe('Verify evidence')
    expect(verdict.tone).toBe('watch')
  })

  it('keeps live-enabled config at risk severity even when evidence is stale', () => {
    const verdict = describeTradePermission({
      liveTradingEnabled: true,
      paperOnlyMode: false,
      killSwitchActive: false,
      gateTone: 'good',
      runtimeStatus: 'running',
      evidenceStale: true,
    })

    expect(verdict.value).toBe('Live flag on')
    expect(verdict.tone).toBe('risk')
  })
})

describe('latestSourceEvidenceTimestamp', () => {
  it('ignores the UI refresh timestamp when source evidence has no timestamp', () => {
    expect(
      latestSourceEvidenceTimestamp({
        uiRefreshTimestamp: '2026-04-28T12:00:00Z',
        sourceTimestamps: [],
      }),
    ).toBeNull()
  })

  it('returns the newest real source timestamp', () => {
    expect(
      latestSourceEvidenceTimestamp({
        uiRefreshTimestamp: '2026-04-28T12:00:00Z',
        sourceTimestamps: ['2026-04-28T11:30:00Z', '2026-04-28T11:45:00Z'],
      }),
    ).toBe('2026-04-28T11:45:00Z')
  })
})

describe('deriveRequiredSafetyEvidence', () => {
  it('marks required evidence stale once it ages past the threshold', () => {
    const result = deriveRequiredSafetyEvidence({
      nowMs: new Date('2026-04-28T12:21:00Z').getTime(),
      staleMinutes: 20,
      heartbeatTimestamp: '2026-04-28T12:00:00Z',
      gateTimestamp: '2026-04-28T12:00:00Z',
      portfolioTimestamp: '2026-04-28T12:00:00Z',
      decisionTimestamp: '2026-04-28T12:00:00Z',
    })

    expect(result.stale).toBe(true)
    expect(result.staleClasses).toEqual([
      'heartbeat evidence',
      'gate evidence',
      'portfolio evidence',
      'decision evidence',
    ])
  })

  it('marks safety evidence stale when a required evidence class is missing', () => {
    const result = deriveRequiredSafetyEvidence({
      nowMs: new Date('2026-04-28T12:00:00Z').getTime(),
      staleMinutes: 20,
      heartbeatTimestamp: '2026-04-28T11:55:00Z',
      gateTimestamp: '2026-04-28T11:59:00Z',
      portfolioTimestamp: '2026-04-28T11:58:00Z',
      decisionTimestamp: null,
    })

    expect(result.stale).toBe(true)
    expect(result.missing).toContain('decision evidence')
  })

  it('does not let fresh noncritical evidence replace required safety evidence', () => {
    const result = deriveRequiredSafetyEvidence({
      nowMs: new Date('2026-04-28T12:00:00Z').getTime(),
      staleMinutes: 20,
      heartbeatTimestamp: null,
      gateTimestamp: null,
      portfolioTimestamp: null,
      decisionTimestamp: null,
    })

    expect(result.latestRequiredTimestamp).toBeNull()
    expect(result.stale).toBe(true)
  })
})

describe('deriveGateEvidenceTimestamp', () => {
  it('does not use a command-center timestamp when no gates are present', () => {
    expect(
      deriveGateEvidenceTimestamp({
        commandCenterGeneratedAt: '2026-04-28T12:00:00Z',
        gateStatuses: {},
        gate3GeneratedAt: '',
        gate3Criteria: [],
      }),
    ).toBeNull()
  })

  it('does not use command-center read-model timestamps even when gate labels exist', () => {
    expect(
      deriveGateEvidenceTimestamp({
        commandCenterGeneratedAt: '2026-04-28T12:00:00Z',
        gateStatuses: { paper: 'pass' },
        gate3GeneratedAt: '',
        gate3Criteria: [],
      }),
    ).toBeNull()
  })

  it('does not use Gate 3 report generated_at as source freshness even when criteria exist', () => {
    expect(
      deriveGateEvidenceTimestamp({
        commandCenterGeneratedAt: '2026-04-28T12:00:00Z',
        gateStatuses: {},
        gate3GeneratedAt: '2026-04-28T11:59:00Z',
        gate3Criteria: [{ criterion_id: 'closed_trades', status: 'pass' }],
      }),
    ).toBeNull()
  })
})

describe('deriveDecisionEvidenceTimestamp', () => {
  it('does not count placeholder no-decision labels as decision evidence', () => {
    expect(
      deriveDecisionEvidenceTimestamp({
        lastDecision: 'No decision yet',
        decision: '',
        selectionId: '',
        selectionGeneratedAt: '2026-04-28T12:00:00Z',
      }),
    ).toBeNull()
  })

  it('uses opportunity selection generation time for real decision evidence', () => {
    expect(
      deriveDecisionEvidenceTimestamp({
        lastDecision: 'selected SPY',
        decision: 'buy',
        selectionId: 'selection-1',
        selectionGeneratedAt: '2026-04-28T12:00:00Z',
      }),
    ).toBe('2026-04-28T12:00:00Z')
  })
})

describe('deriveCombinedGateTone', () => {
  it('includes failing Gate 3 criteria in the safety verdict tone', () => {
    const tone = deriveCombinedGateTone({
      commandCenterGates: { paper: 'pass' },
      gate3Criteria: [{ criterion_id: 'drawdown', status: 'fail' }],
    })

    expect(tone.tone).toBe('risk')
    expect(tone.detail).toMatch(/Gate 3/i)
  })

  it('treats pending Gate 3 criteria as watch instead of passing', () => {
    const tone = deriveCombinedGateTone({
      commandCenterGates: { paper: 'pass' },
      gate3Criteria: [{ criterion_id: 'duration_or_trade_count', status: 'pending' }],
    })

    expect(tone.tone).toBe('watch')
    expect(tone.detail).toMatch(/Gate 3/i)
  })

  it('treats incomplete and negated ready statuses as watch instead of passing', () => {
    const tone = deriveCombinedGateTone({
      commandCenterGates: { paper: 'pass' },
      gate3Criteria: [
        { criterion_id: 'duration_or_trade_count', status: 'incomplete' },
        { criterion_id: 'recovery_drill', status: 'not_ready' },
      ],
    })

    expect(tone.tone).toBe('watch')
    expect(tone.detail).toMatch(/Gate 3/i)
  })
})
