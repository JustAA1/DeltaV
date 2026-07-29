import { useMemo } from 'react'
import type { RaceReplay } from '../../types'
import {
  compoundColor,
  FLAG_COLORS,
  FLAG_LABEL_COLORS,
  formatRaceTime,
} from '../../lib/replayUtils'

interface StintTimelineProps {
  replay: RaceReplay
  t: number
  highlighted?: string | null
  onHoverDriver?: (code: string | null) => void
  onSeek?: (t: number) => void
}

const ROW_H = 22
const LABEL_W = 44
const PAD_TOP = 18
const PAD_BOTTOM = 8

export function StintTimeline({
  replay,
  t,
  highlighted,
  onHoverDriver,
  onSeek,
}: StintTimelineProps) {
  const duration = Math.max(1, replay.duration_s)
  const drivers = replay.drivers
  const height = PAD_TOP + drivers.length * ROW_H + PAD_BOTTOM

  const stintsByDriver = useMemo(() => {
    const map = new Map<string, typeof replay.stints>()
    for (const s of replay.stints) {
      const list = map.get(s.code) ?? []
      list.push(s)
      map.set(s.code, list)
    }
    return map
  }, [replay.stints])

  const pitsByDriver = useMemo(() => {
    const map = new Map<string, typeof replay.pits>()
    for (const p of replay.pits) {
      const list = map.get(p.code) ?? []
      list.push(p)
      map.set(p.code, list)
    }
    return map
  }, [replay.pits])

  const xOf = (sec: number, width: number) => LABEL_W + (sec / duration) * (width - LABEL_W)

  return (
    <div className="replay-stints">
      <div className="replay-stints-header">
        <h2>Race picture</h2>
        <div className="replay-legend">
          <span className="replay-legend-item">
            <i style={{ background: compoundColor('SOFT') }} /> Soft
          </span>
          <span className="replay-legend-item">
            <i style={{ background: compoundColor('MEDIUM') }} /> Medium
          </span>
          <span className="replay-legend-item">
            <i style={{ background: compoundColor('HARD') }} /> Hard
          </span>
          <span className="replay-legend-item">
            <i style={{ background: compoundColor('INTERMEDIATE') }} /> Inter
          </span>
          <span className="replay-legend-item">
            <i style={{ background: compoundColor('WET') }} /> Wet
          </span>
          <span className="replay-legend-item">
            <i className="flag-sc" /> SC
          </span>
          <span className="replay-legend-item">
            <i className="flag-vsc" /> VSC
          </span>
        </div>
      </div>

      <div className="replay-stints-scroll">
        <svg
          className="replay-stints-svg"
          viewBox={`0 0 800 ${height}`}
          preserveAspectRatio="none"
          role="img"
          aria-label="Tyre stint timeline"
          onClick={(e) => {
            if (!onSeek) return
            const svg = e.currentTarget
            const rect = svg.getBoundingClientRect()
            const x = ((e.clientX - rect.left) / rect.width) * 800
            if (x < LABEL_W) return
            const sec = ((x - LABEL_W) / (800 - LABEL_W)) * duration
            onSeek(Math.max(0, Math.min(duration, sec)))
          }}
        >
          {/* Flag bands */}
          {replay.flags.map((f, i) => {
            const x1 = xOf(f.t_start_s, 800)
            const x2 = xOf(f.t_end_s, 800)
            return (
              <g key={`flag-${i}`}>
                <rect
                  x={x1}
                  y={PAD_TOP - 4}
                  width={Math.max(1, x2 - x1)}
                  height={drivers.length * ROW_H + 4}
                  fill={FLAG_COLORS[f.type] ?? 'rgba(255,255,255,0.1)'}
                />
                <text
                  x={(x1 + x2) / 2}
                  y={12}
                  textAnchor="middle"
                  fill={FLAG_LABEL_COLORS[f.type] ?? '#ccc'}
                  fontSize={10}
                  fontWeight={700}
                >
                  {f.type}
                </text>
              </g>
            )
          })}

          {drivers.map((drv, row) => {
            const y = PAD_TOP + row * ROW_H
            const stints = stintsByDriver.get(drv.code) ?? []
            const pits = pitsByDriver.get(drv.code) ?? []
            const isHi = highlighted === drv.code
            return (
              <g
                key={drv.code}
                onMouseEnter={() => onHoverDriver?.(drv.code)}
                onMouseLeave={() => onHoverDriver?.(null)}
                style={{ cursor: 'pointer' }}
              >
                <rect
                  x={0}
                  y={y}
                  width={800}
                  height={ROW_H}
                  fill={isHi ? 'rgba(255,255,255,0.06)' : 'transparent'}
                />
                <text
                  x={4}
                  y={y + ROW_H / 2 + 1}
                  dominantBaseline="middle"
                  fill={drv.color}
                  fontSize={11}
                  fontWeight={700}
                >
                  {drv.code}
                </text>
                {stints.map((s) => {
                  const x1 = xOf(Math.max(0, s.t_start_s), 800)
                  const x2 = xOf(Math.min(duration, Math.max(s.t_end_s, s.t_start_s + 1)), 800)
                  const w = Math.max(2, x2 - x1)
                  return (
                    <rect
                      key={`${s.code}-${s.stint}`}
                      x={x1}
                      y={y + 4}
                      width={w}
                      height={ROW_H - 8}
                      rx={3}
                      fill={compoundColor(s.compound)}
                      opacity={0.9}
                      stroke={isHi ? '#fff' : 'rgba(0,0,0,0.35)'}
                      strokeWidth={isHi ? 1.25 : 0.5}
                    >
                      <title>
                        {drv.code} · {s.compound} · L{s.start_lap}–{s.end_lap}
                      </title>
                    </rect>
                  )
                })}
                {pits.map((p, i) => {
                  const x = xOf(p.t_s, 800)
                  return (
                    <line
                      key={`pit-${drv.code}-${i}`}
                      x1={x}
                      x2={x}
                      y1={y + 3}
                      y2={y + ROW_H - 3}
                      stroke="#111"
                      strokeWidth={2}
                    >
                      <title>
                        {drv.code} pit · Lap {p.lap} · {formatRaceTime(p.t_s)}
                      </title>
                    </line>
                  )
                })}
              </g>
            )
          })}

          {/* Playhead */}
          <line
            x1={xOf(t, 800)}
            x2={xOf(t, 800)}
            y1={PAD_TOP - 6}
            y2={PAD_TOP + drivers.length * ROW_H}
            stroke="#fff"
            strokeWidth={1.5}
            opacity={0.9}
          />
        </svg>
      </div>
    </div>
  )
}
