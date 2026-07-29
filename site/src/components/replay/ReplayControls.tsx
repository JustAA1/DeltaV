import type { ReplayLapMarker } from '../../types'
import { formatRaceTime, REPLAY_SPEEDS, type ReplaySpeed } from '../../lib/replayUtils'

interface ReplayControlsProps {
  t: number
  duration: number
  playing: boolean
  speed: ReplaySpeed
  lapMarkers: ReplayLapMarker[]
  onToggle: () => void
  onSeek: (t: number) => void
  onSpeed: (s: ReplaySpeed) => void
  onReset: () => void
}

export function ReplayControls({
  t,
  duration,
  playing,
  speed,
  lapMarkers,
  onToggle,
  onSeek,
  onSpeed,
  onReset,
}: ReplayControlsProps) {
  const currentLap =
    [...lapMarkers].reverse().find((m) => m.t_s <= t)?.lap ??
    (lapMarkers[0]?.lap ?? null)

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

      <label className="replay-scrubber">
        <span className="visually-hidden">Race progress</span>
        <input
          type="range"
          min={0}
          max={Math.max(1, duration)}
          step={0.25}
          value={Math.min(t, duration)}
          onChange={(e) => onSeek(Number(e.target.value))}
        />
      </label>
    </div>
  )
}
