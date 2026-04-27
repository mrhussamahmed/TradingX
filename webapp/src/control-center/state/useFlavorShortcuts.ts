import { useEffect } from 'react'

import { FLAVORS } from './types'
import { usePreferences } from './PreferencesContext'

export function isShortcutBlockedTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false
  }
  if (target.isContentEditable || target.getAttribute('contenteditable') === 'true') {
    return true
  }
  const tag = target.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
    return true
  }
  const role = target.getAttribute('role')
  if (role === 'dialog' || role === 'alertdialog' || role === 'slider') {
    return true
  }
  return Boolean(target.closest('[role="dialog"], [role="alertdialog"]'))
}

export function useFlavorShortcuts(onSwitch?: (label: string) => void) {
  const { setActiveFlavor } = usePreferences()

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (!(event.metaKey || event.ctrlKey)) {
        return
      }
      if (event.altKey || event.shiftKey) {
        return
      }
      if (isShortcutBlockedTarget(event.target) || isShortcutBlockedTarget(document.activeElement)) {
        return
      }
      const idx = Number.parseInt(event.key, 10)
      if (!Number.isFinite(idx)) {
        return
      }
      const match = FLAVORS.find((flavor) => flavor.index === idx)
      if (!match) {
        return
      }
      event.preventDefault()
      setActiveFlavor(match.id, 'manual')
      onSwitch?.(match.label)
    }

    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [setActiveFlavor, onSwitch])
}
