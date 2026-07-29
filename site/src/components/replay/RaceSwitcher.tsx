import { useNavigate } from 'react-router-dom'
import type { ReplaysIndexRace } from '../../types'

interface RaceSwitcherProps {
  races: ReplaysIndexRace[]
  /** Round currently being viewed. */
  round: number
  season: number
}

/** Previous / next arrows plus a dropdown for moving between races. */
export function RaceSwitcher({ races, round, season }: RaceSwitcherProps) {
  const navigate = useNavigate()
  const ordered = [...races].sort((a, b) => a.round - b.round)
  if (ordered.length === 0) return null

  const index = ordered.findIndex((r) => r.round === round)
  const prev = index > 0 ? ordered[index - 1] : null
  const next = index >= 0 && index < ordered.length - 1 ? ordered[index + 1] : null

  const go = (race: ReplaysIndexRace | null) => {
    if (race) navigate(`/replays/${race.season}/${race.round}`)
  }

  return (
    <div className="race-switcher">
      <button
        type="button"
        className="race-switcher-arrow"
        onClick={() => go(prev)}
        disabled={!prev}
        aria-label={prev ? `Previous race: ${prev.event_name}` : 'No earlier race'}
        title={prev ? `Previous · ${prev.event_name}` : ''}
      >
        ←
      </button>

      <select
        className="race-switcher-select"
        value={round}
        onChange={(e) => {
          const picked = ordered.find((r) => r.round === Number(e.target.value))
          go(picked ?? null)
        }}
        aria-label="Jump to a race"
      >
        {ordered.map((r) => (
          <option key={r.round} value={r.round}>
            R{String(r.round).padStart(2, '0')} · {r.event_name}
          </option>
        ))}
      </select>

      <button
        type="button"
        className="race-switcher-arrow"
        onClick={() => go(next)}
        disabled={!next}
        aria-label={next ? `Next race: ${next.event_name}` : 'No later race'}
        title={next ? `Next · ${next.event_name}` : ''}
      >
        →
      </button>

      <span className="race-switcher-count">
        {index + 1} / {ordered.length}
        <span className="race-switcher-season"> · {season}</span>
      </span>
    </div>
  )
}
