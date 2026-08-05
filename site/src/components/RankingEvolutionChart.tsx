import { useMemo } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { countryFlag } from '../lib/countryFlag'
import { ranksAtStage } from '../lib/leaderboard'
import type { ChartSeries, LeaderboardStage } from '../types'

/** Map stage short labels → country names used by countryFlag. */
const STAGE_COUNTRY: Record<string, string> = {
  Australia: 'Australia',
  China: 'China',
  Japan: 'Japan',
  Bahrain: 'Bahrain',
  'Saudi Arabia': 'Saudi Arabia',
  Miami: 'United States',
  Imola: 'Italy',
  Monaco: 'Monaco',
  Canada: 'Canada',
  Spain: 'Spain',
  Austria: 'Austria',
  Britain: 'United Kingdom',
  Hungary: 'Hungary',
  Belgium: 'Belgium',
  Netherlands: 'Netherlands',
  Italy: 'Italy',
  Azerbaijan: 'Azerbaijan',
  Singapore: 'Singapore',
  USA: 'United States',
  'US West': 'United States',
  Mexico: 'Mexico',
  Brazil: 'Brazil',
  'Las Vegas': 'United States',
  Qatar: 'Qatar',
  'Abu Dhabi': 'United Arab Emirates',
  Styria: 'Austria',
  Tuscany: 'Italy',
  Eifel: 'Germany',
  Portugal: 'Portugal',
  Sakhir: 'Bahrain',
  Turkey: 'Turkey',
  Russia: 'Russia',
  France: 'France',
  Germany: 'Germany',
  Malaysia: 'Malaysia',
  Europe: 'Azerbaijan',
  Korea: 'Korea',
  India: 'India',
  'San Marino': 'Italy',
  Pacific: 'Japan',
  Argentina: 'Argentina',
  'South Africa': 'South Africa',
  Luxembourg: 'Germany',
}

function stageFlag(label: string): string {
  const base = label.replace(/\s+S$/, '').trim()
  const country = STAGE_COUNTRY[base] ?? base
  return countryFlag(country)
}

function shortLabel(series: ChartSeries, mode: 'drivers' | 'constructors'): string {
  if (mode === 'drivers') {
    return (series.code || series.label).slice(0, 3).toUpperCase()
  }
  const name = series.label
  const key = name.toLowerCase()
  if (key.includes('haas')) return 'Haas'
  if (key.includes('red bull')) return 'Redbull'
  if (key.includes('aston martin')) return 'Aston Martin'
  if (name.length <= 12) return name
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .join('')
    .slice(0, 4)
    .toUpperCase()
}

function FlagTick({
  x,
  y,
  payload,
  index,
  visibleTicksCount,
}: {
  x?: number | string
  y?: number | string
  payload?: { value?: string }
  index?: number
  visibleTicksCount?: number
}) {
  if (x == null || y == null) return null
  const xNum = typeof x === 'number' ? x : Number(x)
  const yNum = typeof y === 'number' ? y : Number(y)
  if (!Number.isFinite(xNum) || !Number.isFinite(yNum)) return null

  const label = String(payload?.value ?? '')
  const flag = stageFlag(label)
  const i = index ?? 0
  const last = (visibleTicksCount ?? 1) - 1
  const dense = (visibleTicksCount ?? 0) > 16
  if (dense && i !== 0 && i !== last && i % 2 !== 0) {
    return (
      <g transform={`translate(${xNum},${yNum})`}>
        <line x1={0} y1={0} x2={0} y2={4} stroke="#444" strokeWidth={1} />
      </g>
    )
  }

  return (
    <g transform={`translate(${xNum},${yNum})`}>
      <line x1={0} y1={0} x2={0} y2={4} stroke="#444" strokeWidth={1} />
      {flag ? (
        <text dy={22} textAnchor="middle" fontSize={16}>
          {flag}
        </text>
      ) : (
        <text dy={18} textAnchor="middle" fill="#888" fontSize={9}>
          {label.slice(0, 3)}
        </text>
      )}
    </g>
  )
}

interface RankingEvolutionChartProps {
  stages: LeaderboardStage[]
  series: ChartSeries[]
  mode: 'drivers' | 'constructors'
  hidden: Set<string>
  chartKey: string
}

