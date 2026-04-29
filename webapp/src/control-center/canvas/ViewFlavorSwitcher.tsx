import type { ReactNode } from 'react'
import { Check } from 'lucide-react'

import { FLAVORS, type ViewFlavor } from '../state/types'
import { usePreferences } from '../state/PreferencesContext'

import styles from './Canvas.module.css'

const THUMBS: Record<ViewFlavor, ReactNode> = {
  'mission-control': (
    <div className={styles.thumbForge}>
      <span />
      <span />
      <span />
      <span />
      <span />
      <span />
    </div>
  ),
  'market-chart': (
    <div className={styles.thumbChart}>
      {[6, 10, 7, 13, 9, 15, 11, 18, 14, 20, 16, 22, 18, 24].map((h, i) => (
        <span key={i} style={{ height: `${h}px` }} />
      ))}
    </div>
  ),
  'strategy-forge': (
    <div className={styles.thumbForge}>
      {Array.from({ length: 9 }, (_, i) => (
        <span key={i} />
      ))}
    </div>
  ),
  'market-day-ops': (
    <div className={styles.thumbDay}>
      {Array.from({ length: 6 }, (_, i) => (
        <span key={i} />
      ))}
    </div>
  ),
  'risk-core': (
    <div className={styles.thumbRisk}>
      <span />
      <span />
      <span />
      <i />
    </div>
  ),
  'portfolio-constellation': (
    <div className={styles.thumbConst}>
      <span />
      <span />
      <span />
      <span />
      <span />
    </div>
  ),
  'evidence-replay': (
    <div className={styles.thumbReplay}>
      {Array.from({ length: 4 }, (_, i) => (
        <span key={i} />
      ))}
    </div>
  ),
}

export function ViewFlavorSwitcher() {
  const { prefs, setActiveFlavor } = usePreferences()
  return (
    <div className={styles.flavorBar} role="tablist" aria-label="Center canvas view flavor">
      {FLAVORS.map((flavor) => {
        const active = prefs.activeFlavor === flavor.id
        return (
          <button
            type="button"
            key={flavor.id}
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            className={[styles.flavorCard, active ? styles.flavorActive : ''].filter(Boolean).join(' ')}
            onClick={() => setActiveFlavor(flavor.id, 'manual')}
            data-flavor-id={flavor.id}
          >
            <div className={styles.flavorIndex}>
              <span>{flavor.index}</span>
              <span aria-hidden>•</span>
              <span className="kbd" style={{ height: 16 }}>
                {flavor.shortcut}
              </span>
              <span className={styles.flavorCheck} aria-hidden>
                <Check size={10} strokeWidth={3} />
              </span>
            </div>
            <div className={styles.flavorThumb}>{THUMBS[flavor.id]}</div>
            <div>
              <div className={styles.flavorTitle}>{flavor.label}</div>
              <div className={styles.flavorSub}>
                {flavor.subtitle}
                {flavor.depth === 'v1' ? ' · v1' : flavor.depth === 'v1-sparse' ? ' · v1 (sparse)' : ''}
              </div>
            </div>
          </button>
        )
      })}
    </div>
  )
}
