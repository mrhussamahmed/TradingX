import { useEffect, useRef, type ReactNode } from 'react'
import { AlertTriangle, Info, ShieldAlert, X } from 'lucide-react'

import styles from './Dialog.module.css'

export type ConfirmDialogTone = 'info' | 'watch' | 'risk'

export type ConfirmDialogProps = {
  open: boolean
  title: string
  subtitle?: string
  tone?: ConfirmDialogTone
  confirmLabel: string
  confirmDisabled?: boolean
  confirmDisabledReason?: string
  onConfirm: () => void
  onClose: () => void
  busy?: boolean
  children?: ReactNode
}

export function ConfirmDialog(props: ConfirmDialogProps) {
  const {
    open,
    title,
    subtitle,
    tone = 'info',
    confirmLabel,
    confirmDisabled,
    confirmDisabledReason,
    onConfirm,
    onClose,
    busy,
    children,
  } = props

  const confirmRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    if (!open) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  useEffect(() => {
    if (!open) return
    if (confirmDisabled) return
    confirmRef.current?.focus()
  }, [open, confirmDisabled])

  if (!open) return null

  const Icon = tone === 'risk' ? ShieldAlert : tone === 'watch' ? AlertTriangle : Info
  const iconClass =
    tone === 'risk'
      ? styles.headerIconRisk
      : tone === 'watch'
        ? styles.headerIconWarn
        : styles.headerIconInfo
  const confirmClass =
    tone === 'risk' ? 'btn btn-danger' : tone === 'watch' ? 'btn btn-warn' : 'btn btn-primary'

  return (
    <div
      className={styles.scrim}
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div className={styles.dialog} role="alertdialog" aria-labelledby="confirm-dialog-title" aria-modal>
        <header className={styles.header}>
          <div className={`${styles.headerIcon} ${iconClass}`}>
            <Icon size={14} aria-hidden />
          </div>
          <div>
            <h2 id="confirm-dialog-title" className={styles.headerTitle}>
              {title}
            </h2>
            {subtitle ? <p className={styles.headerSubtitle}>{subtitle}</p> : null}
          </div>
          <button
            type="button"
            className={styles.headerIcon}
            style={{ marginLeft: 'auto', color: 'var(--text-muted)', borderColor: 'var(--border-muted)' }}
            onClick={onClose}
            aria-label="Close dialog"
          >
            <X size={14} />
          </button>
        </header>
        <div className={styles.body}>
          {children}
          {confirmDisabled && confirmDisabledReason ? (
            <div className={`${styles.warningCallout} ${tone === 'watch' ? styles.warningCalloutWatch : ''}`}>
              <span>{confirmDisabledReason}</span>
            </div>
          ) : null}
        </div>
        <footer className={styles.footer}>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            ref={confirmRef}
            type="button"
            className={confirmClass}
            onClick={onConfirm}
            disabled={confirmDisabled || busy}
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </footer>
      </div>
    </div>
  )
}
