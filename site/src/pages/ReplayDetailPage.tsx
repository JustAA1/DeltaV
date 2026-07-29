import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { DriverOverlay } from '../components/replay/DriverOverlay'
import { PositionsPanel } from '../components/replay/PositionsPanel'
import { RaceSwitcher } from '../components/replay/RaceSwitcher'
import { RaceFeed } from '../components/replay/RaceFeed'
import { ReplayControls } from '../components/replay/ReplayControls'
import { TrackMap } from '../components/replay/TrackMap'
import { useReplayClock } from '../lib/useReplayClock'
import { formatEventDate, formatRaceTime } from '../lib/replayUtils'

export function ReplayDetailPage() {
  const params = useParams()
  const season = Number(params.season)
  const round = Number(params.round)

  const { data: replay, isLoading, isError, refetch } = useQuery({
    queryKey: ['replay', season, round],
    queryFn: () => api.replay(season, round),
    enabled: Number.isFinite(season) && Number.isFinite(round) && round > 0,
  })

  const clock = useReplayClock(replay?.duration_s ?? 0, `${season}-${round}`)
  const [highlighted, setHighlighted] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  // Only needed for the overlay's photo; the replay payload carries the rest
  const { data: driversData } = useQuery({
    queryKey: ['drivers'],
    queryFn: () => api.drivers(),
    staleTime: Infinity,
  })
  // Already cached when arriving from the all-races grid
  const { data: index } = useQuery({
    queryKey: ['replays-index'],
    queryFn: api.replaysIndex,
    staleTime: Infinity,
  })

  const driverRecord = useMemo(
    () => driversData?.drivers.find((d) => d.code === selected),
    [driversData, selected],
  )

  /** How much of the race actually has usable GPS, and where it runs out. */
  const coverage = useMemo(() => {
    if (!replay) return null
    const series = Object.values(replay.pos)
    const frames = series[0]?.x?.length ?? 0
    if (!frames) return { fraction: 0, lastT: 0 }
    let covered = 0
    let lastT = 0
    for (let i = 0; i < frames; i += 5) {
      const cars = series.reduce((n, s) => n + (s.x[i] >= 0 ? 1 : 0), 0)
      if (cars >= 10) {
        covered += 1
        lastT = i / replay.hz
      }
    }
    return { fraction: covered / Math.ceil(frames / 5), lastT }
  }, [replay])

  if (isLoading) return <LoadingSkeleton />

  if (isError || !replay) {
    return (
      <section className="page">
        <p className="page-empty" role="alert">
          Could not load this race replay.{' '}
          <button type="button" className="what-if-clear" onClick={() => void refetch()}>
            Retry
          </button>{' '}
          <Link to="/replays" className="replay-back">
            Back to all races
          </Link>
        </p>
      </section>
    )
  }

  return (
    <section className="page replay-page">
      <header className="page-header">
        <div>
          <Link to="/replays" className="replay-back">
            ← All races
          </Link>
          <h1>{replay.event_name}</h1>
          <p className="page-subtitle">
            Round {replay.round} · {replay.circuit}
            {replay.event_date && ` · ${formatEventDate(replay.event_date)}`} ·{' '}
            {replay.total_laps} laps
          </p>
        </div>
        {index && (
          <RaceSwitcher races={index.races ?? []} round={replay.round} season={index.season} />
        )}
      </header>

      {coverage && coverage.fraction < 0.9 && (
        <p className="replay-data-note">
          The position feed only covers about {Math.round(coverage.fraction * 100)}% of this race
          {coverage.lastT > 0 && `, ending around ${formatRaceTime(coverage.lastT)}`}. Cars will
          be missing from the map outside that window.
        </p>
      )}

      {replay.order_source === 'timing' && (
        <p className="replay-data-note">
          The transponder data for this race does not line up with the timing feed, so the running
          order comes from lap times alone. Positions and intervals only update as cars cross the
          start/finish line rather than continuously, and the cars on the map may not match the
          order shown while a lap is in progress.
        </p>
      )}

      <div className="replay-layout">
        <div className="replay-main">
          <ReplayControls
            t={clock.t}
            duration={clock.duration}
            playing={clock.playing}
            speed={clock.speed}
            lapMarkers={replay.lap_markers}
            onToggle={clock.toggle}
            onSeek={clock.seek}
            onSpeed={clock.setSpeed}
            onReset={clock.reset}
          />

          <TrackMap
            replay={replay}
            t={clock.t}
            highlighted={highlighted}
            selected={selected}
            onHoverDriver={setHighlighted}
            onSelectDriver={setSelected}
            inset={<RaceFeed replay={replay} t={clock.t} />}
          />
        </div>

        <aside className="replay-side replay-side-positions">
          <PositionsPanel
            replay={replay}
            t={clock.t}
            highlighted={highlighted}
            selected={selected}
            onHoverDriver={setHighlighted}
            onSelectDriver={setSelected}
          />
        </aside>
      </div>

      {selected && (
        <DriverOverlay
          replay={replay}
          code={selected}
          t={clock.t}
          driverRecord={driverRecord}
          onClose={() => setSelected(null)}
        />
      )}
    </section>
  )
}
