import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  areWebWritesUnlocked,
  lockWebWrites,
  postRuntimeHostStart,
  unlockWebWrites,
} from '../../api'

const SECRET_LITERAL = 'TOP-SECRET-VALUE-12345-ZZZZ'

type CapturedRequest = {
  url: string
  method: string
  headers: Headers
  body: string | null
}

function recordingFetchMock(): { spy: ReturnType<typeof vi.fn>; calls: CapturedRequest[] } {
  const calls: CapturedRequest[] = []
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : (input as URL).toString()
    const method = (init?.method ?? 'GET').toUpperCase()
    const headers = new Headers(init?.headers as HeadersInit | undefined)
    const body =
      typeof init?.body === 'string' ? init.body : init?.body == null ? null : String(init.body)
    calls.push({ url, method, headers, body })
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => ({ status: 'completed', message: 'ok' }),
      text: async () => JSON.stringify({ status: 'completed', message: 'ok' }),
      headers: new Headers(),
      url,
      clone: () => undefined as unknown as Response,
      body: null,
      bodyUsed: false,
      arrayBuffer: async () => new ArrayBuffer(0),
      blob: async () => new Blob([]),
      formData: async () => new FormData(),
      redirected: false,
      type: 'basic',
    } as unknown as Response
  })
  vi.stubGlobal('fetch', spy)
  return { spy, calls }
}

describe('Signing boundary regression', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
    window.localStorage.clear()
    lockWebWrites()
  })

  afterEach(() => {
    lockWebWrites()
    vi.restoreAllMocks()
  })

  describe('unlockWebWrites secret storage', () => {
    it('writes the secret only to sessionStorage, never to localStorage', () => {
      unlockWebWrites(SECRET_LITERAL)
      expect(window.sessionStorage.getItem('tradingx.web.writeSigningSecret')).toBe(SECRET_LITERAL)
      const localKeys = Object.keys(window.localStorage)
      for (const key of localKeys) {
        const value = window.localStorage.getItem(key) ?? ''
        expect(value.includes(SECRET_LITERAL)).toBe(false)
      }
    })

    it('removes the secret on lock', () => {
      unlockWebWrites(SECRET_LITERAL)
      expect(areWebWritesUnlocked()).toBe(true)
      lockWebWrites()
      expect(areWebWritesUnlocked()).toBe(false)
      expect(window.sessionStorage.getItem('tradingx.web.writeSigningSecret')).toBeNull()
    })
  })

  describe('POST request signing', () => {
    it('leaves writes unsigned when the browser session is locked', async () => {
      const { calls } = recordingFetchMock()
      await postRuntimeHostStart({
        symbols: ['SPY'],
        quantity: '1',
        interval_seconds: 60,
        max_cycles: null,
        sizing_policy: {
          mode: 'percent_equity',
          fixed_quantity: '10',
          equity_percent: '5',
          max_order_notional: '5000',
          cash_reserve_percent: '20',
        },
      })
      expect(JSON.parse(calls[0].body ?? '{}').sizing_policy).toEqual({
        mode: 'percent_equity',
        fixed_quantity: '10',
        equity_percent: '5',
        max_order_notional: '5000',
        cash_reserve_percent: '20',
      })
      const writeCalls = calls.filter((call) => call.method === 'POST')
      expect(writeCalls.length).toBeGreaterThan(0)
      for (const call of writeCalls) {
        const idempotency = call.headers.get('X-TradingX-Idempotency-Key') ?? ''
        expect(call.headers.get('X-TradingX-Signature')).toBeNull()
        expect(call.headers.get('X-TradingX-Timestamp')).toBeNull()
        expect(idempotency.length).toBeGreaterThan(0)
      }
    })

    it('signs writes after unlocking the browser session', async () => {
      const { calls } = recordingFetchMock()
      unlockWebWrites(SECRET_LITERAL)

      await postRuntimeHostStart({
        symbols: ['SPY'],
        quantity: '1',
        interval_seconds: 60,
        max_cycles: null,
      })

      const postCall = calls.find((call) => call.method === 'POST')
      expect(postCall).toBeDefined()
      expect(postCall?.headers.get('X-TradingX-Timestamp')).toMatch(/^\d+$/)
      expect(postCall?.headers.get('X-TradingX-Signature')).toMatch(/^[a-f0-9]{64}$/)
      expect(postCall?.headers.get('X-TradingX-Signature')).not.toContain(SECRET_LITERAL)
    })

    it('never includes the raw secret in any outbound request header, body, or URL', async () => {
      const { calls } = recordingFetchMock()
      unlockWebWrites(SECRET_LITERAL)
      await postRuntimeHostStart({
        symbols: ['SPY'],
        quantity: '1',
        interval_seconds: 60,
        max_cycles: null,
      })
      for (const call of calls) {
        expect(call.url.includes(SECRET_LITERAL)).toBe(false)
        const bodyText = call.body ?? ''
        expect(bodyText.includes(SECRET_LITERAL)).toBe(false)
        for (const [, value] of call.headers.entries()) {
          expect(value.includes(SECRET_LITERAL)).toBe(false)
        }
      }
    })

    it('produces a different idempotency key per POST', async () => {
      const { calls } = recordingFetchMock()
      await postRuntimeHostStart({
        symbols: ['SPY'],
        quantity: '1',
        interval_seconds: 60,
        max_cycles: null,
      })
      await new Promise((resolve) => setTimeout(resolve, 5))
      await postRuntimeHostStart({
        symbols: ['SPY'],
        quantity: '1',
        interval_seconds: 60,
        max_cycles: null,
      })
      const writeCalls = calls.filter((call) => call.method === 'POST')
      expect(writeCalls.length).toBe(2)
      const idemA = writeCalls[0].headers.get('X-TradingX-Idempotency-Key')
      const idemB = writeCalls[1].headers.get('X-TradingX-Idempotency-Key')
      expect(idemA).not.toBe(idemB)
    })
  })

  describe('describeWriteMode reads only booleans from config', () => {
    it('treats configSummary as a sealed surface that cannot inject a secret', async () => {
      const { describeWriteMode } = await import('../state/DataContext')
      const malicious = {
        config: {
          web_write_mode_enabled: true,
          web_write_signing_configured: true,
          web_write_max_age_seconds: 300,
          symbol_universe: [],
          service_interval_seconds: 300,
          web_refresh_interval_seconds: 15,
        },
        live_disable_report: {
          paper_only_mode: true,
          live_trading_enabled: false,
          manual_kill_switch_active: false,
        },
      } as const
      const withInjectedSecret = {
        ...malicious,
        config: {
          ...malicious.config,
          // Fields the production type doesn't declare but a hostile server might emit.
          // describeWriteMode must ignore them entirely.
          web_write_signing_secret: SECRET_LITERAL,
          signature: SECRET_LITERAL,
          secret: SECRET_LITERAL,
        },
      } as unknown as Parameters<typeof describeWriteMode>[0]
      const writeMode = describeWriteMode(withInjectedSecret, false)
      expect(writeMode.unlocked).toBe(false)
      expect(writeMode.detail).toMatch(/signing secret/i)
      expect(writeMode.detail.includes(SECRET_LITERAL)).toBe(false)
      expect(JSON.stringify(writeMode).includes(SECRET_LITERAL)).toBe(false)
    })
  })
})
