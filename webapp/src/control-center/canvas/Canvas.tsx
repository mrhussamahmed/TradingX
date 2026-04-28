import { useCallback, useEffect, useState } from 'react'
import { Layers, RotateCcw, Settings2, Sparkles, X } from 'lucide-react'

import { FLAVORS } from '../state/types'
import type { AutoSwitchSuggestion } from '../state/types'
import { usePreferences } from '../state/PreferencesContext'
import { useFlavorShortcuts } from '../state/useFlavorShortcuts'
import { useData } from '../state/DataContext'
import { useAutoSwitchSuggestion } from '../state/useAutoSwitchSuggestion'
import { EvidenceReplayFlavor } from '../flavors/EvidenceReplayFlavor'
import { MarketChartFlavor } from '../flavors/MarketChartFlavor'
import { MarketDayOpsFlavor } from '../flavors/MarketDayOpsFlavor'
import { OperatorMissionControlFlavor } from '../flavors/OperatorMissionControlFlavor'
import { PortfolioConstellationFlavor } from '../flavors/PortfolioConstellationFlavor'
import { RiskCoreFlavor } from '../flavors/RiskCoreFlavor'
import { StrategyForgeFlavor } from '../flavors/StrategyForgeFlavor'

import { ViewDefaultsDrawer } from './ViewDefaultsDrawer'
import { ViewFlavorSwitcher } from './ViewFlavorSwitcher'
import styles from './Canvas.module.css'

export type CanvasProps = {
  drawerOpen: boolean
  onDrawerOpenChange: (open: boolean) => void
}

export function Canvas({ drawerOpen, onDrawerOpenChange }: CanvasProps) {
  const { prefs, manualOverride, hasStoredPrefs, resumeAutoSwitch, setToggle, setActiveFlavor } =
    usePreferences()
  const { commandCenter, incidents, schedulerState, gate3Readiness } = useData()
  const [transition, setTransition] = useState<{ key: number; message: string } | null>(null)
  const [systemHintDismissed, setSystemHintDismissed] = useState(false)

  const showTransition = useCallback((label: string, reason?: string) => {
    setTransition({ key: Date.now(), message: reason ? `Switched to ${label} — ${reason}` : `Switched to ${label}` })
  }, [])

  useEffect(() => {
    if (!transition) return
    const id = window.setTimeout(() => setTransition(null), 4000)
    return () => window.clearTimeout(id)
  }, [transition])

  useFlavorShortcuts(showTransition)

  const flavorMeta = FLAVORS.find((flavor) => flavor.id === prefs.activeFlavor) ?? FLAVORS[0]

  const suggestion = useAutoSwitchSuggestion({
    enabled: prefs.autoSwitchByWorkflow,
    manualOverride,
    activeFlavor: prefs.activeFlavor,
    commandCenter,
    incidents,
    schedulerState,
    gate3Readiness,
  })

  const handleAcceptSuggestion = useCallback(
    (next: AutoSwitchSuggestion) => {
      const meta = FLAVORS.find((flavor) => flavor.id === next.flavor)
      setActiveFlavor(next.flavor, 'auto')
      if (meta) {
        showTransition(meta.label, next.detail)
      }
    },
    [setActiveFlavor, showTransition],
  )

  return (
    <main className={styles.canvasInner} aria-label="Center canvas">
      <ViewFlavorSwitcher />

      <div className={styles.canvasHeader}>
        <div className={styles.canvasTitleBlock}>
          <div className={styles.canvasTitle}>
            <Sparkles size={18} color="var(--primary-bright)" aria-hidden />
            <span>{flavorMeta.label}</span>
            {transition ? (
              <span key={transition.key} className={styles.transitionBadge}>
                {transition.message}
              </span>
            ) : null}
          </div>
          <span className={styles.canvasSubtitle}>
            {flavorMeta.subtitle} · {prefs.density} · {prefs.accentTheme.replace('-', ' / ')}
          </span>
        </div>
        <div className={styles.canvasHeaderActions}>
          {manualOverride ? (
            <button type="button" className="btn btn-ghost" onClick={resumeAutoSwitch}>
              <RotateCcw size={14} /> Resume auto-switch
            </button>
          ) : null}
          <button
            type="button"
            className="btn"
            aria-pressed={prefs.showEvidenceLayer}
            onClick={() => setToggle('showEvidenceLayer', !prefs.showEvidenceLayer)}
            title="Toggle evidence layer overlay"
          >
            <Layers size={14} /> Evidence: {prefs.showEvidenceLayer ? 'On' : 'Off'}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => onDrawerOpenChange(!drawerOpen)}
            aria-expanded={drawerOpen}
            aria-controls="view-defaults-drawer"
          >
            <Settings2 size={14} /> View Settings
          </button>
        </div>
      </div>

      {suggestion ? (
        <div className={styles.suggestionBanner} role="status" aria-live="polite">
          <strong>Suggested view:</strong>
          <span>
            {suggestion.detail}
          </span>
          <button
            type="button"
            className="btn btn-sm btn-primary"
            style={{ marginLeft: 'auto' }}
            onClick={() => handleAcceptSuggestion(suggestion)}
          >
            Switch to {FLAVORS.find((f) => f.id === suggestion.flavor)?.label}
          </button>
        </div>
      ) : null}

      {manualOverride ? (
        <div className={styles.overrideBanner}>
          <span>Manual view override active.</span>
          <button type="button" className="btn btn-sm btn-ghost" onClick={resumeAutoSwitch} style={{ marginLeft: 'auto' }}>
            Resume auto-switch
          </button>
        </div>
      ) : null}

      {!hasStoredPrefs && !systemHintDismissed ? (
        <div className={styles.systemDefaultsHint}>
          <span>Using system view defaults. Open View Settings to customize and persist.</span>
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => onDrawerOpenChange(true)}
          >
            Open settings
          </button>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={() => setSystemHintDismissed(true)}
            aria-label="Dismiss system defaults hint"
          >
            <X size={12} />
          </button>
        </div>
      ) : null}

      <div className={styles.canvasScroll} id="canvas-scroll">
        <ActiveFlavor flavorId={prefs.activeFlavor} />
      </div>

      <ViewDefaultsDrawer open={drawerOpen} onClose={() => onDrawerOpenChange(false)} />
    </main>
  )
}

function ActiveFlavor({ flavorId }: { flavorId: string }) {
  switch (flavorId) {
    case 'mission-control':
      return <OperatorMissionControlFlavor />
    case 'market-chart':
      return <MarketChartFlavor />
    case 'strategy-forge':
      return <StrategyForgeFlavor />
    case 'market-day-ops':
      return <MarketDayOpsFlavor />
    case 'risk-core':
      return <RiskCoreFlavor />
    case 'portfolio-constellation':
      return <PortfolioConstellationFlavor />
    case 'evidence-replay':
      return <EvidenceReplayFlavor />
    default:
      return null
  }
}
