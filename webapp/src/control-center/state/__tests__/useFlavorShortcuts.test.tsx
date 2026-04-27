import { describe, expect, it } from 'vitest'
import { act, fireEvent, render } from '@testing-library/react'

import { PreferencesProvider, usePreferences } from '../PreferencesContext'
import { useFlavorShortcuts, isShortcutBlockedTarget } from '../useFlavorShortcuts'

function ShortcutHarness() {
  const { prefs } = usePreferences()
  useFlavorShortcuts()
  return (
    <div>
      <span data-testid="active">{prefs.activeFlavor}</span>
      <input data-testid="text-input" />
      <textarea data-testid="textarea" />
      <select data-testid="select">
        <option value="a">a</option>
      </select>
      <div data-testid="dialog" role="dialog">
        <button data-testid="dialog-button">Inside dialog</button>
      </div>
    </div>
  )
}

function renderHarness() {
  return render(
    <PreferencesProvider>
      <ShortcutHarness />
    </PreferencesProvider>,
  )
}

function dispatchShortcut(key: string, opts: { metaKey?: boolean; ctrlKey?: boolean } = { metaKey: true }) {
  const event = new KeyboardEvent('keydown', {
    key,
    code: `Digit${key}`,
    metaKey: opts.metaKey ?? false,
    ctrlKey: opts.ctrlKey ?? false,
    bubbles: true,
    cancelable: true,
  })
  act(() => {
    window.dispatchEvent(event)
  })
}

describe('useFlavorShortcuts', () => {
  it('switches active flavor for Cmd+1 through Cmd+6', () => {
    const { getByTestId } = renderHarness()
    expect(getByTestId('active').textContent).toBe('market-chart')

    dispatchShortcut('2')
    expect(getByTestId('active').textContent).toBe('strategy-forge')

    dispatchShortcut('5', { ctrlKey: true })
    expect(getByTestId('active').textContent).toBe('portfolio-constellation')

    dispatchShortcut('6')
    expect(getByTestId('active').textContent).toBe('evidence-replay')
  })

  it('ignores keys 7+ that do not map to a flavor', () => {
    const { getByTestId } = renderHarness()
    dispatchShortcut('1')
    expect(getByTestId('active').textContent).toBe('market-chart')
    dispatchShortcut('7')
    expect(getByTestId('active').textContent).toBe('market-chart')
    dispatchShortcut('0')
    expect(getByTestId('active').textContent).toBe('market-chart')
  })

  it('does not fire when the meta/ctrl modifier is missing', () => {
    const { getByTestId } = renderHarness()
    dispatchShortcut('3', {})
    expect(getByTestId('active').textContent).toBe('market-chart')
  })

  it('does not fire when shift or alt are also held', () => {
    const { getByTestId } = renderHarness()
    const event = new KeyboardEvent('keydown', {
      key: '4',
      code: 'Digit4',
      metaKey: true,
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    })
    act(() => {
      window.dispatchEvent(event)
    })
    expect(getByTestId('active').textContent).toBe('market-chart')
  })

  it('is suppressed while a text input has focus', () => {
    const { getByTestId } = renderHarness()
    const input = getByTestId('text-input') as HTMLInputElement
    input.focus()
    dispatchShortcut('3')
    expect(getByTestId('active').textContent).toBe('market-chart')
    input.blur()
    dispatchShortcut('3')
    expect(getByTestId('active').textContent).toBe('market-day-ops')
  })

  it('is suppressed while a textarea has focus', () => {
    const { getByTestId } = renderHarness()
    ;(getByTestId('textarea') as HTMLTextAreaElement).focus()
    dispatchShortcut('5')
    expect(getByTestId('active').textContent).toBe('market-chart')
  })

  it('is suppressed while a button inside a dialog has focus', () => {
    const { getByTestId } = renderHarness()
    ;(getByTestId('dialog-button') as HTMLButtonElement).focus()
    dispatchShortcut('4')
    expect(getByTestId('active').textContent).toBe('market-chart')
  })
})

describe('isShortcutBlockedTarget', () => {
  it('blocks input, textarea, select, contenteditable, dialog descendants', () => {
    const input = document.createElement('input')
    const textarea = document.createElement('textarea')
    const select = document.createElement('select')
    const editable = document.createElement('div')
    editable.setAttribute('contenteditable', 'true')
    const dialog = document.createElement('div')
    dialog.setAttribute('role', 'dialog')
    const dialogChild = document.createElement('button')
    dialog.appendChild(dialogChild)
    document.body.appendChild(dialog)

    expect(isShortcutBlockedTarget(input)).toBe(true)
    expect(isShortcutBlockedTarget(textarea)).toBe(true)
    expect(isShortcutBlockedTarget(select)).toBe(true)
    expect(isShortcutBlockedTarget(editable)).toBe(true)
    expect(isShortcutBlockedTarget(dialog)).toBe(true)
    expect(isShortcutBlockedTarget(dialogChild)).toBe(true)
    expect(isShortcutBlockedTarget(document.createElement('div'))).toBe(false)
    fireEvent.click(dialog) // ensure dialog stays in DOM
    document.body.removeChild(dialog)
  })

  it('does not block plain divs or buttons outside a dialog', () => {
    const div = document.createElement('div')
    const button = document.createElement('button')
    expect(isShortcutBlockedTarget(div)).toBe(false)
    expect(isShortcutBlockedTarget(button)).toBe(false)
  })
})
