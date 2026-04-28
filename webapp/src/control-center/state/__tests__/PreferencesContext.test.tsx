import { describe, expect, it, beforeEach, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { useEffect } from 'react'

import {
  PreferencesProvider,
  PREFERENCES_STORAGE_KEY,
  usePreferences,
  validateStoredPreferences,
} from '../PreferencesContext'
import { SYSTEM_DEFAULTS, type ViewFlavorPreferences } from '../types'

function PreferencesProbe({
  onMount,
}: {
  onMount: (api: ReturnType<typeof usePreferences>) => void
}) {
  const api = usePreferences()
  useEffect(() => {
    onMount(api)
  }, [api, onMount])
  return (
    <div>
      <span data-testid="active">{api.prefs.activeFlavor}</span>
      <span data-testid="density">{api.prefs.density}</span>
      <span data-testid="theme">{api.prefs.accentTheme}</span>
      <span data-testid="manual">{String(api.manualOverride)}</span>
      <span data-testid="hasStored">{String(api.hasStoredPrefs)}</span>
    </div>
  )
}

describe('validateStoredPreferences', () => {
  it('returns null when JSON is invalid', () => {
    expect(validateStoredPreferences('not-json')).toBeNull()
  })

  it('returns null when payload is not an object', () => {
    expect(validateStoredPreferences('"hello"')).toBeNull()
    expect(validateStoredPreferences('null')).toBeNull()
  })

  it('substitutes invalid fields with system defaults', () => {
    const value = validateStoredPreferences(
      JSON.stringify({
        activeFlavor: 'unknown-flavor',
        defaultFlavor: 'risk-core',
        density: 'oversize',
        accentTheme: 'plaid',
        autoSwitchByWorkflow: 'maybe',
        pinEmergencyControls: true,
        showEvidenceLayer: false,
        applyToMissionControl: true,
      }),
    )
    expect(value).not.toBeNull()
    const validated = value as ViewFlavorPreferences
    expect(validated.activeFlavor).toBe(SYSTEM_DEFAULTS.activeFlavor)
    expect(validated.defaultFlavor).toBe('risk-core')
    expect(validated.density).toBe(SYSTEM_DEFAULTS.density)
    expect(validated.accentTheme).toBe(SYSTEM_DEFAULTS.accentTheme)
    expect(validated.autoSwitchByWorkflow).toBe(SYSTEM_DEFAULTS.autoSwitchByWorkflow)
    expect(validated.pinEmergencyControls).toBe(true)
    expect(validated.showEvidenceLayer).toBe(false)
  })
})

describe('PreferencesProvider', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.restoreAllMocks()
  })

  it('falls back to system defaults when no preferences are stored', () => {
    render(
      <PreferencesProvider>
        <PreferencesProbe onMount={() => undefined} />
      </PreferencesProvider>,
    )
    expect(screen.getByTestId('active').textContent).toBe(SYSTEM_DEFAULTS.activeFlavor)
    expect(screen.getByTestId('density').textContent).toBe(SYSTEM_DEFAULTS.density)
    expect(screen.getByTestId('theme').textContent).toBe(SYSTEM_DEFAULTS.accentTheme)
    expect(screen.getByTestId('hasStored').textContent).toBe('false')
  })

  it('loads valid stored preferences and starts on the default flavor', () => {
    window.localStorage.setItem(
      PREFERENCES_STORAGE_KEY,
      JSON.stringify({
        ...SYSTEM_DEFAULTS,
        defaultFlavor: 'risk-core',
        density: 'compact',
        accentTheme: 'green-gray',
      }),
    )
    render(
      <PreferencesProvider>
        <PreferencesProbe onMount={() => undefined} />
      </PreferencesProvider>,
    )
    expect(screen.getByTestId('active').textContent).toBe('risk-core')
    expect(screen.getByTestId('density').textContent).toBe('compact')
    expect(screen.getByTestId('theme').textContent).toBe('green-gray')
    expect(screen.getByTestId('hasStored').textContent).toBe('true')
  })

  it('migrates legacy Market Chart startup preferences to Mission Control', () => {
    window.localStorage.setItem(
      PREFERENCES_STORAGE_KEY,
      JSON.stringify({
        ...SYSTEM_DEFAULTS,
        activeFlavor: 'market-chart',
        defaultFlavor: 'market-chart',
        density: 'compact',
      }),
    )
    render(
      <PreferencesProvider>
        <PreferencesProbe onMount={() => undefined} />
      </PreferencesProvider>,
    )
    expect(screen.getByTestId('active').textContent).toBe('mission-control')
    expect(screen.getByTestId('density').textContent).toBe('compact')
    expect(screen.getByTestId('hasStored').textContent).toBe('true')
  })

  it('drops invalid stored preferences and applies system defaults silently', () => {
    window.localStorage.setItem(PREFERENCES_STORAGE_KEY, '{not valid JSON')
    render(
      <PreferencesProvider>
        <PreferencesProbe onMount={() => undefined} />
      </PreferencesProvider>,
    )
    expect(screen.getByTestId('active').textContent).toBe(SYSTEM_DEFAULTS.activeFlavor)
    expect(screen.getByTestId('density').textContent).toBe(SYSTEM_DEFAULTS.density)
    expect(screen.getByTestId('hasStored').textContent).toBe('false')
  })

  it('marks manual override when setActiveFlavor is called manually', () => {
    let api: ReturnType<typeof usePreferences> | null = null
    render(
      <PreferencesProvider>
        <PreferencesProbe
          onMount={(value) => {
            api = value
          }}
        />
      </PreferencesProvider>,
    )
    expect(screen.getByTestId('manual').textContent).toBe('false')
    act(() => {
      api!.setActiveFlavor('strategy-forge', 'manual')
    })
    expect(screen.getByTestId('active').textContent).toBe('strategy-forge')
    expect(screen.getByTestId('manual').textContent).toBe('true')
    act(() => {
      api!.resumeAutoSwitch()
    })
    expect(screen.getByTestId('manual').textContent).toBe('false')
  })

  it('does not mark manual override when setActiveFlavor source is auto', () => {
    let api: ReturnType<typeof usePreferences> | null = null
    render(
      <PreferencesProvider>
        <PreferencesProbe
          onMount={(value) => {
            api = value
          }}
        />
      </PreferencesProvider>,
    )
    act(() => {
      api!.setActiveFlavor('risk-core', 'auto')
    })
    expect(screen.getByTestId('active').textContent).toBe('risk-core')
    expect(screen.getByTestId('manual').textContent).toBe('false')
  })

  it('persists defaults to localStorage on save', () => {
    let api: ReturnType<typeof usePreferences> | null = null
    render(
      <PreferencesProvider>
        <PreferencesProbe
          onMount={(value) => {
            api = value
          }}
        />
      </PreferencesProvider>,
    )
    act(() => {
      api!.setDefaultFlavor('portfolio-constellation')
      api!.setDensity('cinematic')
      api!.setAccentTheme('purple-teal')
    })
    let result: { ok: boolean; value?: ViewFlavorPreferences } = { ok: false }
    act(() => {
      result = api!.saveDefaults()
    })
    expect(result.ok).toBe(true)
    expect(result.value?.defaultFlavor).toBe('portfolio-constellation')
    const raw = window.localStorage.getItem(PREFERENCES_STORAGE_KEY)
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw!)
    expect(parsed.defaultFlavor).toBe('portfolio-constellation')
    expect(parsed.density).toBe('cinematic')
    expect(parsed.accentTheme).toBe('purple-teal')
  })

  it('clears defaults on resetToSystemDefaults', () => {
    window.localStorage.setItem(
      PREFERENCES_STORAGE_KEY,
      JSON.stringify({ ...SYSTEM_DEFAULTS, density: 'compact' }),
    )
    let api: ReturnType<typeof usePreferences> | null = null
    render(
      <PreferencesProvider>
        <PreferencesProbe
          onMount={(value) => {
            api = value
          }}
        />
      </PreferencesProvider>,
    )
    act(() => {
      api!.resetToSystemDefaults()
    })
    expect(screen.getByTestId('density').textContent).toBe(SYSTEM_DEFAULTS.density)
    expect(window.localStorage.getItem(PREFERENCES_STORAGE_KEY)).toBeNull()
  })

  it('reports save failure when localStorage throws', () => {
    const setItemSpy = vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded')
    })
    try {
      let api: ReturnType<typeof usePreferences> | null = null
      render(
        <PreferencesProvider>
          <PreferencesProbe
            onMount={(value) => {
              api = value
            }}
          />
        </PreferencesProvider>,
      )
      let result: { ok: boolean; error?: string } = { ok: true }
      act(() => {
        result = api!.saveDefaults()
      })
      expect(result.ok).toBe(false)
      expect(result.error).toMatch(/quota|storage/i)
    } finally {
      setItemSpy.mockRestore()
    }
  })
})
