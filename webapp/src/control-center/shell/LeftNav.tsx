import { useEffect, useState } from 'react'
import {
  Activity,
  Bell,
  BookOpen,
  CalendarClock,
  CircleCheck,
  Cpu,
  FileEdit,
  FileText,
  FlaskConical,
  FlaskRound,
  GitBranch,
  PieChart,
  Server,
  Settings,
  Shield,
} from 'lucide-react'

import type { ConfigSummary } from '../../types'
import { usePreferences } from '../state/PreferencesContext'
import type { ViewFlavor } from '../state/types'

import styles from './Shell.module.css'

type NavId =
  | 'mission-control'
  | 'runtime-host'
  | 'paper-only'
  | 'gate3-readiness'
  | 'portfolio'
  | 'strategies'
  | 'proposal-studio'
  | 'scheduler'
  | 'evidence'
  | 'alerts'
  | 'reports'
  | 'research'
  | 'settings'
  | 'system'

type IconType = typeof Activity

type NavItem = {
  id: NavId
  label: string
  icon: IconType
  flavor: ViewFlavor | null
  group: 'primary' | 'expansion'
}

const NAV_ITEMS: ReadonlyArray<NavItem> = [
  { id: 'mission-control', label: 'Mission Control', icon: Activity, flavor: null, group: 'primary' },
  { id: 'runtime-host', label: 'Runtime Host', icon: Cpu, flavor: 'market-day-ops', group: 'primary' },
  { id: 'paper-only', label: 'Paper Only', icon: Shield, flavor: null, group: 'primary' },
  { id: 'gate3-readiness', label: 'Gate 3 Readiness', icon: CircleCheck, flavor: 'risk-core', group: 'primary' },
  { id: 'portfolio', label: 'Portfolio', icon: PieChart, flavor: 'portfolio-constellation', group: 'primary' },
  { id: 'strategies', label: 'Strategies', icon: GitBranch, flavor: 'strategy-forge', group: 'primary' },
  { id: 'proposal-studio', label: 'Proposal Studio', icon: FileEdit, flavor: 'strategy-forge', group: 'primary' },
  { id: 'scheduler', label: 'Scheduler', icon: CalendarClock, flavor: 'market-day-ops', group: 'primary' },
  { id: 'evidence', label: 'Evidence', icon: BookOpen, flavor: 'evidence-replay', group: 'expansion' },
  { id: 'alerts', label: 'Alerts', icon: Bell, flavor: 'risk-core', group: 'expansion' },
  { id: 'reports', label: 'Reports', icon: FileText, flavor: 'evidence-replay', group: 'expansion' },
  { id: 'research', label: 'Research', icon: FlaskConical, flavor: 'strategy-forge', group: 'expansion' },
  { id: 'settings', label: 'Settings', icon: Settings, flavor: null, group: 'expansion' },
  { id: 'system', label: 'System', icon: Server, flavor: null, group: 'expansion' },
]

const CANONICAL_FOR_FLAVOR: Record<ViewFlavor, NavId> = {
  'market-chart': 'mission-control',
  'strategy-forge': 'strategies',
  'market-day-ops': 'scheduler',
  'risk-core': 'gate3-readiness',
  'portfolio-constellation': 'portfolio',
  'evidence-replay': 'evidence',
}

export type LeftNavProps = {
  onOpenSettings: () => void
  configSummary: ConfigSummary
  alertCount: number
}

export function LeftNav({ onOpenSettings, configSummary, alertCount }: LeftNavProps) {
  const { prefs, setActiveFlavor } = usePreferences()
  const [selectedId, setSelectedId] = useState<NavId>(CANONICAL_FOR_FLAVOR[prefs.activeFlavor])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedId((current) => {
      const currentItem = NAV_ITEMS.find((item) => item.id === current)
      if (!currentItem || currentItem.flavor === null) {
        return current
      }
      if (currentItem.flavor === prefs.activeFlavor) {
        return current
      }
      return CANONICAL_FOR_FLAVOR[prefs.activeFlavor]
    })
  }, [prefs.activeFlavor])

  function handleNav(item: NavItem) {
    setSelectedId(item.id)
    if (item.id === 'settings') {
      onOpenSettings()
      return
    }
    if (item.flavor && item.flavor !== prefs.activeFlavor) {
      setActiveFlavor(item.flavor, 'manual')
    }
  }

  const primary = NAV_ITEMS.filter((item) => item.group === 'primary')
  const expansion = NAV_ITEMS.filter((item) => item.group === 'expansion')

  const tradingMode = configSummary.live_disable_report.paper_only_mode ? 'Paper Only' : 'Live Check'
  const writeMode = configSummary.config.web_write_mode_enabled ? 'Writes Enabled' : 'Read Only'

  return (
    <aside className={styles.leftNav} aria-label="Primary navigation">
      <nav>
        {primary.map((item) => (
          <NavRow
            key={item.id}
            item={item}
            active={selectedId === item.id}
            onClick={() => handleNav(item)}
          />
        ))}
        <div className={styles.navHeader}>Expansion</div>
        {expansion.map((item) => (
          <NavRow
            key={item.id}
            item={item}
            active={selectedId === item.id}
            badge={item.id === 'alerts' && alertCount > 0 ? alertCount : undefined}
            onClick={() => handleNav(item)}
          />
        ))}
      </nav>

      <div className={styles.envCard}>
        <span className={styles.envCardLabel}>Environment</span>
        <span className={styles.envCardValue}>
          <FlaskRound size={14} />
          {tradingMode}
          <span className={configSummary.live_disable_report.paper_only_mode ? 'dot dot-good' : 'dot dot-watch'} />
        </span>
        <span className={styles.envCardSub}>{writeMode}</span>
        {configSummary.live_disable_report.manual_kill_switch_active ? (
          <span className={styles.envCardSub} style={{ color: 'var(--risk)' }}>
            Kill switch active
          </span>
        ) : null}
      </div>
    </aside>
  )
}

function NavRow({
  item,
  active,
  badge,
  onClick,
}: {
  item: NavItem
  active: boolean
  badge?: number
  onClick: () => void
}) {
  const Icon = item.icon
  return (
    <button
      type="button"
      onClick={onClick}
      className={[styles.navItem, active ? styles.navItemActive : ''].filter(Boolean).join(' ')}
      aria-current={active ? 'page' : undefined}
      data-nav-id={item.id}
    >
      <Icon className={styles.navIcon} aria-hidden />
      <span>{item.label}</span>
      {badge ? <span className={styles.navBadge}>{badge}</span> : null}
    </button>
  )
}
