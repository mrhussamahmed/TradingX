import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { parseNumericValue, toCurrency } from './format'
import { EmptyState } from './ui'

function ChartTooltip(props: {
  active?: boolean
  label?: string
  payload?: Array<{ name?: string; value?: number | string; color?: string }>
  formatValue?: (value: number | string, name?: string) => string
}) {
  if (!props.active || !props.payload?.length) {
    return null
  }
  return (
    <div className="chart-tooltip">
      <strong>{props.label}</strong>
      {props.payload.map((entry) => (
        <div key={`${entry.name}-${entry.value}`} className="chart-tooltip-row">
          <span>{entry.name}</span>
          <strong>
            {props.formatValue
              ? props.formatValue(entry.value ?? '', entry.name)
              : typeof entry.value === 'number'
                ? toCurrency(entry.value)
                : entry.value}
          </strong>
        </div>
      ))}
    </div>
  )
}

export function EquityChart(props: {
  points: Array<{ label: string; equity: string; cash?: string; buying_power?: string }>
  emptyTitle: string
  emptyDetail: string
}) {
  if (!props.points.length) {
    return <EmptyState title={props.emptyTitle} detail={props.emptyDetail} />
  }
  const data = props.points.map((point) => ({
    label: point.label,
    Equity: parseNumericValue(point.equity),
    Cash: parseNumericValue(point.cash),
    BuyingPower: parseNumericValue(point.buying_power),
  }))
  return (
    <div className="chart-shell tall">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 12, right: 18, left: 6, bottom: 12 }}>
          <defs>
            <linearGradient id="equityGradient" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="rgba(135, 163, 199, 0.34)" />
              <stop offset="100%" stopColor="rgba(135, 163, 199, 0.02)" />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(126, 145, 163, 0.12)" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: '#91a1b7', fontSize: 11 }}
            axisLine={{ stroke: 'rgba(126, 145, 163, 0.16)' }}
            tickLine={false}
            label={{
              value: 'Observation',
              fill: '#91a1b7',
              fontSize: 11,
              offset: 0,
              position: 'insideBottom',
            }}
          />
          <YAxis
            tickFormatter={(value) => `$${Math.round(value / 1000)}k`}
            tick={{ fill: '#91a1b7', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={64}
            label={{
              value: 'USD',
              angle: -90,
              fill: '#91a1b7',
              fontSize: 11,
              position: 'insideLeft',
              dx: -4,
            }}
          />
          <Tooltip content={<ChartTooltip formatValue={(value) => toCurrency(Number(value))} />} />
          <Legend
            verticalAlign="top"
            align="right"
            iconType="plainline"
            wrapperStyle={{ paddingBottom: '12px' }}
          />
          <Area
            type="monotone"
            dataKey="Equity"
            stroke="#87a3c7"
            fill="url(#equityGradient)"
            strokeWidth={1.8}
            dot={false}
            activeDot={{ r: 4, fill: '#dce7f7' }}
          />
          {data.some((point) => point.Cash > 0) ? (
            <Line
              type="monotone"
              dataKey="Cash"
              stroke="#6fb186"
              strokeWidth={1.4}
              dot={false}
            />
          ) : null}
          {data.some((point) => point.BuyingPower > 0) ? (
            <Line
              type="monotone"
              dataKey="BuyingPower"
              name="Buying Power"
              stroke="#b7c6da"
              strokeDasharray="5 4"
              strokeWidth={1.2}
              dot={false}
            />
          ) : null}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ExposureChart(props: { items: Array<{ symbol: string; value: string }> }) {
  if (!props.items.length) {
    return <EmptyState title="No exposure" detail="TradingX is flat right now." />
  }
  const data = props.items.map((item) => ({
    symbol: item.symbol,
    value: parseNumericValue(item.value),
  }))
  return (
    <div className="chart-shell compact">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 12, right: 24, left: 4, bottom: 16 }}
        >
          <CartesianGrid stroke="rgba(126, 145, 163, 0.12)" horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={(value) => `${value}%`}
            tick={{ fill: '#91a1b7', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            label={{
              value: 'Percent of deployed capital',
              fill: '#91a1b7',
              fontSize: 11,
              offset: 0,
              position: 'insideBottom',
            }}
          />
          <YAxis
            type="category"
            dataKey="symbol"
            tick={{ fill: '#d4deeb', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={54}
          />
          <Tooltip
            content={
              <ChartTooltip
                formatValue={(value) =>
                  typeof value === 'number'
                    ? `${value.toFixed(2)}%`
                    : `${value}%`
                }
              />
            }
          />
          <Bar dataKey="value" radius={[0, 6, 6, 0]}>
            {data.map((entry) => (
              <Cell key={entry.symbol} fill="#718fb8" />
            ))}
            <LabelList
              dataKey="value"
              position="right"
              formatter={(value) =>
                typeof value === 'number' ? `${value.toFixed(1)}%` : `${value ?? ''}`
              }
              fill="#dbe5f3"
              fontSize={11}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function Sparkline(props: { values: string[] }) {
  const data = props.values.map((value, index) => ({
    index,
    value: parseNumericValue(value),
  }))
  if (!data.length) {
    return <span className="sparkline-empty">Waiting for history</span>
  }
  const values = data.map((point) => point.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const path = data
    .map((point, index) => {
      const x = (index / Math.max(data.length - 1, 1)) * 100
      const y = 100 - ((point.value - min) / span) * 100
      return `${index === 0 ? 'M' : 'L'} ${x} ${y}`
    })
    .join(' ')
  return (
    <div className="sparkline-shell">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <path d={path} />
      </svg>
    </div>
  )
}
