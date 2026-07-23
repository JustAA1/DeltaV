interface RaceSelectorProps {
  rounds: { round: number; event_name: string }[]
  selected: number
  onChange: (round: number) => void
}

export function RaceSelector({ rounds, selected, onChange }: RaceSelectorProps) {
  return (
    <div className="race-selector">
      <label htmlFor="race-round">Race</label>
      <select
        id="race-round"
        value={selected}
        onChange={(e) => onChange(Number(e.target.value))}
      >
        {rounds.map((r) => (
          <option key={r.round} value={r.round}>
            R{r.round} — {r.event_name}
          </option>
        ))}
      </select>
    </div>
  )
}
