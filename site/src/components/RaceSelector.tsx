interface RaceSelectorProps {
  rounds: { round: number; event_name: string }[]
  selected: number
  onChange: (round: number) => void
}

export function RaceSelector({ rounds, selected, onChange }: RaceSelectorProps) {
  const index = rounds.findIndex((r) => r.round === selected)
  const prev = index > 0 ? rounds[index - 1] : null
  const next = index >= 0 && index < rounds.length - 1 ? rounds[index + 1] : null

  return (
    <div className="season-nav race-nav" role="group" aria-label="Race">
      <button
        type="button"
        className="season-arrow"
        onClick={() => prev && onChange(prev.round)}
        disabled={prev == null}
        aria-label={prev ? `Go to round ${prev.round}` : 'No earlier race'}
      >
        ‹
      </button>
      <label className="season-select race-select">
        <span className="visually-hidden">Race</span>
        <select
          value={selected}
          onChange={(e) => {
            onChange(Number(e.target.value))
            e.currentTarget.blur()
          }}
        >
          {rounds.map((r) => (
            <option key={r.round} value={r.round}>
              R{r.round} — {r.event_name}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="season-arrow"
        onClick={() => next && onChange(next.round)}
        disabled={next == null}
        aria-label={next ? `Go to round ${next.round}` : 'No later race'}
      >
        ›
      </button>
    </div>
  )
}
