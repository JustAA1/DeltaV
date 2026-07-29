import { useEffect, useMemo } from 'react'
import { DriverAvatar } from '../DriverAvatar'
import type { DriverRecord, RaceReplay } from '../../types'
import {
  compoundColor,
  formatRaceTime,
  isInPit,
  sampleProgress,
  timeAtProgress,
} from '../../lib/replayUtils'

interface DriverOverlayProps {
  replay: RaceReplay
  code: string
  t: number
  driverRecord?: DriverRecord
  onClose: () => void
}

export function DriverOverlay({ replay, code, t, driverRecord, onClose }: DriverOverlayProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const driver = replay.drivers.find((d) => d.code === code)

  const live = useMemo(() => {
    if (!driver) return null
    const own = replay.prog[code]
    const prog = own ? sampleProgress(own, t, replay.hz) : null

    let position: number | null = null
    let interval: string | null = null
    if (prog != null) {
      const others = replay.drivers
        .map((d) => {
          const s = replay.prog[d.code]
          const p = s ? sampleProgress(s, t, replay.hz) : null
          return p != null && t <= d.end_t_s + 1 ? { code: d.code, p } : null
        })
        .filter((v): v is { code: string; p: number } => v !== null)
        .sort((a, b) => b.p - a.p)
      const i = others.findIndex((o) => o.code === code)
      if (i >= 0) {
        position = i + 1
        const ahead = others[i - 1]
        if (ahead) {
          const lapsDown = Math.floor(ahead.p - others[i].p)
          if (lapsDown >= 1) {
            interval = `+${lapsDown} LAP${lapsDown > 1 ? 'S' : ''}`
          } else {
            const series = replay.prog[ahead.code]
            const then = series ? timeAtProgress(series, others[i].p, replay.hz) : null
            if (then != null) interval = `+${Math.max(0, t - then).toFixed(1)}s`
          }
        }
      }
    }

    const stints = replay.stints.filter((s) => s.code === code)
    const current = [...stints].reverse().find((s) => s.t_start_s <= t)
    return {
      prog,
      lap: prog != null ? Math.floor(prog) + 1 : null,
      position,
      interval,
      compound: current?.compound ?? null,
      stops: replay.pits.filter((p) => p.code === code && p.t_s <= t).length,
      inPit: isInPit(replay.pit_windows?.[code], t),
      retired: t > driver.end_t_s + 1,
    }
  }, [replay, code, t, driver])

  const stints = useMemo(
    () => replay.stints.filter((s) => s.code === code).sort((a, b) => a.stint - b.stint),
    [replay.stints, code],
  )

  if (!driver || !live) return null

  const totalLaps = Math.max(1, replay.total_laps)

  return (
    <div className="trio-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="trio-modal replay-driver-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`${driver.name} race detail`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="trio-modal-head">
          <div className="replay-driver-id">
            <DriverAvatar
              code={driver.code}
              name={driver.name}
              color={driver.color || '#888'}
              image={driverRecord?.image ?? null}
              size={54}
            />
            <div>
              <h2>{driver.name}</h2>
              <p className="replay-driver-team">
                #{driver.number} · {driver.team}
              </p>
            </div>
          </div>
          <button type="button" className="trio-modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="replay-driver-body">
          <div className="replay-driver-stats">
            <Stat label="Position" value={live.retired ? 'OUT' : (live.position ?? '—')} />
            <Stat label="Lap" value={live.lap ? `${live.lap} / ${totalLaps}` : '—'} />
            <Stat label="Interval" value={live.inPit ? 'IN PIT' : (live.interval ?? 'Leader')} />
            <Stat label="Tyre" value={live.compound ?? '—'} />
            <Stat label="Stops" value={live.stops} />
            <PositionDelta grid={driver.grid} position={live.retired ? null : live.position} />
          </div>

          <p className="replay-driver-status">
            {driver.status}
            {' · at '}
            {formatRaceTime(t)}
          </p>

          <section className="replay-driver-section">
            <h3>Stint history</h3>
            {stints.length === 0 ? (
              <p className="replay-driver-empty">No stint data for this car.</p>
            ) : (
              <>
                <div className="replay-stint-strip">
                  {stints.map((s) => {
                    const laps = Math.max(1, s.end_lap - s.start_lap + 1)
                    return (
                      <span
                        key={s.stint}
                        className="replay-stint-chunk"
                        style={{
                          background: compoundColor(s.compound),
                          // Share of the whole race, so a car that retires early
                          // leaves the rest of the rail empty
                          width: `${(laps / totalLaps) * 100}%`,
                        }}
                        title={`${s.compound} · L${s.start_lap}–${s.end_lap} (${laps} laps)`}
                      >
                        {s.compound.slice(0, 1)}
                      </span>
                    )
                  })}
                  {/* Everything past the current lap is dimmed, so the strip fills
                      in as the replay plays */}
                  <span
                    className="replay-stint-future"
                    style={{ left: `${racePct(live.prog, totalLaps)}%` }}
                  />
                </div>
                <ul className="replay-stint-key">
                  {stints.map((s) => (
                    <li key={s.stint}>
                      <i style={{ background: compoundColor(s.compound) }} />
                      {s.compound} · L{s.start_lap}–{s.end_lap}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}

/** How far through the race a car is, as a percentage of total laps. */
function racePct(prog: number | null, totalLaps: number): number {
  if (prog == null) return 0
  return Math.max(0, Math.min(100, (prog / totalLaps) * 100))
}

function PositionDelta({ grid, position }: { grid: number | null; position: number | null }) {
  const gained = grid && grid > 0 && position ? grid - position : null
  const tone = gained == null || gained === 0 ? 'even' : gained > 0 ? 'up' : 'down'
  return (
    <div className="replay-driver-stat">
      <span className="replay-driver-stat-label">Grid → Pos</span>
      <span className="replay-driver-stat-value">
        {grid && grid > 0 ? grid : '—'} → {position ?? '—'}
        {gained != null && (
          <span className={`replay-pos-delta is-${tone}`}>
            {gained > 0 ? `+${gained}` : gained < 0 ? gained : '='}
          </span>
        )}
      </span>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="replay-driver-stat">
      <span className="replay-driver-stat-label">{label}</span>
      <span className="replay-driver-stat-value">{value}</span>
    </div>
  )
}
