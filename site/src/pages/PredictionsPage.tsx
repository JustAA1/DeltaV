import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { DriverAvatar } from '../components/DriverAvatar'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { RaceSelector } from '../components/RaceSelector'
import type { DriverRecord } from '../types'

function driverMap(drivers: DriverRecord[]) {
  return new Map(drivers.map((d) => [d.code, d]))
}

type SortMode = 'prediction' | 'actual'

interface Row {
  driver_code: string
  driver_name: string
  team: string
  predicted_position: number
  actual_position: number | null
  delta: number | null
}

function deltaClass(delta: number | null): string {
  if (delta === null) return ''
  if (delta === 0) return 'delta-perfect'
  if (Math.abs(delta) <= 1) return 'delta-close'
  return 'delta-off'
}

function deltaLabel(delta: number | null): string {
  if (delta === null) return '—'
  if (delta === 0) return '0'
  return delta > 0 ? `+${delta}` : String(delta)
}

function PosBox({ row, hasActual }: { row: Row; hasActual: boolean }) {
  return (
    <div className="pos-box">
      {hasActual && (
        <div className="pos-cell">
          <span className="pos-cell-label">Actual</span>
          <span className="pos-cell-val">P{row.actual_position ?? '—'}</span>
        </div>
      )}
      <div className="pos-cell">
        <span className="pos-cell-label">Pred</span>
        <span className="pos-cell-val">P{row.predicted_position}</span>
      </div>
      {hasActual && (
        <div className="pos-cell">
          <span className="pos-cell-label">Δ</span>
          <span className={`pos-cell-val ${deltaClass(row.delta)}`}>{deltaLabel(row.delta)}</span>
        </div>
      )}
    </div>
  )
}

function DriverRow({
  row,
  drivers,
  hasActual,
  displayPos,
}: {
  row: Row
  drivers: Map<string, DriverRecord>
  hasActual: boolean
  displayPos: number
}) {
  const meta = drivers.get(row.driver_code)
  const color = meta?.color ?? '#888'
  return (
    <article className="driver-card" style={{ borderLeftColor: color }}>
      <div className="driver-card-rank">
        <span>P{displayPos}</span>
        {!hasActual && <span className="rank-pred">Pred</span>}
      </div>
      <DriverAvatar code={row.driver_code} name={row.driver_name} color={color} image={meta?.image} />
      <div className="driver-card-body">
        <h3>{row.driver_name}</h3>
        <p className="team-label" style={{ color }}>{row.team}</p>
      </div>
      {hasActual && <PosBox row={row} hasActual={hasActual} />}
    </article>
  )
}

function podiumAvatarSize(position: number): number {
  if (position === 1) return 72
  if (position === 2) return 60
  return 52
}

function PodiumCard({
  row,
  drivers,
  hasActual,
  displayPos,
}: {
  row: Row
  drivers: Map<string, DriverRecord>
  hasActual: boolean
  displayPos: number
}) {
  const meta = drivers.get(row.driver_code)
  const color = meta?.color ?? '#888'
  return (
    <article className={`podium-card podium-${displayPos}`} style={{ borderTopColor: color }}>
      <div className="podium-pos">
        P{displayPos}
        {!hasActual && <span className="rank-pred">Pred</span>}
      </div>
      <DriverAvatar
        code={row.driver_code}
        name={row.driver_name}
        color={color}
        image={meta?.image}
        size={podiumAvatarSize(displayPos)}
      />
      <h3>{row.driver_name}</h3>
      <p className="team-label" style={{ color }}>{row.team}</p>
      {hasActual && <PosBox row={row} hasActual={hasActual} />}
    </article>
  )
}

