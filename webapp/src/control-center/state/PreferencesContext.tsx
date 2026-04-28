import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import {
  FLAVORS,
  SYSTEM_DEFAULTS,
  type AccentTheme,
  type CanvasDensity,
  type ViewFlavor,
  type ViewFlavorPreferences,
} from './types'

export const PREFERENCES_STORAGE_KEY = 'tradingx.viewFlavor.preferences'
const PREFERENCES_SCHEMA_VERSION = 2

export type ToggleKey =
  | 'autoSwitchByWorkflow'
  | 'pinEmergencyControls'
  | 'showEvidenceLayer'
  | 'applyToMissionControl'

export type PreferencesContextValue = {
  prefs: ViewFlavorPreferences
  saved: ViewFlavorPreferences
  manualOverride: boolean
  hasStoredPrefs: boolean
  storageBlocked: boolean
  setActiveFlavor: (flavor: ViewFlavor, source: 'manual' | 'auto') => void
  setDefaultFlavor: (flavor: ViewFlavor) => void
  setDensity: (density: CanvasDensity) => void
  setAccentTheme: (theme: AccentTheme) => void
  setToggle: (key: ToggleKey, value: boolean) => void
  saveDefaults: () => { ok: boolean; value?: ViewFlavorPreferences; error?: string }
  resetToSystemDefaults: () => void
  resumeAutoSwitch: () => void
}

const PreferencesContext = createContext<PreferencesContextValue | null>(null)

function isViewFlavor(value: unknown): value is ViewFlavor {
  return typeof value === 'string' && FLAVORS.some((flavor) => flavor.id === value)
}

function isDensity(value: unknown): value is CanvasDensity {
  return value === 'compact' || value === 'balanced' || value === 'cinematic'
}

function isTheme(value: unknown): value is AccentTheme {
  return (
    value === 'blue-red' ||
    value === 'cyan-amber' ||
    value === 'purple-teal' ||
    value === 'green-gray'
  )
}

function readBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback
}

// eslint-disable-next-line react-refresh/only-export-components
export function validateStoredPreferences(raw: string): ViewFlavorPreferences | null {
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') {
      return null
    }
    const candidate = parsed as Partial<ViewFlavorPreferences>
    const schemaVersion =
      'schemaVersion' in candidate && typeof candidate.schemaVersion === 'number'
        ? candidate.schemaVersion
        : null
    const isLegacyMarketChartDefault =
      schemaVersion === null &&
      candidate.defaultFlavor === 'market-chart' &&
      (!candidate.activeFlavor || candidate.activeFlavor === 'market-chart')
    return {
      activeFlavor: isLegacyMarketChartDefault
        ? SYSTEM_DEFAULTS.activeFlavor
        : isViewFlavor(candidate.activeFlavor)
        ? candidate.activeFlavor
        : SYSTEM_DEFAULTS.activeFlavor,
      defaultFlavor: isLegacyMarketChartDefault
        ? SYSTEM_DEFAULTS.defaultFlavor
        : isViewFlavor(candidate.defaultFlavor)
        ? candidate.defaultFlavor
        : SYSTEM_DEFAULTS.defaultFlavor,
      density: isDensity(candidate.density)
        ? candidate.density
        : SYSTEM_DEFAULTS.density,
      accentTheme: isTheme(candidate.accentTheme)
        ? candidate.accentTheme
        : SYSTEM_DEFAULTS.accentTheme,
      autoSwitchByWorkflow: readBoolean(
        candidate.autoSwitchByWorkflow,
        SYSTEM_DEFAULTS.autoSwitchByWorkflow,
      ),
      pinEmergencyControls: readBoolean(
        candidate.pinEmergencyControls,
        SYSTEM_DEFAULTS.pinEmergencyControls,
      ),
      showEvidenceLayer: readBoolean(
        candidate.showEvidenceLayer,
        SYSTEM_DEFAULTS.showEvidenceLayer,
      ),
      applyToMissionControl: readBoolean(
        candidate.applyToMissionControl,
        SYSTEM_DEFAULTS.applyToMissionControl,
      ),
    }
  } catch {
    return null
  }
}

