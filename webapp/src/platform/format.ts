export function cx(...tokens: Array<string | false | null | undefined>) {
  return tokens.filter(Boolean).join(' ')
}

export function formatTimestamp(raw: string | null | undefined) {
  if (!raw) {
    return 'Not yet recorded'
  }
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) {
    return raw
  }
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)
}

export function formatTimeUntil(
  raw: string | null | undefined,
  nowMs: number = Date.now(),
) {
  if (!raw) {
    return 'Not scheduled'
  }
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) {
    return raw
  }
  const deltaSeconds = Math.round((date.getTime() - nowMs) / 1000)
  if (deltaSeconds <= 0) {
    return 'Due now'
  }
  const minutes = Math.floor(deltaSeconds / 60)
  const seconds = deltaSeconds % 60
  if (minutes <= 0) {
    return `In ${seconds}s`
  }
  return `In ${minutes}m ${seconds}s`
}

export function prettyLabel(value: string | null | undefined) {
  if (!value) {
    return 'n/a'
  }
  return value
    .replaceAll('_', ' ')
    .replaceAll('-', ' ')
    .replace(/\b\w/g, (match) => match.toUpperCase())
}

export function parseNumericValue(value: string | number | null | undefined) {
  if (typeof value === 'number') {
    return value
  }
  if (!value) {
    return 0
  }
  const normalized = value.replaceAll(',', '').replaceAll('$', '').replaceAll('%', '')
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : 0
}

export function toCurrency(value: string | number | null | undefined) {
  const amount = parseNumericValue(value)
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(amount)
}

export function shortDirection(value: string) {
  if (value.startsWith('+') || value.toLowerCase().includes('good')) {
    return 'up'
  }
  if (value.startsWith('-') || value.toLowerCase().includes('bad')) {
    return 'down'
  }
  return 'flat'
}
