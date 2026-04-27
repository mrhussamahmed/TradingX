import type { ReactNode } from 'react'

import styles from './Flavor.module.css'

export type FlavorPlaceholderProps = {
  title: string
  subtitle: string
  children?: ReactNode
}

export function FlavorPlaceholder({ title, subtitle, children }: FlavorPlaceholderProps) {
  return (
    <section className={styles.flavorPlaceholder}>
      <div>
        <h2>{title}</h2>
        <p style={{ color: 'var(--text-muted)', margin: '4px 0 0', fontSize: 12 }}>{subtitle}</p>
      </div>
      {children}
    </section>
  )
}
