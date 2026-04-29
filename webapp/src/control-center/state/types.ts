export type ViewFlavor =
  | 'mission-control'
  | 'market-chart'
  | 'strategy-forge'
  | 'market-day-ops'
  | 'risk-core'
  | 'portfolio-constellation'
  | 'evidence-replay'

export type CanvasDensity = 'compact' | 'balanced' | 'cinematic'

export type AccentTheme = 'blue-red' | 'cyan-amber' | 'purple-teal' | 'green-gray'

export type ViewFlavorPreferences = {
  activeFlavor: ViewFlavor
  defaultFlavor: ViewFlavor
  density: CanvasDensity
  accentTheme: AccentTheme
  autoSwitchByWorkflow: boolean
  pinEmergencyControls: boolean
  showEvidenceLayer: boolean
  applyToMissionControl: boolean
}

export const SYSTEM_DEFAULTS: ViewFlavorPreferences = {
  activeFlavor: 'mission-control',
  defaultFlavor: 'mission-control',
  density: 'balanced',
  accentTheme: 'blue-red',
  autoSwitchByWorkflow: true,
  pinEmergencyControls: true,
  showEvidenceLayer: true,
  applyToMissionControl: true,
}

export type FlavorDepth = 'full' | 'v1' | 'v1-sparse'

export type FlavorMeta = {
  id: ViewFlavor
  label: string
  subtitle: string
  shortcut: string
  index: number
  depth: FlavorDepth
}

export const FLAVORS: ReadonlyArray<FlavorMeta> = [
  {
    id: 'mission-control',
    label: 'Mission Control',
    subtitle: 'Status, safety & attention',
    shortcut: 'Cmd+1',
    index: 1,
    depth: 'full',
  },
  {
    id: 'market-chart',
    label: 'Portfolio Graphs',
    subtitle: 'Equity, cash, exposure & benchmarks',
    shortcut: 'Cmd+2',
    index: 2,
    depth: 'full',
  },
  {
    id: 'strategy-forge',
    label: 'Strategy Quality',
    subtitle: 'Research, evidence & degradation',
    shortcut: 'Cmd+3',
    index: 3,
    depth: 'v1',
  },
  {
    id: 'market-day-ops',
    label: 'Paper Trading',
    subtitle: 'Runtime, orders & session flow',
    shortcut: 'Cmd+4',
    index: 4,
    depth: 'full',
  },
  {
    id: 'risk-core',
    label: 'Risk & Safety',
    subtitle: 'Limits, gates & operator controls',
    shortcut: 'Cmd+5',
    index: 5,
    depth: 'full',
  },
  {
    id: 'portfolio-constellation',
    label: 'Open Risk',
    subtitle: 'Allocation, concentration & exposure',
    shortcut: 'Cmd+6',
    index: 6,
    depth: 'v1-sparse',
  },
  {
    id: 'evidence-replay',
    label: 'Evidence & Why',
    subtitle: 'Audit trail, replay & trust',
    shortcut: 'Cmd+7',
    index: 7,
    depth: 'v1',
  },
]

export const ACCENT_THEMES: ReadonlyArray<{ id: AccentTheme; label: string }> = [
  { id: 'blue-red', label: 'Blue / Red' },
  { id: 'cyan-amber', label: 'Cyan / Amber' },
  { id: 'purple-teal', label: 'Purple / Teal' },
  { id: 'green-gray', label: 'Green / Gray' },
]

export const DENSITIES: ReadonlyArray<{ id: CanvasDensity; label: string }> = [
  { id: 'compact', label: 'Compact' },
  { id: 'balanced', label: 'Balanced' },
  { id: 'cinematic', label: 'Cinematic' },
]

export type AutoSwitchReason =
  | 'pre-open-checklist'
  | 'risk-incident'
  | 'gate-fail'
  | 'strategy-proposal'
  | 'replay-route'
  | 'portfolio-route'
  | 'mission-control'
  | 'normal-supervision'

export type AutoSwitchSuggestion = {
  flavor: ViewFlavor
  reason: AutoSwitchReason
  detail: string
}
