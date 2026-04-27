import { describe, expect, it } from 'vitest'

import type {
  BotRuntimeState,
  CommandCenterSnapshot,
  ConfigSummary,
  RuntimeHeartbeatSnapshot,
} from '../../../types'

import { describePnl, deriveRiskTone, deriveRuntimeTone } from '../TopStatusStrip'
import { deriveResumeBlocker } from '../OperatorRail'

const blankRuntimeState: BotRuntimeState = {
  status: 'idle',
  status_reason: '',
  active_symbols: [],
  started_at_utc: null,
  updated_at_utc: '',
  last_error: '',
  active_strategy_id: '',
  active_model_snapshot_id: '',
  latest_selection_id: '',
}

const blankRuntimeHeartbeat: RuntimeHeartbeatSnapshot = {
  heartbeat_state: 'Idle',
  heartbeat_summary: '',
  heartbeat_tone: 'neutral',
  cadence_seconds: 60,
  cadence_label: '60s',
  last_evaluation_at_utc: null,
  next_evaluation_at_utc: null,
  last_decision: '',
  decision_reason: '',
  score_explanation: '',
  current_exposure: '',
  current_exposure_detail: '',
  active_symbol: '',
  selected_symbol: '',
  decision: '',
  runtime_truth: [],
  symbol_rows: [],
  decision_ladder: [],
  operator_guidance: null,
}

const blankConfig: ConfigSummary = {
  config: {
    web_write_mode_enabled: true,
    web_write_signing_configured: true,
    web_write_max_age_seconds: 300,
    symbol_universe: ['SPY'],
    service_interval_seconds: 300,
    web_refresh_interval_seconds: 15,
  },
  live_disable_report: {
    paper_only_mode: true,
    live_trading_enabled: false,
    manual_kill_switch_active: false,
  },
}

function makeCommandCenter(gates: Record<string, string>): CommandCenterSnapshot {
  return {
    generated_at_utc: '',
    service_status: {
      status: 'idle',
      active_symbols: [],
      interval_seconds: 300,
      cycles_completed: 0,
      started_at_utc: null,
      last_completed_at_utc: null,
      last_error: '',
    },
    market_session_label: '',
    session_mode: '',
    account_summary: { cash: '', equity: '', buying_power: '', daily_pnl: '' },
    equity_curve: [],
    exposure_breakdown: [],
    watchlist: [],
    gate_statuses: gates,
    recommendations: {},
    headline_incidents: [],
  }
}

describe('deriveRiskTone', () => {
  it('returns neutral when no gates exist', () => {
    expect(deriveRiskTone({}).tone).toBe('neutral')
  })

  it('flags risk when any gate fails', () => {
    expect(deriveRiskTone({ paper: 'pass', limits: 'failing' }).tone).toBe('risk')
    expect(deriveRiskTone({ a: 'BLOCK_REQUIRED' }).tone).toBe('risk')
  })

  it('flags watch on degraded gates', () => {
    expect(deriveRiskTone({ paper: 'pass', drift: 'watch' }).tone).toBe('watch')
    expect(deriveRiskTone({ slippage: 'degraded' }).tone).toBe('watch')
  })

  it('returns good when all gates pass', () => {
    expect(deriveRiskTone({ paper: 'pass', limits: 'ok' }).tone).toBe('good')
  })
})

describe('deriveRuntimeTone', () => {
  it('reads tone from heartbeat snapshot', () => {
    expect(deriveRuntimeTone({ ...blankRuntimeHeartbeat, heartbeat_tone: 'good' })).toBe('good')
    expect(deriveRuntimeTone({ ...blankRuntimeHeartbeat, heartbeat_tone: 'risk' })).toBe('risk')
    expect(deriveRuntimeTone({ ...blankRuntimeHeartbeat, heartbeat_tone: 'watch' })).toBe('watch')
    expect(deriveRuntimeTone({ ...blankRuntimeHeartbeat, heartbeat_tone: 'unknown' })).toBe('neutral')
  })
})

