import styles from './Shell.module.css'

type PulseRouteLogoProps = {
  variant: 'wordmark' | 'glyph'
}

export function PulseRouteLogo({ variant }: PulseRouteLogoProps) {
  if (variant === 'glyph') {
    return (
      <svg
        className={`${styles.pulseRouteLogo} ${styles.pulseRouteGlyph}`}
        role="img"
        aria-label="Pulse Route TradeX glyph"
        viewBox="0 0 96 44"
        focusable="false"
      >
        <path className={styles.pulseRouteLine} d="M2 25h27L39 6l12 32 8-13h15" />
        <path className={styles.pulseRouteX} d="M73 14 94 34M94 14 73 34" />
      </svg>
    )
  }

  return (
    <svg
      className={`${styles.pulseRouteLogo} ${styles.pulseRouteWordmark}`}
      role="img"
      aria-label="Pulse Route TradeX wordmark"
      viewBox="0 0 196 44"
      focusable="false"
    >
      <path className={styles.pulseRouteLine} d="M2 25h27L39 6l12 32 8-13h15" />
      <path className={styles.pulseRouteX} d="M73 14 94 34M94 14 73 34" />
      <text className={styles.pulseRouteText} x="106" y="30">
        Trade
      </text>
      <text className={`${styles.pulseRouteText} ${styles.pulseRouteTextAccent}`} x="176" y="30">
        X
      </text>
    </svg>
  )
}