export function RankingEvolutionChart({
  stages,
  series,
  mode,
  hidden,
  chartKey,
}: RankingEvolutionChartProps) {
  const lastIndex = Math.max(0, stages.length - 1)

  const activeSeries = useMemo(
    () => series.filter((s) => !s.disqualified),
    [series],
  )

  const { rows, maxRank } = useMemo(() => {
    if (!stages.length || !activeSeries.length) {
      return { rows: [] as Record<string, string | number | null>[], maxRank: 1 }
    }

    const built = stages.map((stage) => {
      const ranks = ranksAtStage(activeSeries, stages, stage.id)
      const row: Record<string, string | number | null> = {
        stageId: stage.id,
        label: stage.label,
      }
      for (const s of activeSeries) {
        row[s.id] = ranks.get(s.id) ?? null
      }
      return row
    })

    return { rows: built, maxRank: activeSeries.length }
  }, [stages, activeSeries])

  const title =
    mode === 'drivers' ? 'Driver Ranking Evolution' : 'Constructor Ranking Evolution'

  if (!rows.length) return null

  return (
    <section className="lb-rank-evo" aria-label={title}>
      <div className="lb-rank-evo-head">
        <h3>{title}</h3>
      </div>
      <div className="lb-rank-evo-chart">
        <ResponsiveContainer width="100%" height={Math.max(340, maxRank * 24 + 72)}>
          <LineChart
            key={chartKey}
            data={rows}
            margin={{ top: 20, right: 96, left: 4, bottom: 8 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#22222a" horizontal vertical={false} />
            <XAxis
              dataKey="label"
              stroke="#666"
              interval={0}
              tick={(props) => <FlagTick {...props} />}
              height={40}
              padding={{ left: 12, right: 12 }}
            />
            <YAxis
              stroke="#666"
              tick={{ fill: '#999', fontSize: 11 }}
              width={28}
              domain={[1, maxRank]}
              reversed
              allowDecimals={false}
              ticks={Array.from({ length: maxRank }, (_, i) => i + 1)}
              interval={0}
            />
            <Tooltip
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null
                const ordered = [...payload]
                  .filter((p) => typeof p.value === 'number')
                  .sort((a, b) => Number(a.value) - Number(b.value))
                return (
                  <div className="lb-tooltip">
                    <p className="lb-tooltip-label">{String(label ?? '')}</p>
                    <ul className="lb-tooltip-list">
                      {ordered.slice(0, 12).map((p) => {
                        const s = activeSeries.find((x) => x.id === p.dataKey)
                        return (
                          <li key={String(p.dataKey)} style={{ color: String(p.color ?? '#fff') }}>
                            <span className="lb-tooltip-pos">P{p.value}</span>
                            <span>{s ? shortLabel(s, mode) : String(p.dataKey)}</span>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                )
              }}
              cursor={{ stroke: '#444', strokeWidth: 1 }}
            />
            {activeSeries.map((s) => {
              const dimmed = hidden.has(s.id)
              const endText = shortLabel(s, mode)
              return (
                <Line
                  key={s.id}
                  type="monotone"
                  dataKey={s.id}
                  name={s.label}
                  stroke={s.color}
                  strokeWidth={dimmed ? 1 : 2.25}
                  strokeOpacity={dimmed ? 0.12 : 0.95}
                  strokeDasharray={s.isSecondDriver ? '6 4' : undefined}
                  dot={{
                    r: 2.5,
                    fill: s.color,
                    fillOpacity: dimmed ? 0.15 : 1,
                    strokeWidth: 0,
                  }}
                  activeDot={{ r: 4 }}
                  connectNulls
                  isAnimationActive
                  animationDuration={500}
                  label={
                    ((props: {
                      x?: string | number
                      y?: string | number
                      index?: number
                    }) => {
                      const index = props.index
                      const x = typeof props.x === 'number' ? props.x : Number(props.x)
                      const y = typeof props.y === 'number' ? props.y : Number(props.y)
                      if (
                        index !== lastIndex ||
                        !Number.isFinite(x) ||
                        !Number.isFinite(y) ||
                        dimmed
                      ) {
                        return null
                      }
                      return (
                        <text
                          x={x + 8}
                          y={y}
                          dy={4}
                          fill={s.color}
                          fontSize={11}
                          fontWeight={600}
                          textAnchor="start"
                        >
                          {endText}
                        </text>
                      )
                    }) as never
                  }
                />
              )
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
