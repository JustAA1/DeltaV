import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { ReplayCard } from '../components/replay/ReplayCard'
import { SeasonSwitcher } from '../components/replay/SeasonSwitcher'

export function ReplaysPage() {
  const [params, setParams] = useSearchParams()
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['replays-index'],
    queryFn: api.replaysIndex,
  })

  // Winner photos live in drivers.json, keyed by code
  const { data: driversData } = useQuery({
    queryKey: ['drivers'],
    queryFn: () => api.drivers(),
    staleTime: Infinity,
  })
  const byCode = useMemo(
    () => new Map((driversData?.drivers ?? []).map((d) => [d.code, d])),
    [driversData],
  )

  // Seasons come from the races themselves, so new ones appear as the pipeline
  // backfills them without any change here.
  const seasons = useMemo(() => {
    const years = new Set((data?.races ?? []).map((r) => r.season))
    if (data?.season) years.add(data.season)
    return [...years].sort((a, b) => a - b)
  }, [data])

  if (isLoading) return <LoadingSkeleton />

  if (isError || !data) {
    return (
      <section className="page">
        <p className="page-empty" role="alert">
          Could not load replays.{' '}
          <button type="button" className="what-if-clear" onClick={() => void refetch()}>
            Retry
          </button>
        </p>
      </section>
    )
  }

  const requested = Number(params.get('season'))
  const season = seasons.includes(requested) ? requested : (seasons.at(-1) ?? data.season)
  const races = (data.races ?? [])
    .filter((r) => r.season === season)
    .sort((a, b) => a.round - b.round)

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Replays</h1>
          <p className="page-subtitle">
            Track-map playback of every completed {season} race
          </p>
        </div>
        <SeasonSwitcher
          seasons={seasons}
          season={season}
          raceCount={races.length}
          onSeason={(next) => setParams({ season: String(next) })}
        />
      </header>

      {races.length === 0 ? (
        <p className="page-empty">
          No replay data for {season} yet. Run{' '}
          <code>python replays.py --season {season} --max-round 11 --sync</code> in{' '}
          <code>pipeline/</code>.
        </p>
      ) : (
        <div className="replay-card-grid">
          {races.map((race) => (
            <ReplayCard
              key={`${race.season}-${race.round}`}
              race={race}
              driver={race.winner ? byCode.get(race.winner.code) : undefined}
            />
          ))}
        </div>
      )}
    </section>
  )
}
