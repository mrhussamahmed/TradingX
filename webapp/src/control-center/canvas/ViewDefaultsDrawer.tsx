import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

import { ACCENT_THEMES, DENSITIES, FLAVORS, type AccentTheme, type ViewFlavor } from '../state/types'
import { usePreferences, type ToggleKey } from '../state/PreferencesContext'
import { useToast } from '../state/ToastContext'

import styles from './Canvas.module.css'

const THEME_SWATCHES: Record<AccentTheme, [string, string]> = {
  'blue-red': ['#147cff', '#ff3347'],
  'cyan-amber': ['#19d3ff', '#ffb020'],
  'purple-teal': ['#7c4dff', '#18d6c2'],
  'green-gray': ['#28e078', '#8ea3b8'],
}

export type ViewDefaultsDrawerProps = {
  open: boolean
  onClose: () => void
}

export function ViewDefaultsDrawer({ open, onClose }: ViewDefaultsDrawerProps) {
  const {
    prefs,
    hasStoredPrefs,
    storageBlocked,
    setDefaultFlavor,
    setDensity,
    setAccentTheme,
    setToggle,
    saveDefaults,
    resetToSystemDefaults,
  } = usePreferences()
  const { pushToast } = useToast()
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    if (!open) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <aside
      id="view-defaults-drawer"
      className={styles.drawer}
      role="dialog"
      aria-modal="false"
      aria-label="View Defaults"
    >
      <header className={styles.drawerHeader}>
        <div className={styles.drawerTitle}>
          <h3>View Settings</h3>
          <span>Customize how the center canvas behaves.</span>
        </div>
        <button
          ref={closeButtonRef}
          type="button"
          className={styles.drawerClose}
          onClick={onClose}
          aria-label="Close defaults drawer"
        >
          <X size={14} />
        </button>
      </header>

      <div className={styles.drawerBody}>
        {!hasStoredPrefs ? (
          <div className={styles.drawerBanner}>
            Using system view defaults. Click <strong>Save Defaults</strong> to persist your changes.
          </div>
        ) : null}

        {storageBlocked ? (
          <div className={styles.drawerBannerWatch}>
            Local storage is unavailable. Defaults will not persist across reloads.
          </div>
        ) : null}

        <section className={styles.drawerSection}>
          <span className={styles.drawerLabel}>Default Startup View</span>
          <select
            className={styles.drawerSelect}
            value={prefs.defaultFlavor}
            onChange={(event) => setDefaultFlavor(event.target.value as ViewFlavor)}
            aria-label="Default startup view"
          >
            {FLAVORS.map((flavor) => (
              <option key={flavor.id} value={flavor.id}>
                {flavor.label}
              </option>
            ))}
          </select>
        </section>

        <section className={styles.drawerSection}>
          <span className={styles.drawerLabel}>Canvas Density</span>
          <div className={styles.densityRow}>
            {DENSITIES.map((option) => (
              <button
                type="button"
                key={option.id}
                className={[styles.densityOption, prefs.density === option.id ? styles.densityActive : '']
                  .filter(Boolean)
                  .join(' ')}
                onClick={() => setDensity(option.id)}
                aria-pressed={prefs.density === option.id}
              >
                {option.label}
              </button>
            ))}
          </div>
          <span className={styles.drawerHint}>Density of information shown in the canvas.</span>
        </section>

        <section className={styles.drawerSection}>
          <span className={styles.drawerLabel}>Accent Theme</span>
          <div className={styles.themeRow}>
            {ACCENT_THEMES.map((theme) => {
              const swatch = THEME_SWATCHES[theme.id]
              return (
                <button
                  type="button"
                  key={theme.id}
                  className={[styles.themeOption, prefs.accentTheme === theme.id ? styles.themeActive : '']
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => setAccentTheme(theme.id)}
                  aria-pressed={prefs.accentTheme === theme.id}
                >
                  <span className={styles.themeSwatch}>
                    <span style={{ background: swatch[0] }} />
                    <span style={{ background: swatch[1] }} />
                  </span>
                  <span>{theme.label}</span>
                </button>
              )
            })}
          </div>
          <span className={styles.drawerHint}>Color emphasis for charts, states, and UI.</span>
        </section>

        <section className={styles.drawerSection}>
          <ToggleField
            label="Auto-switch by Workflow"
            hint="Suggest a flavor when workflow signals change."
            value={prefs.autoSwitchByWorkflow}
            onChange={(value) => setToggle('autoSwitchByWorkflow', value)}
          />
          <ToggleField
            label="Pin Emergency Controls"
            hint="Keep operator commands expanded at any width."
            value={prefs.pinEmergencyControls}
            onChange={(value) => setToggle('pinEmergencyControls', value)}
          />
          <ToggleField
            label="Show Evidence Layer"
            hint="Overlay evidence markers on charts and timelines."
            value={prefs.showEvidenceLayer}
            onChange={(value) => setToggle('showEvidenceLayer', value)}
          />
          <ToggleField
            label="Apply to Mission Control"
            hint="Use these defaults when the app first opens."
            value={prefs.applyToMissionControl}
            onChange={(value) => setToggle('applyToMissionControl', value)}
          />
        </section>
      </div>

      <footer className={styles.drawerFooter}>
        <button
          type="button"
          className="btn"
          onClick={() => {
            resetToSystemDefaults()
            pushToast('Reset to system defaults.', 'info')
          }}
        >
          Reset
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            const result = saveDefaults()
            if (!result.ok) {
              pushToast(result.error ?? 'Could not save defaults.', 'risk')
              return
            }
            const defaultFlavor = result.value?.defaultFlavor ?? prefs.defaultFlavor
            const label = FLAVORS.find((flavor) => flavor.id === defaultFlavor)?.label ?? 'Mission Control'
            pushToast(`Saved defaults — startup view: ${label}.`, 'good')
          }}
        >
          Save Defaults
        </button>
      </footer>
    </aside>
  )
}

function ToggleField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string
  hint?: string
  value: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <div className={styles.toggleRow}>
      <div>
        <label>{label}</label>
        {hint ? <span>{hint}</span> : null}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        aria-label={label}
        className={[styles.toggle, value ? styles.toggleOn : ''].filter(Boolean).join(' ')}
        onClick={() => onChange(!value)}
      />
    </div>
  )
}

// Drop-in suppression for a specific lint rule used elsewhere
export type { ToggleKey }