describe('describePnl', () => {
  it('returns neutral on empty value', () => {
    expect(describePnl('').tone).toBe('neutral')
  })

  it('formats positive values as good', () => {
    const result = describePnl('1234.56')
    expect(result.tone).toBe('good')
    expect(result.display.startsWith('+')).toBe(true)
  })

  it('formats negative values as risk', () => {
    const result = describePnl('-150')
    expect(result.tone).toBe('risk')
  })

  it('treats zero as neutral', () => {
    const result = describePnl('0')
    expect(result.tone).toBe('neutral')
  })
})

describe('deriveResumeBlocker', () => {
  it('blocks when write mode is disabled on the server', () => {
    const blocker = deriveResumeBlocker({
      runtimeState: blankRuntimeState,
      runtimeHeartbeat: blankRuntimeHeartbeat,
      commandCenter: makeCommandCenter({}),
      configSummary: {
        ...blankConfig,
        config: { ...blankConfig.config, web_write_mode_enabled: false },
      },
      writeUnlocked: true,
    })
    expect(blocker.blocked).toBe(true)
    expect(blocker.reason).toMatch(/write mode is disabled/i)
  })

  it('blocks when writes are not unlocked', () => {
    const blocker = deriveResumeBlocker({
      runtimeState: blankRuntimeState,
      runtimeHeartbeat: blankRuntimeHeartbeat,
      commandCenter: makeCommandCenter({}),
      configSummary: blankConfig,
      writeUnlocked: false,
    })
    expect(blocker.blocked).toBe(true)
    expect(blocker.reason).toMatch(/signing secret/i)
  })

  it('blocks when manual kill switch is active', () => {
    const blocker = deriveResumeBlocker({
      runtimeState: blankRuntimeState,
      runtimeHeartbeat: blankRuntimeHeartbeat,
      commandCenter: makeCommandCenter({}),
      configSummary: {
        ...blankConfig,
        live_disable_report: { ...blankConfig.live_disable_report, manual_kill_switch_active: true },
      },
      writeUnlocked: true,
    })
    expect(blocker.blocked).toBe(true)
    expect(blocker.reason).toMatch(/kill switch is active/i)
  })

  it('blocks when a gate is failing and names the gate', () => {
    const blocker = deriveResumeBlocker({
      runtimeState: blankRuntimeState,
      runtimeHeartbeat: blankRuntimeHeartbeat,
      commandCenter: makeCommandCenter({ risk_limits: 'failing' }),
      configSummary: blankConfig,
      writeUnlocked: true,
    })
    expect(blocker.blocked).toBe(true)
    expect(blocker.reason).toMatch(/Risk Limits is failing/i)
    expect(blocker.reason).toMatch(/Risk Core/i)
  })

  it('blocks when runtime is already running', () => {
    const blocker = deriveResumeBlocker({
      runtimeState: { ...blankRuntimeState, status: 'running' },
      runtimeHeartbeat: blankRuntimeHeartbeat,
      commandCenter: makeCommandCenter({}),
      configSummary: blankConfig,
      writeUnlocked: true,
    })
    expect(blocker.blocked).toBe(true)
    expect(blocker.reason).toMatch(/already running/i)
  })

  it('blocks when configured symbol universe is empty', () => {
    const blocker = deriveResumeBlocker({
      runtimeState: blankRuntimeState,
      runtimeHeartbeat: blankRuntimeHeartbeat,
      commandCenter: makeCommandCenter({}),
      configSummary: {
        ...blankConfig,
        config: { ...blankConfig.config, symbol_universe: [] },
      },
      writeUnlocked: true,
    })
    expect(blocker.blocked).toBe(true)
    expect(blocker.reason).toMatch(/symbol universe is empty/i)
  })

  it('does not block when conditions are clean', () => {
    const blocker = deriveResumeBlocker({
      runtimeState: blankRuntimeState,
      runtimeHeartbeat: blankRuntimeHeartbeat,
      commandCenter: makeCommandCenter({ paper: 'pass', limits: 'ok' }),
      configSummary: blankConfig,
      writeUnlocked: true,
    })
    expect(blocker.blocked).toBe(false)
  })
})
