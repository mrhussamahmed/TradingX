import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'

import { EvidenceTimeline, type TimelineEvent } from '../EvidenceTimeline'

function makeEvents(count: number): TimelineEvent[] {
  const out: TimelineEvent[] = []
  const start = Date.UTC(2026, 3, 27, 9, 30)
  for (let i = 0; i < count; i += 1) {
    const severity =
      i % 17 === 0 ? 'risk' : i % 9 === 0 ? 'watch' : i % 5 === 0 ? 'good' : 'info'
    out.push({
      id: `event-${i}`,
      timestamp: new Date(start - i * 60_000).toISOString(),
      category: i % 2 === 0 ? 'execution' : 'evidence',
      source: i % 3 === 0 ? 'incidents' : i % 3 === 1 ? 'replay' : 'explorer',
      severity,
      symbol: i % 2 === 0 ? 'SPY' : 'QQQ',
      headline: `Event ${i}`,
      detail: i % 4 === 0 ? `Detail line ${i}` : undefined,
      evidenceRef: i % 7 === 0 ? `evidence/path/event-${i}.json` : undefined,
    })
  }
  return out
}

describe('EvidenceTimeline', () => {
  it('renders empty state when no events exist', () => {
    render(<EvidenceTimeline events={[]} showEvidenceLayer={true} />)
    expect(screen.getByText(/No evidence yet/i)).toBeInTheDocument()
  })

  it('renders rows and counts for moderate event volume', () => {
    render(<EvidenceTimeline events={makeEvents(20)} showEvidenceLayer={true} />)
    expect(screen.getByText(/20 events/)).toBeInTheDocument()
    const rows = screen.getAllByRole('row')
    expect(rows.length).toBeGreaterThan(1)
  })

  it('paginates above the 100-row threshold', () => {
    render(<EvidenceTimeline events={makeEvents(500)} showEvidenceLayer={true} />)
    expect(screen.getByText(/Showing 1–50 of 500/)).toBeInTheDocument()
    const next = screen.getByRole('button', { name: /Next page/i })
    fireEvent.click(next)
    expect(screen.getByText(/Showing 51–100 of 500/)).toBeInTheDocument()
    const prev = screen.getByRole('button', { name: /Previous page/i })
    fireEvent.click(prev)
    expect(screen.getByText(/Showing 1–50 of 500/)).toBeInTheDocument()
  })

  it('renders 500 events without crashing and limits visible rows to one page', () => {
    const events = makeEvents(500)
    const { container } = render(<EvidenceTimeline events={events} showEvidenceLayer={true} />)
    const tableRows = container.querySelectorAll('tbody tr')
    expect(tableRows.length).toBeLessThanOrEqual(50)
  })

  it('filters by severity', () => {
    render(<EvidenceTimeline events={makeEvents(40)} showEvidenceLayer={true} />)
    fireEvent.change(screen.getByLabelText(/Severity filter/i), { target: { value: 'risk' } })
    const counts = screen.getAllByText(/risk/i)
    expect(counts.length).toBeGreaterThan(0)
  })

  it('filters by source', () => {
    render(<EvidenceTimeline events={makeEvents(30)} showEvidenceLayer={true} />)
    fireEvent.change(screen.getByLabelText(/Source filter/i), { target: { value: 'incidents' } })
    const tbody = screen.getByRole('table').querySelector('tbody')!
    const rows = within(tbody as HTMLElement).getAllByRole('row')
    expect(rows.length).toBeLessThanOrEqual(50)
  })

  it('searches by headline', () => {
    render(<EvidenceTimeline events={makeEvents(10)} showEvidenceLayer={true} />)
    fireEvent.change(screen.getByLabelText(/Search evidence/i), { target: { value: 'Event 7' } })
    expect(screen.getByText('Event 7')).toBeInTheDocument()
  })

  it('hides evidence column when evidence layer is off', () => {
    render(<EvidenceTimeline events={makeEvents(5)} showEvidenceLayer={false} />)
    expect(screen.queryByText('Evidence', { selector: 'th' })).not.toBeInTheDocument()
  })

  it('respects symbol filter prop', () => {
    render(
      <EvidenceTimeline
        events={makeEvents(10)}
        showEvidenceLayer={true}
        symbolFilter="QQQ"
      />,
    )
    const tbody = screen.getByRole('table').querySelector('tbody')!
    const rows = within(tbody as HTMLElement).getAllByRole('row')
    rows.forEach((row) => {
      const symbolCell = within(row).getAllByRole('cell')[2]
      const text = symbolCell.textContent ?? ''
      expect(['QQQ', '—']).toContain(text)
    })
  })
})
