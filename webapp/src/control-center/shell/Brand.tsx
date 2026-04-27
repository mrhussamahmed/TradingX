import styles from './Shell.module.css'

export function Brand() {
  return (
    <div className={styles.brandRow} aria-label="TradeX">
      <div className={styles.brandMark} aria-hidden>
        TX
      </div>
      <div className={styles.brandText}>
        Trade<em>X</em>
      </div>
    </div>
  )
}
