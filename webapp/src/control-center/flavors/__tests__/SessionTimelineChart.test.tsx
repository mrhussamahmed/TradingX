import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import type { SessionTimelineResponse } from '../../../types'
import { SessionTimelineChart } from '../SessionTimelineChart'

function makeTimeline(): SessionTimelineResponse {
  return {
    session: {
      trading_day: '2026-04-28',
      schedule_id: 'schedule-1',
      session_open_at_utc: '2026-04-28T13:30:00+00:00',
      session_close_at_utc: '2026-04-28T20:00:00+00:00',
      exchange: 'XNYS',
      timezone: 'America/New_York',
      status: 'complete_session_metadata',
      metadata_status: 'complete',
      partial_reason: '',
    },
    available_trading_days: ['2026-04-28', '2026-04-27'],
    filters: {
      trading_day: '2026-04-28',
      symbol: null,
      cycle_id: null,
      incident_id: null,
    },
    events: [
      {
        event_id: 'cycle-1',
        event_type: 'service_cycle',
        symbol: 'SPY',
        severity: 'info',
        headline: 'Service cycle completed',
        details: 'Cycle status: completed.',
        occurred_at_utc: '2026-04-28T14:00:00+00:00',
        artifact_path: 'artifacts/paper_loop/service_cycles/cycle-1.json',
        related_ids: ['cycle-1'],
        shape: 'instant',
        started_at_utc: null,
        ended_at_utc: null,
        duration_seconds: null,
        status: 'completed',
        reason: 'Cycle status: completed.',
        evidence_freshness: 'source_timestamp',
        source_status: 'authoritative_instant',
      },
      {
        event_id: 'reconcile-1',
        event_type: 'reconciliation',
        symbol: '',
        severity: 'warning',
        headline: 'Reconciliation stale',
        details: 'Broker state was stale.',
        occurred_at_utc: '2026-04-28T19:00:00+00:00',
        artifact_path: 'artifacts/paper_loop/reconciliation/reconcile-1.json',
        related_ids: ['reconcile-1'],
        shape: 'instant',
        started_at_utc: null,
        ended_at_utc: null,
        duration_seconds: null,
        status: 'warning',
        reason: 'Broker state was stale.',
        evidence_freshness: 'source_timestamp',
        source_status: 'authoritative_instant',
      },
    ],
  }
}

describe('SessionTimelineChart', () => {
  it('renders a date picker, legend, and tooltip-backed timeline events', () => {
    render(
      <SessionTimelineChart
        title="Operation Timeline"
        description="Session timeline"
        timeline={makeTimeline()}
        selectedTradingDay="2026-04-28"
        onTradingDayChange={() => undefined}
        emptyStateMessage="No events."
      />,
    )

    expect(screen.getByLabelText(/Operation Timeline trading day/i)).toHaveValue('2026-04-28')
    expect(screen.getAllByText(/Service Cycle/i).length).toBeGreaterThan(0)
    const eventButton = screen.getByRole('button', { name: /Service Cycle Service cycle completed/i })
    expect(eventButton).toHaveAttribute('title', expect.stringContaining('Evidence freshness'))
    expect(eventButton).toHaveAttribute('title', expect.stringContaining('Duration: instant'))
  })

  it('emits selected dates through the change handler', () => {
    const onTradingDayChange = vi.fn()
    render(
      <SessionTimelineChart
        title="Evidence Timeline"
        description="Session timeline"
        timeline={makeTimeline()}
        selectedTradingDay="2026-04-28"
        onTradingDayChange={onTradingDayChange}
        emptyStateMessage="No events."
      />,
    )

    fireEvent.change(screen.getByLabelText(/Evidence Timeline trading day/i), {
      target: { value: '2026-04-27' },
    })

    expect(onTradingDayChange).toHaveBeenCalledWith('2026-04-27')
  })

  it('summarizes retained post-close events without stretching the session axis', () => {
    const timeline = makeTimeline()
    timeline.events = [
      {
        ...timeline.events[0],
        event_id: 'close',
        event_type: 'digest',
        headline: 'Close digest',
        occurred_at_utc: '2026-04-28T20:00:00+00:00',
      },
      {
        ...timeline.events[1],
        event_id: 'post-close',
        event_type: 'digest',
        headline: 'Post-close reconciliation',
        occurred_at_utc: '2026-04-28T20:01:00+00:00',
      },
    ]
    render(
      <SessionTimelineChart
        title="Operation Timeline"
        description="Session timeline"
        timeline={timeline}
        selectedTradingDay="2026-04-28"
        onTradingDayChange={() => undefined}
        emptyStateMessage="No events."
      />,
    )

    const close = screen.getByRole('button', { name: /Digest Close digest/i })
    expect(close).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Digest Post-close reconciliation/i })).not.toBeInTheDocument()
    expect(screen.getByText(/After session: 1/i)).toHaveAttribute('title', expect.stringContaining('Digest: 1'))
  })

  it('clusters dense instant events into readable count markers', () => {
    const timeline = makeTimeline()
    timeline.events = Array.from({ length: 12 }, (_, index) => ({
      ...timeline.events[0],
      event_id: `cycle-${index}`,
      headline: `Cycle ${index}`,
      occurred_at_utc: `2026-04-28T14:${String(index).padStart(2, '0')}:00+00:00`,
    }))

    render(
      <SessionTimelineChart
        title="Operation Timeline"
        description="Session timeline"
        timeline={timeline}
        selectedTradingDay="2026-04-28"
        onTradingDayChange={() => undefined}
        emptyStateMessage="No events."
      />,
    )

    const cluster = screen.getByRole('button', { name: /Service Cycle 12 events/i })
    expect(cluster).toHaveTextContent('12')
    expect(cluster).toHaveAttribute('title', expect.stringContaining('Events: 12'))
    expect(screen.queryByRole('button', { name: /Service Cycle Cycle 0/i })).not.toBeInTheDocument()
  })

  it('uses a disclosed regular-session reference when schedule metadata is missing', () => {
    const timeline = makeTimeline()
    timeline.session = {
      ...timeline.session,
      session_open_at_utc: null,
      session_close_at_utc: null,
      status: 'missing_session_metadata',
      metadata_status: 'schedule_missing',
      partial_reason: 'No market-day schedule metadata was found for this trading day.',
    }
    timeline.events = [
      {
        ...timeline.events[0],
        event_id: 'pre-open',
        headline: 'Pre-open closed cycle',
        occurred_at_utc: '2026-04-28T09:00:00+00:00',
      },
      {
        ...timeline.events[0],
        event_id: 'regular-session',
        headline: 'Regular session cycle',
        occurred_at_utc: '2026-04-28T14:00:00+00:00',
      },
    ]

    render(
      <SessionTimelineChart
        title="Evidence Timeline"
        description="Session timeline"
        timeline={timeline}
        selectedTradingDay="2026-04-28"
        onTradingDayChange={() => undefined}
        emptyStateMessage="No events."
      />,
    )

    expect(screen.getByText(/regular XNYS session as a visual reference/i)).toBeInTheDocument()
    expect(screen.getByText(/Before session: 1/i)).toBeInTheDocument()
    expect(screen.queryByText(/No market-day schedule metadata was found/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Service Cycle Regular session cycle/i })).toBeInTheDocument()
  })
})
