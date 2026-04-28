import { PulseRouteLogo } from './PulseRouteLogo'
import styles from './Shell.module.css'

export function Brand() {
  return (
    <div className={styles.brandRow} aria-label="TradeX">
      <PulseRouteLogo variant="wordmark" />
    </div>
  )
}
