import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { KILL_SWITCH_PHRASE, KillSwitchDialog } from '../KillSwitchDialog'

describe('KillSwitchDialog', () => {
  function renderDialog(overrides: Partial<Parameters<typeof KillSwitchDialog>[0]> = {}) {
    const onConfirm = vi.fn()
    const onClose = vi.fn()
    const utils = render(
      <KillSwitchDialog
        open
        onConfirm={onConfirm}
        onClose={onClose}
        killEndpointSupported
        killSwitchAlreadyActive={false}
        affectedSummary={{ activeSymbols: ['SPY'], runtimeStatus: 'running' }}
        {...overrides}
      />,
    )
    return { ...utils, onConfirm, onClose }
  }

  it('renders the typed-phrase requirement', () => {
    renderDialog()
    expect(screen.getByRole('heading', { name: /Activate Kill Switch/i })).toBeInTheDocument()
    expect(screen.getByLabelText(new RegExp(`Type ${KILL_SWITCH_PHRASE} to confirm`))).toBeInTheDocument()
    expect(screen.getByText(/Type KILL TRADINGX to confirm\./)).toBeInTheDocument()
  })

  it('disables confirm until phrase matches exactly', () => {
    const { onConfirm } = renderDialog()
    const confirm = screen.getByRole('button', { name: /Activate Kill Switch/i })
    expect(confirm).toBeDisabled()

    const input = screen.getByLabelText(/Type KILL TRADINGX/i) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'kill tradingx' } })
    expect(confirm).toBeDisabled()
    fireEvent.change(input, { target: { value: KILL_SWITCH_PHRASE } })
    expect(confirm).not.toBeDisabled()
    fireEvent.click(confirm)
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('keeps confirm disabled when endpoint is unavailable, even with correct phrase', () => {
    renderDialog({ killEndpointSupported: false })
    const input = screen.getByLabelText(/Type KILL TRADINGX/i) as HTMLInputElement
    fireEvent.change(input, { target: { value: KILL_SWITCH_PHRASE } })
    const confirm = screen.getByRole('button', { name: /Activate Kill Switch/i })
    expect(confirm).toBeDisabled()
    expect(screen.getByText(/backend endpoint is not implemented yet/i)).toBeInTheDocument()
  })

  it('shows the runtime status and active symbols', () => {
    renderDialog({
      affectedSummary: { activeSymbols: ['SPY', 'QQQ'], runtimeStatus: 'running' },
    })
    expect(screen.getByText(/SPY, QQQ/)).toBeInTheDocument()
  })

  it('blocks confirm when kill switch is already active', () => {
    renderDialog({ killSwitchAlreadyActive: true })
    const input = screen.getByLabelText(/Type KILL TRADINGX/i) as HTMLInputElement
    fireEvent.change(input, { target: { value: KILL_SWITCH_PHRASE } })
    const confirm = screen.getByRole('button', { name: /Activate Kill Switch/i })
    expect(confirm).toBeDisabled()
    expect(screen.getByText(/Kill switch is already active/i)).toBeInTheDocument()
  })
})