export function PredictionsPage() {
  const { data: racesData, isLoading: racesLoading } = useQuery({
    queryKey: ['races'],
    queryFn: api.races,
  })
  const { data: driversData } = useQuery({
    queryKey: ['drivers'],
    queryFn: api.drivers,
  })

  const rounds = racesData?.races ?? []
  const [selectedRound, setSelectedRound] = useState<number | null>(null)
  const round = selectedRound ?? rounds[rounds.length - 1]?.round ?? 1
  const [sortBy, setSortBy] = useState<SortMode | null>(null)

  const { data: prediction, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['predictions', round],
    queryFn: () => api.predictions(round),
    enabled: round > 0,
  })

  const drivers = useMemo(
    () => driverMap(driversData?.drivers ?? []),
    [driversData],
  )

  const hasActual = !!prediction?.actual?.length && !prediction?.upcoming
  const isUpcoming = !hasActual
  // Default: actual result for completed races, prediction for upcoming ones.
  // A user's explicit choice (sortBy) overrides the default.
  const effectiveSort: SortMode =
    !hasActual ? 'prediction' : sortBy ?? 'actual'

  const rows = useMemo<Row[]>(() => {
    if (!prediction) return []
    const actualMap = new Map((prediction.actual ?? []).map((a) => [a.driver_code, a.position]))
    const list: Row[] = prediction.predictions.map((p) => {
      const actual = actualMap.get(p.driver_code) ?? null
      const delta = actual != null ? p.predicted_position - actual : null
      return {
        driver_code: p.driver_code,
        driver_name: p.driver_name,
        team: p.team,
        predicted_position: p.predicted_position,
        actual_position: actual,
        delta,
      }
    })
    return list.sort((a, b) => {
      if (effectiveSort === 'actual') {
        const av = a.actual_position ?? Number.POSITIVE_INFINITY
        const bv = b.actual_position ?? Number.POSITIVE_INFINITY
        return av - bv
      }
      return a.predicted_position - b.predicted_position
    })
  }, [prediction, effectiveSort])

  const posFor = (row: Row, idx: number) =>
    effectiveSort === 'actual' ? row.actual_position ?? idx + 1 : row.predicted_position

  const podium = rows.slice(0, 3)
  const rest = rows.slice(3)

  if (racesLoading) return <LoadingSkeleton />

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Predictions</h1>
        </div>
        {rounds.length > 0 && (
          <RaceSelector rounds={rounds} selected={round} onChange={setSelectedRound} />
        )}
      </header>

      {prediction && (
        <div className="race-banner">
          <h2>{prediction.event_name}</h2>
          <span className="badge">Round {prediction.round}</span>
          {isUpcoming && <span className="badge upcoming-badge">Upcoming — not yet raced</span>}
          <div className="sort-controls toggle-group" role="group" aria-label="Sort order">
            <button
              type="button"
              className={effectiveSort === 'prediction' ? 'toggle active' : 'toggle'}
              onClick={() => setSortBy('prediction')}
            >
              Sort by prediction
            </button>
            <button
              type="button"
              className={effectiveSort === 'actual' ? 'toggle active' : 'toggle'}
              onClick={() => setSortBy('actual')}
              disabled={!hasActual}
              title={hasActual ? undefined : 'No results yet for this round'}
            >
              Sort by actual result
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <LoadingSkeleton />
      ) : isError ? (
        <p className="page-empty" role="alert">
          Could not load predictions for round {round}
          {error instanceof Error ? `: ${error.message}` : ''}.{' '}
          <button type="button" className="what-if-clear" onClick={() => void refetch()}>
            Retry
          </button>
        </p>
      ) : !prediction ? (
        <p className="page-empty">No prediction data for this round yet.</p>
      ) : (
        <>
          {podium.length > 0 && (
            <div className="podium">
              {podium.map((row, idx) => (
                <PodiumCard
                  key={row.driver_code}
                  row={row}
                  drivers={drivers}
                  hasActual={hasActual}
                  displayPos={posFor(row, idx)}
                />
              ))}
            </div>
          )}

          <div className="driver-grid">
            {rest.map((row, idx) => (
              <DriverRow
                key={row.driver_code}
                row={row}
                drivers={drivers}
                hasActual={hasActual}
                displayPos={posFor(row, idx + 3)}
              />
            ))}
          </div>
        </>
      )}
    </section>
  )
}
