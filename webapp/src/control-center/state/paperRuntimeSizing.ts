import type { RuntimeSizingPolicyPayload } from '../../api'

export type PaperRuntimeSizingMode = 'fixed_shares' | 'percent_equity'

export type PaperRuntimeSizingSettings = {
  mode: PaperRuntimeSizingMode
  fixedQuantity: string
  equityPercent: string
  maxOrderNotional: string
  cashReservePercent: string
}

const STORAGE_KEY = 'tradingx.paperRuntime.sizing'

export const DEFAULT_PAPER_RUNTIME_SIZING: PaperRuntimeSizingSettings = {
  mode: 'fixed_shares',
  fixedQuantity: '10',
  equityPercent: '5',
  maxOrderNotional: '5000',
  cashReservePercent: '20',
}

export function readPaperRuntimeSizingSettings(): PaperRuntimeSizingSettings {
  if (typeof window === 'undefined') {
    return DEFAULT_PAPER_RUNTIME_SIZING
  }
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) {
    return DEFAULT_PAPER_RUNTIME_SIZING
  }
  try {
    return normalizeSizingSettings(JSON.parse(raw) as Partial<PaperRuntimeSizingSettings>)
  } catch {
    return DEFAULT_PAPER_RUNTIME_SIZING
  }
}

export function writePaperRuntimeSizingSettings(settings: PaperRuntimeSizingSettings) {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalizeSizingSettings(settings)))
}

export function buildPaperRuntimeSizingPayload(
  settings: PaperRuntimeSizingSettings,
): RuntimeSizingPolicyPayload {
  const normalized = normalizeSizingSettings(settings)
  return {
    mode: normalized.mode,
    fixed_quantity: normalized.fixedQuantity,
    equity_percent: normalized.equityPercent,
    max_order_notional: normalized.maxOrderNotional.trim() || null,
    cash_reserve_percent: normalized.cashReservePercent,
  }
}

export function paperRuntimeFallbackQuantity(settings: PaperRuntimeSizingSettings) {
  const normalized = normalizeSizingSettings(settings)
  return normalized.mode === 'fixed_shares' ? normalized.fixedQuantity : '1'
}

export function describePaperRuntimeSizing(settings: PaperRuntimeSizingSettings) {
  const normalized = normalizeSizingSettings(settings)
  const base =
    normalized.mode === 'fixed_shares'
      ? `${normalized.fixedQuantity} shares per accepted entry`
      : `${normalized.equityPercent}% equity per accepted entry`
  const cap = normalized.maxOrderNotional.trim()
    ? `, capped at $${normalized.maxOrderNotional}`
    : ''
  return `${base}${cap}, ${normalized.cashReservePercent}% cash reserve`
}

export function normalizeSizingSettings(
  settings: Partial<PaperRuntimeSizingSettings>,
): PaperRuntimeSizingSettings {
  const mode = settings.mode === 'percent_equity' ? 'percent_equity' : 'fixed_shares'
  return {
    mode,
    fixedQuantity: numericText(settings.fixedQuantity, DEFAULT_PAPER_RUNTIME_SIZING.fixedQuantity),
    equityPercent: numericText(settings.equityPercent, DEFAULT_PAPER_RUNTIME_SIZING.equityPercent),
    maxOrderNotional: optionalNumericText(settings.maxOrderNotional),
    cashReservePercent: numericText(
      settings.cashReservePercent,
      DEFAULT_PAPER_RUNTIME_SIZING.cashReservePercent,
    ),
  }
}

function numericText(value: unknown, fallback: string) {
  if (typeof value !== 'string') {
    return fallback
  }
  const trimmed = value.trim()
  return trimmed && Number.isFinite(Number(trimmed)) ? trimmed : fallback
}

function optionalNumericText(value: unknown) {
  if (typeof value !== 'string') {
    return DEFAULT_PAPER_RUNTIME_SIZING.maxOrderNotional
  }
  const trimmed = value.trim()
  return !trimmed || Number.isFinite(Number(trimmed))
    ? trimmed
    : DEFAULT_PAPER_RUNTIME_SIZING.maxOrderNotional
}
