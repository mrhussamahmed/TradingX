import { useCallback, useState } from 'react'

import {
  FLATTEN_ALL_ENDPOINT_AVAILABLE,
  KILL_SWITCH_ENDPOINT_AVAILABLE,
  postFlattenAll,
  postKillSwitch,
  postRuntimeHostStart,
} from '../api'

import { Brand } from './shell/Brand'
import { LeftNav } from './shell/LeftNav'
import { OperatorRail } from './shell/OperatorRail'
import { TopStatusStrip } from './shell/TopStatusStrip'
import { Canvas } from './canvas/Canvas'
import { Toasts } from './canvas/Toasts'
import { KillSwitchDialog } from './dialogs/KillSwitchDialog'
import { FlattenAllDialog } from './dialogs/FlattenAllDialog'
import { ConfirmDialog } from './dialogs/ConfirmDialog'
import { DataProvider, useData } from './state/DataContext'
import { PreferencesProvider, usePreferences } from './state/PreferencesContext'
import { ToastProvider, useToast } from './state/ToastContext'
import {
  buildPaperRuntimeSizingPayload,
  describePaperRuntimeSizing,
  paperRuntimeFallbackQuantity,
  readPaperRuntimeSizingSettings,
} from './state/paperRuntimeSizing'

import shellStyles from './shell/Shell.module.css'
import './styles/global.css'

