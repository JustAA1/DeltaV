import type { ReplayFlag, ReplayLapMarker } from '../../types'
import {
  FLAG_LABEL_COLORS,
  formatRaceTime,
  REPLAY_SPEEDS,
  type ReplaySpeed,
} from '../../lib/replayUtils'

interface ReplayControlsProps {
  t: number
  duration: number
  playing: boolean
  speed: ReplaySpeed
  lapMarkers: ReplayLapMarker[]
  flags?: ReplayFlag[]
  onToggle: () => void
  onSeek: (t: number) => void
  onSpeed: (s: ReplaySpeed) => void
  onReset: () => void
}

/** Stronger fills for the thin scrubber so SC / VSC / RED actually read. */
const SCRUBBER_FLAG_FILL: Record<string, string> = {
  SC: 'rgba(255, 184, 0, 0.82)',
  VSC: 'rgba(245, 215, 110, 0.75)',
  RED: 'rgba(239, 68, 68, 0.82)',
}

function flagLabel(type: string): string {
  return type === 'RED' ? 'RED' : type
}

export function ReplayControls({
  t,
  duration,
  playing,
  speed,
  lapMarkers,
  flags = [],
  onToggle,
  onSeek,
  onSpeed,
  onReset,
}: ReplayControlsProps) {
  const currentLap =
    [...lapMarkers].reverse().find((m) => m.t_s <= t)?.lap ??
    (lapMarkers[0]?.lap ?? null)

  const span = Math.max(1, duration)
  const periods = flags.filter((f) => f.t_end_s > f.t_start_s)

  return (
    <div className="replay-controls">
      <div className="replay-controls-row">
        <button type="button" className="replay-btn" onClick={onReset} aria-label="Reset to start">
          ⏮
        </button>
        <button
          type="button"
          className="replay-btn replay-btn-play"
          onClick={onToggle}
          aria-label={playing ? 'Pause' : 'Play'}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
        <div className="toggle-group replay-speed-group" role="group" aria-label="Playback speed">
          {REPLAY_SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              className={`toggle${speed === s ? ' active' : ''}`}
              onClick={() => onSpeed(s)}
            >
              {s}×
            </button>
          ))}
        </div>
        <div className="replay-time" aria-live="polite">
          <span>{formatRaceTime(t)}</span>
          <span className="replay-time-sep">/</span>
          <span>{formatRaceTime(duration)}</span>
          {currentLap != null && (
            <span className="replay-lap-badge">Lap {currentLap}</span>
          )}
        </div>
      </div>

      <div className={`replay-scrubber${periods.length ? ' has-flags' : ''}`}>
        {/* Labels sit above the rail so short VSC windows still get a readable tag. */}
        {periods.length > 0 && (
          <div className="replay-scrubber-labels" aria-hidden>
            {periods.map((f, i) => {
              const left = (Math.max(0, f.t_start_s) / span) * 100
              const right = (Math.min(span, f.t_end_s) / span) * 100
              const mid = (left + right) / 2
              return (
                <span
                  key={`label-${f.type}-${f.t_start_s}-${i}`}
                  className={`replay-scrubber-flag-label is-${f.type.toLowerCase()}`}
                  style={{
                    left: `${mid}%`,
                    color: FLAG_LABEL_COLORS[f.type] ?? '#ccc',
                  }}
                >
                  {flagLabel(f.type)}
                </span>
              )
            })}
          </div>
        )}

        <div className="replay-scrubber-body">
          <div className="replay-scrubber-rail" aria-hidden>
            {/* Elapsed fill behind the flag bands. */}
            <span
              className="replay-scrubber-played"
              style={{ width: `${Math.min(100, (Math.max(0, t) / span) * 100)}%` }}
            />
            {periods.map((f, i) => {
              const left = (Math.max(0, f.t_start_s) / span) * 100
              const right = (Math.min(span, f.t_end_s) / span) * 100
              const width = Math.max(0.4, right - left)
              return (
                <span
                  key={`band-${f.type}-${f.t_start_s}-${i}`}
                  className={`replay-scrubber-flag is-${f.type.toLowerCase()}`}
                  style={{
                    left: `${left}%`,
                    width: `${width}%`,
                    background: SCRUBBER_FLAG_FILL[f.type] ?? 'rgba(255,255,255,0.35)',
                  }}
                  title={`${flagLabel(f.type)} · ${formatRaceTime(f.t_start_s)}–${formatRaceTime(f.t_end_s)}`}
                />
              )
            })}
          </div>

          <label className="replay-scrubber-input-wrap">
            <span className="visually-hidden">Race progress</span>
            <input
              type="range"
              className="replay-scrubber-input"
              min={0}
              max={Math.max(1, duration)}
              step={0.25}
              value={Math.min(t, duration)}
              onChange={(e) => onSeek(Number(e.target.value))}
            />
          </label>
        </div>
      </div>
    </div>
  )
}
