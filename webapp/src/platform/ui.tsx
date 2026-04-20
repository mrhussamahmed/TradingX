import type { ReactNode } from 'react'

import { cx } from './format'

export function Panel(props: {
  title: string
  eyebrow?: string
  actions?: ReactNode
  className?: string
  children: ReactNode
}) {
  return (
    <section className={cx('surface-panel', props.className)}>
      <header className="surface-panel-header">
        <div>
          {props.eyebrow ? <p className="panel-eyebrow">{props.eyebrow}</p> : null}
          <h2>{props.title}</h2>
        </div>
        {props.actions ? <div className="panel-actions">{props.actions}</div> : null}
      </header>
      {props.children}
    </section>
  )
}

export function StatusBadge(props: { label: string; tone: 'neutral' | 'good' | 'watch' | 'risk' | 'info' }) {
  return <span className={cx('status-badge', `tone-${props.tone}`)}>{props.label}</span>
}

export function EmptyState(props: { title: string; detail: string }) {
  return (
    <div className="empty-state">
      <strong>{props.title}</strong>
      <p>{props.detail}</p>
    </div>
  )
}

export function KeyValueList(props: { items: Array<{ label: string; value: string }> }) {
  return (
    <div className="key-value-list">
      {props.items.map((item) => (
        <div key={`${item.label}-${item.value}`} className="key-value-row">
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  )
}

export function ActionButton(props: {
  label: string
  onClick: () => void
  variant?: 'primary' | 'secondary' | 'ghost'
}) {
  return (
    <button
      type="button"
      className={cx('action-button', props.variant ?? 'secondary')}
      onClick={props.onClick}
    >
      {props.label}
    </button>
  )
}
