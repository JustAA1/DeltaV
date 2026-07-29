import { useMemo } from 'react'
import type { RaceReplay } from '../../types'
import { compoundColor, isInPit, sampleProgress, timeAtProgress } from '../../lib/replayUtils'

interface PositionsPanelProps {
  replay: RaceReplay
  t: number
  highlighted?: string | null
  selected?: string | null
  onHoverDriver?: (code: string | null) => void
  onSelectDriver?: (code: string) => void
}

interface Row {
  code: string
  name: string
  color: string
  compound: string | null
  pits: number
  lap: number | null
  /** Interval to the car ahead, in seconds. Null when it cannot be measured. */
  gap: number | null
  lapsDown: number
  inPit: boolean
  running: boolean
  grid: number
}

export function PositionsPanel({
  replay,
  t,
  highlighted,
  selected,
  onHoverDriver,
  onSelectDriver,
}: PositionsPanelProps) {
  const pitCounts = useMemo(() => {
    const map = new Map<string, number>()
    for (const p of replay.pits) {
      if (p.t_s <= t) map.set(p.code, (map.get(p.code) ?? 0) + 1)
    }
    return map
  }, [replay.pits, t])

  const compounds = useMemo(() => {
    const map = new Map<string, string>()
    for (const s of replay.stints) {
      if (s.t_start_s <= t) map.set(s.code, s.compound)
    }
    return map
  }, [replay.stints, t])

  const rows = useMemo<Row[]>(() => {
    const running: (Row & { prog: number })[] = []
    const out: Row[] = []

    for (const drv of replay.drivers) {
      const series = replay.prog[drv.code]
      const prog = series ? sampleProgress(series, t, replay.hz) : null
      const base: Row = {
        code: drv.code,
        name: drv.name,
        color: drv.color || '#888',
        compound: compounds.get(drv.code) ?? null,
        pits: pitCounts.get(drv.code) ?? 0,
        lap: prog != null ? Math.floor(prog) + 1 : null,
        gap: null,
        lapsDown: 0,
        inPit: isInPit(replay.pit_windows?.[drv.code], t),
        running: prog != null && t <= drv.end_t_s + 1,
        grid: drv.grid && drv.grid > 0 ? drv.grid : 99,
      }
      if (base.running && prog != null) running.push({ ...base, prog })
      else out.push({ ...base, running: false })
    }

    // Grid order breaks the tie on the standing start, where progress is 0 for all
    running.sort((a, b) => b.prog - a.prog || a.grid - b.grid)

    for (let i = 1; i < running.length; i++) {
      const row = running[i]
      const ahead = running[i - 1]
      const lapsDown = Math.floor(ahead.prog - row.prog)
      if (lapsDown >= 1) {
        row.lapsDown = lapsDown
        continue
      }
      // When was the car ahead last at this car's current progress?
      const aheadSeries = replay.prog[ahead.code]
      const then = aheadSeries ? timeAtProgress(aheadSeries, row.prog, replay.hz) : null
      row.gap = then != null ? Math.max(0, t - then) : null
    }

    out.sort((a, b) => a.grid - b.grid)
    return [...running, ...out]
  }, [replay.drivers, replay.prog, replay.pit_windows, replay.hz, t, compounds, pitCounts])

  return (
    <div className="replay-panel">
      <div className="replay-panel-head">
        <h2>Positions</h2>
        <span className="replay-panel-sub">Interval</span>
      </div>
      <ol className="replay-positions">
        {rows.map((row, i) => (
          <li
            key={row.code}
            className={`replay-pos-row${highlighted === row.code ? ' is-active' : ''}${
              selected === row.code ? ' is-selected' : ''
            }${row.running ? '' : ' is-out'}${row.inPit ? ' is-pit' : ''}`}
            onMouseEnter={() => onHoverDriver?.(row.code)}
            onMouseLeave={() => onHoverDriver?.(null)}
          >
            <button
              type="button"
              className="replay-pos-btn"
              onClick={() => onSelectDriver?.(row.code)}
              aria-label={`Show details for ${row.name}`}
            >
              <span className="replay-pos-num">{row.running ? i + 1 : '—'}</span>
              <span className="replay-pos-bar" style={{ background: row.color }} />
              <span className="replay-pos-code">{row.code}</span>
              {row.compound && (
                <span
                  className="replay-pos-tyre"
                  style={{ borderColor: compoundColor(row.compound) }}
                  title={row.compound}
                >
                  {row.compound.slice(0, 1)}
                </span>
              )}
              <span className="replay-pos-gap">{gapLabel(row, i)}</span>
              <span className="replay-pos-pits">
                {row.inPit ? 'PIT' : row.pits > 0 ? `${row.pits}p` : ''}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  )
}

function gapLabel(row: Row, index: number): string {
  if (!row.running) return 'OUT'
  if (index === 0) return row.lap ? `L${row.lap}` : 'Leader'
  if (row.lapsDown >= 1) return `+${row.lapsDown} LAP${row.lapsDown > 1 ? 'S' : ''}`
  if (row.gap == null) return ''
  if (row.gap < 60) return `+${row.gap.toFixed(1)}`
  const m = Math.floor(row.gap / 60)
  return `+${m}:${String(Math.floor(row.gap % 60)).padStart(2, '0')}`
}
