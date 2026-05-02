const ACTIVE_RUNTIME_STATUSES = new Set([
  'running',
  'starting',
  'trading_ready',
  'broker_sync',
  'feature_ready',
  'strategy_ready',
])

export function isRuntimeActive(status: string | null | undefined): boolean {
  return ACTIVE_RUNTIME_STATUSES.has((status ?? '').toLowerCase())
}

export function runtimeStatusTone(status: string | null | undefined) {
  const normalized = (status ?? '').toLowerCase()
  if (isRuntimeActive(normalized)) return 'good'
  if (normalized === 'paused' || normalized === 'warmup') return 'watch'
  if (/halt|fail|error|crash|dead/.test(normalized)) return 'risk'
  return 'info'
}
