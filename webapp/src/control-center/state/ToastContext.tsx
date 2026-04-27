import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

export type ToastTone = 'info' | 'good' | 'watch' | 'risk'

export type Toast = {
  id: number
  message: string
  tone: ToastTone
  ttlMs: number
}

export type ToastContextValue = {
  toasts: Toast[]
  pushToast: (message: string, tone?: ToastTone, ttlMs?: number) => void
  dismiss: (id: number) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)
const DEFAULT_TTL_MS = 4000

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const idRef = useRef(0)

  const dismiss = useCallback((id: number) => {
    setToasts((list) => list.filter((toast) => toast.id !== id))
  }, [])

  const pushToast = useCallback<ToastContextValue['pushToast']>(
    (message, tone = 'info', ttlMs = DEFAULT_TTL_MS) => {
      idRef.current += 1
      const id = idRef.current
      setToasts((list) => [...list, { id, message, tone, ttlMs }])
      if (typeof window !== 'undefined' && ttlMs > 0) {
        window.setTimeout(() => dismiss(id), ttlMs)
      }
    },
    [dismiss],
  )

  const value = useMemo<ToastContextValue>(
    () => ({ toasts, pushToast, dismiss }),
    [toasts, pushToast, dismiss],
  )

  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    throw new Error('useToast must be used inside ToastProvider')
  }
  return ctx
}
