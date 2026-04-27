import { AlertOctagon, AlertTriangle, CheckCircle2, Info } from 'lucide-react'

import { useToast, type ToastTone } from '../state/ToastContext'

import styles from './Canvas.module.css'

const TONE_CLASS: Record<ToastTone, string> = {
  info: styles.toastInfo,
  good: styles.toastGood,
  watch: styles.toastWatch,
  risk: styles.toastRisk,
}

export function Toasts() {
  const { toasts, dismiss } = useToast()
  return (
    <div className={styles.toasts} role="status" aria-live="polite">
      {toasts.map((toast) => {
        const Icon =
          toast.tone === 'risk'
            ? AlertOctagon
            : toast.tone === 'watch'
              ? AlertTriangle
              : toast.tone === 'good'
                ? CheckCircle2
                : Info
        const color =
          toast.tone === 'risk'
            ? 'var(--risk)'
            : toast.tone === 'watch'
              ? 'var(--watch)'
              : toast.tone === 'good'
                ? 'var(--good)'
                : 'var(--primary-bright)'
        return (
          <div
            key={toast.id}
            className={[styles.toast, TONE_CLASS[toast.tone]].filter(Boolean).join(' ')}
            onClick={() => dismiss(toast.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                dismiss(toast.id)
              }
            }}
          >
            <Icon className={styles.toastIcon} color={color} aria-hidden />
            <span>{toast.message}</span>
          </div>
        )
      })}
    </div>
  )
}