function ControlCenterShell() {
  const data = useData()
  const { pushToast } = useToast()
  const { setActiveFlavor } = usePreferences()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [killOpen, setKillOpen] = useState(false)
  const [killBusy, setKillBusy] = useState(false)
  const [flattenOpen, setFlattenOpen] = useState(false)
  const [flattenBusy, setFlattenBusy] = useState(false)
  const [resumeOpen, setResumeOpen] = useState(false)
  const [resumeBusy, setResumeBusy] = useState(false)
  const [railCollapsed, setRailCollapsed] = useState(false)

  const shellClass = railCollapsed
    ? `${shellStyles.shell} ${shellStyles.shellRailCollapsed}`
    : shellStyles.shell
  const configuredCadenceSeconds =
    data.runtimeHeartbeat.configured_cadence_seconds ??
    data.configSummary.config.service_interval_seconds ??
    300
  const runningCadenceSeconds =
    data.runtimeHeartbeat.running_cadence_seconds ??
    data.runtimeHeartbeat.cadence_seconds ??
    configuredCadenceSeconds

  const onRequestResume = useCallback(() => {
    setResumeOpen(true)
  }, [])

  const onConfirmResume = useCallback(async () => {
    const symbols = data.configSummary.config.symbol_universe
    const sizingSettings = readPaperRuntimeSizingSettings()
    if (!Array.isArray(symbols) || symbols.length === 0) {
      pushToast(
        'Start Paper Runtime: configured symbol universe is empty. Configure at least one symbol before starting.',
        'risk',
      )
      setResumeOpen(false)
      return
    }
    setResumeBusy(true)
    try {
      await data.runAction('Start Paper Runtime', () =>
        postRuntimeHostStart({
          symbols,
          quantity: paperRuntimeFallbackQuantity(sizingSettings),
          interval_seconds: Number(configuredCadenceSeconds),
          max_cycles: null,
          sizing_policy: buildPaperRuntimeSizingPayload(sizingSettings),
        }),
      )
    } finally {
      setResumeBusy(false)
      setResumeOpen(false)
    }
  }, [configuredCadenceSeconds, data, pushToast])

  const onConfirmKillSwitch = useCallback(async () => {
    setKillBusy(true)
    try {
      await data.runAction('Kill Switch', () => postKillSwitch())
    } finally {
      setKillBusy(false)
      setKillOpen(false)
    }
  }, [data])

  const onConfirmFlattenAll = useCallback(async () => {
    setFlattenBusy(true)
    try {
      await data.runAction('Flatten All', () => postFlattenAll())
    } finally {
      setFlattenBusy(false)
      setFlattenOpen(false)
    }
  }, [data])

  const onOpenSettings = useCallback(() => setDrawerOpen(true), [])
  const onOpenGateReport = useCallback(() => {
    setActiveFlavor('risk-core', 'manual')
    pushToast('Opened Risk Core for gate report.', 'info')
  }, [pushToast, setActiveFlavor])
  const onOpenAlertsCenter = useCallback(() => {
    setActiveFlavor('risk-core', 'manual')
    pushToast('Opened Risk Core for active alerts.', 'info')
  }, [pushToast, setActiveFlavor])
  const onOpenRuntimeHost = useCallback(() => {
    setActiveFlavor('market-day-ops', 'manual')
    pushToast('Opened Paper Trading for runtime detail.', 'info')
  }, [pushToast, setActiveFlavor])

  if (data.isBooting) {
    return (
      <div
        style={{
          display: 'grid',
          placeItems: 'center',
          height: '100vh',
          background: 'var(--bg-root)',
          color: 'var(--text-secondary)',
          fontSize: 14,
        }}
      >
        Loading operator platform…
      </div>
    )
  }

  const alertCount = data.incidents.filter((incident) => !incident.acknowledged_at_utc).length
  const resumeSizingSummary = describePaperRuntimeSizing(readPaperRuntimeSizingSettings())

  return (
    <>
      <div className={shellClass}>
        <Brand />
        <TopStatusStrip
          commandCenter={data.commandCenter}
          configSummary={data.configSummary}
          runtimeHeartbeat={data.runtimeHeartbeat}
          incidents={data.incidents}
          generatedAt={data.generatedAt}
          onOpenAlertsCenter={onOpenAlertsCenter}
        />
        <LeftNav
          onOpenSettings={onOpenSettings}
          configSummary={data.configSummary}
          alertCount={alertCount}
        />
        <Canvas drawerOpen={drawerOpen} onDrawerOpenChange={setDrawerOpen} />
        <OperatorRail
          commandCenter={data.commandCenter}
          runtimeState={data.runtimeState}
          runtimeHeartbeat={data.runtimeHeartbeat}
          configSummary={data.configSummary}
          incidents={data.incidents}
          gate3Readiness={data.gate3Readiness}
          writeMode={data.writeMode}
          onRequestKillSwitch={() => setKillOpen(true)}
          onRequestFlattenAll={() => setFlattenOpen(true)}
          onRequestResume={onRequestResume}
          onOpenGateReport={onOpenGateReport}
          onOpenAlertsCenter={onOpenAlertsCenter}
          onOpenRuntimeHost={onOpenRuntimeHost}
          onCollapsedChange={setRailCollapsed}
        />
      </div>

      {data.pageError ? (
        <div
          role="alert"
          style={{
            position: 'fixed',
            bottom: 16,
            left: 16,
            background: 'var(--bg-panel-elevated)',
            border: '1px solid rgba(255, 51, 71, 0.55)',
            borderRadius: 6,
            padding: '8px 12px',
            color: 'var(--risk)',
            fontSize: 12,
            zIndex: 70,
            maxWidth: 360,
          }}
        >
          {data.pageError}
        </div>
      ) : null}

      <Toasts />

      <KillSwitchDialog
        open={killOpen}
        onClose={() => setKillOpen(false)}
        onConfirm={onConfirmKillSwitch}
        busy={killBusy}
        killEndpointSupported={KILL_SWITCH_ENDPOINT_AVAILABLE}
        killSwitchAlreadyActive={data.configSummary.live_disable_report.manual_kill_switch_active}
        affectedSummary={{
          activeSymbols: data.runtimeState.active_symbols,
          runtimeStatus: data.runtimeState.status,
        }}
      />

      <FlattenAllDialog
        open={flattenOpen}
        onClose={() => setFlattenOpen(false)}
        onConfirm={onConfirmFlattenAll}
        busy={flattenBusy}
        flattenEndpointSupported={FLATTEN_ALL_ENDPOINT_AVAILABLE}
        positions={data.portfolio.positions_panel.positions}
      />

      <ConfirmDialog
        open={resumeOpen}
        title="Start paper runtime"
        subtitle="Start the paper runtime with the configured symbol universe."
        tone="info"
        confirmLabel="Start Paper Runtime"
        busy={resumeBusy}
        onClose={() => setResumeOpen(false)}
        onConfirm={onConfirmResume}
      >
        <p style={{ margin: 0 }}>
          Symbol universe: {data.configSummary.config.symbol_universe.join(', ') || 'SPY'}
        </p>
        <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: 13 }}>
          Sizing: {resumeSizingSummary}.
        </p>
        <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: 13 }}>
          Cadence: configured {cadenceLabel(configuredCadenceSeconds)}
          {data.runtimeHeartbeat.cadence_source === 'operator_override' ? ' from operator override' : ' from config'}
          {' · '}currently running {cadenceLabel(runningCadenceSeconds)}
          {' · '}applies {data.runtimeHeartbeat.cadence_applies_at?.replaceAll('_', ' ') ?? 'next start'}.
          The runtime will start from idle. If a gate degrades during startup, the runtime will halt automatically.
        </p>
      </ConfirmDialog>
    </>
  )
}

function cadenceLabel(seconds: number): string {
  if (seconds >= 3600) {
    const hours = seconds / 3600
    return hours === 1 ? '1 hour' : `${hours} hours`
  }
  return `${Math.round(seconds / 60)} minutes`
}

export function ControlCenterApp() {
  return (
    <ToastProvider>
      <PreferencesProvider>
        <DataProvider>
          <ControlCenterShell />
        </DataProvider>
      </PreferencesProvider>
    </ToastProvider>
  )
}
