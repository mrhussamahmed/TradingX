import styles from './Shell.module.css'

export function Brand() {
  return (
    <div className={styles.brandRow} aria-label="TradeX">
      <span className={styles.brandWordmark}>
        Trade<span>X</span>
      </span>
    </div>
  )
}
