import { useEffect, useRef, useState } from 'react'

import { toCurrency } from '../../platform/format'
import type { PortfolioPositionRow } from '../../types'

import { ConfirmDialog } from './ConfirmDialog'
import styles from './Dialog.module.css'

export const FLATTEN_PHRASE = 'FLATTEN ALL'

export type FlattenAllDialogProps = {
  open: boolean
  onClose: () => void
  onConfirm: () => void
  busy?: boolean
  flattenEndpointSupported: boolean
  positions: PortfolioPositionRow[]
}

export function FlattenAllDialog({
  open,
  onClose,
  onConfirm,
  busy,
  flattenEndpointSupported,
  positions,
}: FlattenAllDialogProps) {
  const [phrase, setPhrase] = useState('')
  const [touched, setTouched] = useState(false)
  const inputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (!open) {
      setPhrase('') // eslint-disable-line react-hooks/set-state-in-effect
      setTouched(false)
      return
    }
    const id = window.setTimeout(() => inputRef.current?.focus(), 50)
    return () => window.clearTimeout(id)
  }, [open])

  const phraseMatch = phrase === FLATTEN_PHRASE
  const phraseInvalid = touched && !phraseMatch
  const hasPositions = positions.length > 0

  const disabledReason = !flattenEndpointSupported
    ? 'Flatten All backend endpoint is not implemented yet. Use the documented closeout runbook to flatten positions outside the operator UI.'
    : !hasPositions
      ? 'No open positions to flatten.'
      : !phraseMatch
        ? `Type ${FLATTEN_PHRASE} to confirm.`
        : undefined

  return (
    <ConfirmDialog
      open={open}
      tone="watch"
      title="Flatten all open positions"
      subtitle="Submit market closeout orders for every active position."
      confirmLabel="Flatten All"
      confirmDisabled={!flattenEndpointSupported || !hasPositions || !phraseMatch}
      confirmDisabledReason={disabledReason}
      onConfirm={() => {
        if (!phraseMatch) {
          setTouched(true)
          return
        }
        onConfirm()
      }}
      onClose={onClose}
      busy={busy}
    >
      <p style={{ margin: 0 }}>
        This will:
      </p>
      <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--text-secondary)' }}>
        <li>Submit a market closeout for each open position.</li>
        <li>Pause the runtime host until all closeouts confirm.</li>
        <li>Record a closeout incident for evidence.</li>
      </ul>

      {hasPositions ? (
        <div className={styles.affectedTable}>
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Quantity</th>
                <th>Market Value</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => (
                <tr key={position.symbol}>
                  <td>{position.symbol}</td>
                  <td className="numeric">{position.quantity}</td>
                  <td className="numeric">
                    {position.market_value ? toCurrency(position.market_value) : '—'}
                  </td>
                  <td>{position.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className={`${styles.warningCallout} ${styles.warningCalloutWatch}`}>
          <span>No open positions are currently recorded.</span>
        </div>
      )}

      <div className={styles.confirmField}>
        <label className={styles.confirmFieldLabel} htmlFor="flatten-all-phrase">
          Type {FLATTEN_PHRASE} to confirm
        </label>
        <input
          ref={inputRef}
          id="flatten-all-phrase"
          type="text"
          autoComplete="off"
          spellCheck={false}
          className={[styles.confirmInput, phraseInvalid ? styles.confirmInputError : '']
            .filter(Boolean)
            .join(' ')}
          value={phrase}
          onChange={(event) => {
            setPhrase(event.target.value)
            setTouched(true)
          }}
          onBlur={() => setTouched(true)}
          aria-invalid={phraseInvalid}
        />
        <span className={styles.confirmHint}>The phrase is case-sensitive.</span>
      </div>
    </ConfirmDialog>
  )
}
