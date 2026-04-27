import { useEffect, useRef, useState } from 'react'

import { ConfirmDialog } from './ConfirmDialog'
import styles from './Dialog.module.css'

export const KILL_SWITCH_PHRASE = 'KILL TRADINGX'

export type KillSwitchDialogProps = {
  open: boolean
  onClose: () => void
  onConfirm: () => void
  busy?: boolean
  killEndpointSupported: boolean
  killSwitchAlreadyActive: boolean
  affectedSummary: { activeSymbols: string[]; runtimeStatus: string }
}

export function KillSwitchDialog({
  open,
  onClose,
  onConfirm,
  busy,
  killEndpointSupported,
  killSwitchAlreadyActive,
  affectedSummary,
}: KillSwitchDialogProps) {
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

  const phraseMatch = phrase === KILL_SWITCH_PHRASE
  const phraseInvalid = touched && !phraseMatch
  const disabledReason = !killEndpointSupported
    ? 'Kill Switch backend endpoint is not implemented yet. Use the documented runbook to activate kill state outside the operator UI.'
    : killSwitchAlreadyActive
      ? 'Kill switch is already active.'
      : !phraseMatch
        ? `Type ${KILL_SWITCH_PHRASE} to confirm.`
        : undefined

  return (
    <ConfirmDialog
      open={open}
      tone="risk"
      title="Activate Kill Switch"
      subtitle="Halts the runtime, blocks new orders, and writes a kill-switch incident."
      confirmLabel="Activate Kill Switch"
      confirmDisabled={
        !killEndpointSupported || killSwitchAlreadyActive || !phraseMatch
      }
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
        <li>Stop the runtime host immediately.</li>
        <li>Block all new order submissions.</li>
        <li>Mark the runtime as halted.</li>
        <li>Record a kill-switch incident with operator attribution.</li>
      </ul>

      <div className={`${styles.warningCallout}`}>
        <span>
          Runtime is currently <strong>{affectedSummary.runtimeStatus}</strong>
          {affectedSummary.activeSymbols.length > 0
            ? ` covering ${affectedSummary.activeSymbols.join(', ')}.`
            : ' with no active symbols.'}
        </span>
      </div>

      <div className={styles.confirmField}>
        <label className={styles.confirmFieldLabel} htmlFor="kill-switch-phrase">
          Type {KILL_SWITCH_PHRASE} to confirm
        </label>
        <input
          ref={inputRef}
          id="kill-switch-phrase"
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
        <span className={styles.confirmHint}>
          The phrase is case-sensitive.
        </span>
      </div>
    </ConfirmDialog>
  )
}
