interface SeasonSwitcherProps {
  /** Every season with replay data, ascending. */
  seasons: number[]
  season: number
  onSeason: (season: number) => void
  raceCount: number
}

/** Year picker for the all-races overview: older / newer arrows plus a dropdown. */
export function SeasonSwitcher({ seasons, season, onSeason, raceCount }: SeasonSwitcherProps) {
  if (seasons.length === 0) return null

  const i = seasons.indexOf(season)
  const older = i > 0 ? seasons[i - 1] : null
  const newer = i >= 0 && i < seasons.length - 1 ? seasons[i + 1] : null

  return (
    <div className="race-switcher">
      <button
        type="button"
        className="race-switcher-arrow"
        onClick={() => older != null && onSeason(older)}
        disabled={older == null}
        aria-label={older != null ? `Previous season: ${older}` : 'No earlier season'}
        title={older != null ? `${older} season` : ''}
      >
        ←
      </button>

      <select
        className="race-switcher-select is-season"
        value={season}
        onChange={(e) => onSeason(Number(e.target.value))}
        aria-label="Season"
      >
        {[...seasons].reverse().map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>

      <button
        type="button"
        className="race-switcher-arrow"
        onClick={() => newer != null && onSeason(newer)}
        disabled={newer == null}
        aria-label={newer != null ? `Next season: ${newer}` : 'No later season'}
        title={newer != null ? `${newer} season` : ''}
      >
        →
      </button>

      <span className="race-switcher-count">
        {raceCount} {raceCount === 1 ? 'race' : 'races'}
      </span>
    </div>
  )
}
