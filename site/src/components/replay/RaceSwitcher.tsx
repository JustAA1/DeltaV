import { useNavigate } from 'react-router-dom'
import type { ReplaysIndexRace } from '../../types'
import { replayPath, sortReplays, sessionOf } from '../../lib/replayUtils'

interface RaceSwitcherProps {
  races: ReplaysIndexRace[]
  /** Round currently being viewed. */
  round: number
  /** Session currently being viewed. */
  session?: 'R' | 'S'
  season: number
}

/** Previous / next arrows plus a dropdown for moving between races and sprints. */
export function RaceSwitcher({ races, round, session = 'R', season }: RaceSwitcherProps) {
  const navigate = useNavigate()
  const ordered = sortReplays(races)
  if (ordered.length === 0) return null

  const index = ordered.findIndex(
    (r) => r.round === round && sessionOf(r) === session,
  )
  const prev = index > 0 ? ordered[index - 1] : null
  const next = index >= 0 && index < ordered.length - 1 ? ordered[index + 1] : null
  const currentKey = `${round}_${session}`

  const go = (race: ReplaysIndexRace | null) => {
    if (race) navigate(replayPath(race))
  }

  return (
    <div className="race-switcher">
      <button
        type="button"
        className="race-switcher-arrow"
        onClick={() => go(prev)}
        disabled={!prev}
        aria-label={prev ? `Previous: ${prev.event_name}` : 'No earlier session'}
        title={prev ? `Previous · ${prev.event_name}` : ''}
      >
        ←
      </button>

      <select
        className="race-switcher-select"
        value={currentKey}
        onChange={(e) => {
          const picked = ordered.find(
            (r) => `${r.round}_${sessionOf(r)}` === e.target.value,
          )
          go(picked ?? null)
        }}
        aria-label="Jump to a race"
      >
        {ordered.map((r) => {
          const sess = sessionOf(r)
          const label =
            sess === 'S'
              ? `R${String(r.round).padStart(2, '0')}S · ${r.event_name}`
              : `R${String(r.round).padStart(2, '0')} · ${r.event_name}`
          return (
            <option key={`${r.round}_${sess}`} value={`${r.round}_${sess}`}>
              {label}
            </option>
          )
        })}
      </select>

      <button
        type="button"
        className="race-switcher-arrow"
        onClick={() => go(next)}
        disabled={!next}
        aria-label={next ? `Next: ${next.event_name}` : 'No later session'}
        title={next ? `Next · ${next.event_name}` : ''}
      >
        →
      </button>

      <span className="race-switcher-count">
        {index >= 0 ? index + 1 : '—'} / {ordered.length}
        <span className="race-switcher-season"> · {season}</span>
      </span>
    </div>
  )
}