function loadStoredPrefs(): { value: ViewFlavorPreferences | null; storageBlocked: boolean } {
  if (typeof window === 'undefined') {
    return { value: null, storageBlocked: false }
  }
  try {
    const raw = window.localStorage.getItem(PREFERENCES_STORAGE_KEY)
    if (!raw) {
      return { value: null, storageBlocked: false }
    }
    return { value: validateStoredPreferences(raw), storageBlocked: false }
  } catch {
    return { value: null, storageBlocked: true }
  }
}

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [initialLoad] = useState<{
    value: ViewFlavorPreferences | null
    storageBlocked: boolean
  }>(loadStoredPrefs)
  const hasStoredPrefs = initialLoad.value !== null
  const baseline = initialLoad.value ?? SYSTEM_DEFAULTS

  const [prefs, setPrefs] = useState<ViewFlavorPreferences>(() => ({
    ...baseline,
    activeFlavor: baseline.defaultFlavor,
  }))
  const [saved, setSaved] = useState<ViewFlavorPreferences>(() => baseline)
  const [manualOverride, setManualOverride] = useState(false)
  const [storageBlocked, setStorageBlocked] = useState(() => initialLoad.storageBlocked)
  const prefsRef = useRef(prefs)

  useEffect(() => {
    prefsRef.current = prefs
  }, [prefs])

  useEffect(() => {
    if (typeof document === 'undefined') {
      return
    }
    document.documentElement.dataset.theme = prefs.accentTheme
    document.documentElement.dataset.density = prefs.density
  }, [prefs.accentTheme, prefs.density])

  const setActiveFlavor = useCallback(
    (flavor: ViewFlavor, source: 'manual' | 'auto') => {
      setPrefs((current) => (current.activeFlavor === flavor ? current : { ...current, activeFlavor: flavor }))
      if (source === 'manual') {
        setManualOverride(true)
      }
    },
    [],
  )

  const setDefaultFlavor = useCallback((flavor: ViewFlavor) => {
    setPrefs((current) => ({ ...current, defaultFlavor: flavor }))
  }, [])

  const setDensity = useCallback((density: CanvasDensity) => {
    setPrefs((current) => ({ ...current, density }))
  }, [])

  const setAccentTheme = useCallback((accentTheme: AccentTheme) => {
    setPrefs((current) => ({ ...current, accentTheme }))
  }, [])

  const setToggle = useCallback<PreferencesContextValue['setToggle']>((key, value) => {
    setPrefs((current) => ({ ...current, [key]: value }))
  }, [])

  const saveDefaults = useCallback<PreferencesContextValue['saveDefaults']>(() => {
    const current = prefsRef.current
    const persistShape: ViewFlavorPreferences = {
      ...current,
      activeFlavor: current.defaultFlavor,
    }
    try {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(
          PREFERENCES_STORAGE_KEY,
          JSON.stringify({ ...persistShape, schemaVersion: PREFERENCES_SCHEMA_VERSION }),
        )
      }
      setSaved(persistShape)
      setStorageBlocked(false)
      return { ok: true, value: persistShape }
    } catch (error) {
      setStorageBlocked(true)
      return {
        ok: false,
        error:
          error instanceof Error
            ? error.message
            : 'Local storage unavailable; defaults could not be saved.',
      }
    }
  }, [])

  const resetToSystemDefaults = useCallback(() => {
    const reset: ViewFlavorPreferences = { ...SYSTEM_DEFAULTS }
    setPrefs(reset)
    setSaved(reset)
    setManualOverride(false)
    try {
      if (typeof window !== 'undefined') {
        window.localStorage.removeItem(PREFERENCES_STORAGE_KEY)
        setStorageBlocked(false)
      }
    } catch {
      setStorageBlocked(true)
    }
  }, [])

  const resumeAutoSwitch = useCallback(() => {
    setManualOverride(false)
  }, [])

  const value = useMemo<PreferencesContextValue>(
    () => ({
      prefs,
      saved,
      manualOverride,
      hasStoredPrefs,
      storageBlocked,
      setActiveFlavor,
      setDefaultFlavor,
      setDensity,
      setAccentTheme,
      setToggle,
      saveDefaults,
      resetToSystemDefaults,
      resumeAutoSwitch,
    }),
    [
      prefs,
      saved,
      manualOverride,
      hasStoredPrefs,
      storageBlocked,
      setActiveFlavor,
      setDefaultFlavor,
      setDensity,
      setAccentTheme,
      setToggle,
      saveDefaults,
      resetToSystemDefaults,
      resumeAutoSwitch,
    ],
  )

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function usePreferences() {
  const ctx = useContext(PreferencesContext)
  if (!ctx) {
    throw new Error('usePreferences must be used inside PreferencesProvider')
  }
  return ctx
}
