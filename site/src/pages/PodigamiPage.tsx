import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { PodiumDisplay } from '../components/PodiumDisplay'
import { TopTriosPodium, TrioRankListModal } from '../components/TrioPodium'
import { countryFlag } from '../lib/countryFlag'
import type {
  PodigamiCombo,
  PodigamiRace,
  PodigamiResponse,
  PodigamiSeasonStats,
} from '../types'

const SEASONS = Array.from({ length: 2026 - 1980 + 1 }, (_, i) => 2026 - i)
const DEFAULT_SEASON = 2026

type Scope = 'yearly' | 'alltime'

/** Keep carousel page size in sync with the CSS column breakpoints. */
function useRacePageSize(): number {
  const [size, setSize] = useState(() => {
    if (typeof window === 'undefined') return 5
    const w = window.innerWidth
    if (w <= 640) return 1
    if (w <= 720) return 2
    if (w <= 1100) return 3
    return 5
  })

  useEffect(() => {
    const update = () => {
      const w = window.innerWidth
      setSize(w <= 640 ? 1 : w <= 720 ? 2 : w <= 1100 ? 3 : 5)
    }
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

  return size
}

function useIsNarrow(maxWidth = 640): boolean {
  const [narrow, setNarrow] = useState(() =>
    typeof window === 'undefined' ? false : window.innerWidth <= maxWidth,
  )
  useEffect(() => {
    const update = () => setNarrow(window.innerWidth <= maxWidth)
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [maxWidth])
  return narrow
}

function SeasonNav({
  season,
  onSelect,
}: {
  season: number
  onSelect: (year: number) => void
}) {
  const idx = SEASONS.indexOf(season)
  const older = idx >= 0 && idx < SEASONS.length - 1 ? SEASONS[idx + 1] : null
  const newer = idx > 0 ? SEASONS[idx - 1] : null

  return (
    <div className="season-nav" role="group" aria-label="Season">
      <button
        type="button"
        className="season-arrow"
        onClick={() => older != null && onSelect(older)}
        disabled={older == null}
        aria-label={older != null ? `Go to ${older}` : 'No earlier season'}
      >
        ‹
      </button>
      <label className="season-select">
        <span className="visually-hidden">Season</span>
        <select value={season} onChange={(e) => onSelect(Number(e.target.value))}>
          {SEASONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="season-arrow"
        onClick={() => newer != null && onSelect(newer)}
        disabled={newer == null}
        aria-label={newer != null ? `Go to ${newer}` : 'No later season'}
      >
        ›
      </button>
    </div>
  )
}

function ScopeToggle({ scope, onChange }: { scope: Scope; onChange: (s: Scope) => void }) {
  return (
    <div className="toggle-group" role="group" aria-label="Stats scope">
      <button
        type="button"
        className={scope === 'yearly' ? 'toggle active' : 'toggle'}
        onClick={() => onChange('yearly')}
      >
        Yearly
      </button>
      <button
        type="button"
        className={scope === 'alltime' ? 'toggle active' : 'toggle'}
        onClick={() => onChange('alltime')}
      >
        All-time
      </button>
    </div>
  )
}

function StatCard({
  label,
  value,
  hint,
  onClick,
}: {
  label: string
  value: string | number
  hint?: string
  onClick?: () => void
}) {
  const className = onClick ? 'podigami-stat is-clickable' : 'podigami-stat'
  if (onClick) {
    return (
      <button type="button" className={className} onClick={onClick}>
        <span className="podigami-stat-label">{label}</span>
        <span className="podigami-stat-value">{value}</span>
        {hint && <span className="podigami-stat-hint">{hint}</span>}
      </button>
    )
  }
  return (
    <div className={className}>
      <span className="podigami-stat-label">{label}</span>
      <span className="podigami-stat-value">{value}</span>
      {hint && <span className="podigami-stat-hint">{hint}</span>}
    </div>
  )
}

function lastOccurredLabel(year: number, eventName: string): string {
  return `Last occurred at the ${year} ${eventName}`
}

function RaceCard({ race }: { race: PodigamiRace }) {
  const flag = countryFlag(race.country)
  const prior =
    !race.is_podigami &&
    race.last_occurred_year != null &&
    race.last_occurred_event
      ? lastOccurredLabel(race.last_occurred_year, race.last_occurred_event)
      : null
  return (
    <article className="podigami-race-row is-compact">
      <div className="podigami-race-meta">
        {flag && (
          <span className="podigami-race-flag" aria-hidden>
            {flag}
          </span>
        )}
        <span className="podigami-race-event">{race.event_name}</span>
        <span className="podigami-race-year">{race.year}</span>
        {race.is_podigami ? (
          <span className="podigami-gold-badge">Podigami</span>
        ) : (
          <span className="podigami-race-badge">×{race.trio_count}</span>
        )}
      </div>
      <PodiumDisplay podium={race.podium} size="compact" className="podigami-race-podium" />
      {prior && <p className="podigami-last-occurred">{prior}</p>}
    </article>
  )
}

function chunkRaces(races: PodigamiRace[], size: number): PodigamiRace[][] {
  const pages: PodigamiRace[][] = []
  for (let i = 0; i < races.length; i += size) {
    pages.push(races.slice(i, i + size))
  }
  return pages
}

function RaceCarousel({ races, title }: { races: PodigamiRace[]; title: string }) {
  const pageSize = useRacePageSize()
  const [page, setPage] = useState(0)
  const pages = useMemo(() => chunkRaces(races, pageSize), [races, pageSize])

  useEffect(() => {
    setPage(0)
  }, [races, pageSize])

  if (races.length === 0) return null

  const pageIndex = Math.min(page, Math.max(0, pages.length - 1))
  const canPrev = pageIndex > 0
  const canNext = pageIndex < pages.length - 1
  const from = pageIndex * pageSize + 1
  const to = Math.min(races.length, from + pages[pageIndex]!.length - 1)

  return (
    <section className="podigami-races">
      <div className="podigami-races-head">
        <h2>{title}</h2>
        {races.length > pageSize && (
          <span className="podigami-races-range">
            {from}–{to} of {races.length}
          </span>
        )}
      </div>
      <div className="podigami-race-carousel">
        {canPrev && (
          <button
            type="button"
            className="podigami-carousel-arrow is-prev"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            aria-label="Previous podiums"
          >
            ‹
          </button>
        )}
        <div className="podigami-race-viewport">
          <div
            className="podigami-race-track"
            style={{ transform: `translate3d(-${pageIndex * 100}%, 0, 0)` }}
          >
            {pages.map((pageRaces, i) => (
              <div key={i} className="podigami-race-page" aria-hidden={i !== pageIndex}>
                {pageRaces.map((race) => (
                  <RaceCard key={`${race.year}-${race.round}`} race={race} />
                ))}
              </div>
            ))}
          </div>
        </div>
        {canNext && (
          <button
            type="button"
            className="podigami-carousel-arrow is-next"
            onClick={() => setPage((p) => Math.min(pages.length - 1, p + 1))}
            aria-label="Next podiums"
          >
            ›
          </button>
        )}
      </div>
    </section>
  )
}

function HeroPodigami({ race }: { race: PodigamiRace }) {
  const narrow = useIsNarrow()
  return (
    <section className="podigami-hero">
      <div className="podigami-hero-head">
        <span className="podigami-hero-label">Most recent podigami</span>
        <h2>
          {race.event_name} <span className="podigami-hero-year">{race.year}</span>
        </h2>
        <p>First time this driver trio had ever shared a podium.</p>
      </div>
      <span className="podigami-gold-badge hero-badge">Podigami</span>
      <PodiumDisplay podium={race.podium} size={narrow ? 'compact' : 'large'} />
    </section>
  )
}

function YearlyPanel({
  seasonStats,
  onOpenRanked,
}: {
  seasonStats: PodigamiSeasonStats
  onOpenRanked: (title: string, trios: PodigamiCombo[]) => void
}) {
  return (
    <div className="podigami-panel">
      <div className="podigami-feature">
        <div className="podigami-feature-head">
          <h2>Most common trios — {seasonStats.year}</h2>
          <p>Top three driver trios this season (finishing order ignored).</p>
        </div>
        <TopTriosPodium
          trios={seasonStats.top_trios}
          onOpenAll={() =>
            onOpenRanked(`All trios — ${seasonStats.year}`, seasonStats.all_trios_ranked)
          }
        />
      </div>

      <div className="podigami-stat-grid">
        <StatCard label="Races" value={seasonStats.total_races} />
        <StatCard
          label="Podigamis"
          value={seasonStats.podigamis}
          hint="First-time trios this year"
          onClick={() =>
            onOpenRanked(`All trios — ${seasonStats.year}`, seasonStats.all_trios_ranked)
          }
        />
      </div>

      <RaceCarousel races={seasonStats.races} title={`Podiums — ${seasonStats.year}`} />
    </div>
  )
}

function AllTimePanel({
  data,
  onOpenRanked,
}: {
  data: PodigamiResponse
  onOpenRanked: (title: string, trios: PodigamiCombo[]) => void
}) {
  const at = data.all_time
  const oneTimePct = at.podigamis
    ? Math.round((at.one_time_only / at.podigamis) * 100)
    : 0

  return (
    <div className="podigami-panel">
      <div className="podigami-feature">
        <div className="podigami-feature-head">
          <h2>Most common trios since 1980</h2>
          <p>Top three driver trios of all time (finishing order ignored).</p>
        </div>
        <TopTriosPodium
          trios={at.top_trios}
          onOpenAll={() => onOpenRanked('All trios since 1980', at.all_trios_ranked)}
        />
      </div>

      <div className="podigami-stat-grid">
        <StatCard label="Total races" value={at.total_races} />
        <StatCard
          label="Podigamis"
          value={at.podigamis}
          hint="Click to see all ranked"
          onClick={() => onOpenRanked('All trios since 1980', at.all_trios_ranked)}
        />
        <StatCard label="One-time only" value={at.one_time_only} hint={`${oneTimePct}% of trios`} />
      </div>

      <div className="podigami-list-card">
        <h3>By decade</h3>
        <p className="podigami-section-desc">Click a decade to see its most common trios.</p>
        <div className="podigami-decade-grid">
          {at.decade_breakdown.map((row) => (
            <button
              key={row.decade}
              type="button"
              className="podigami-decade is-clickable"
              onClick={() => onOpenRanked(`Most common trios — ${row.decade}`, row.all_trios_ranked)}
            >
              <span className="podigami-decade-label">{row.decade}</span>
              <span>{row.races} races</span>
              <span>{row.podigamis} podigamis</span>
            </button>
          ))}
        </div>
      </div>

      <RaceCarousel races={at.recent_races} title="Recent podiums" />
    </div>
  )
}

export function PodigamiPage() {
  const [scope, setScope] = useState<Scope>('yearly')
  const [season, setSeason] = useState(DEFAULT_SEASON)
  const [modal, setModal] = useState<{ title: string; trios: PodigamiCombo[] } | null>(null)

  const { data: fullData, isLoading: fullLoading, isError, refetch } = useQuery({
    queryKey: ['podigami'],
    queryFn: () => api.podigami(),
  })

  const seasonStats = useMemo(() => {
    return fullData?.by_season?.[String(season)] ?? null
  }, [fullData, season])

  // Only the yearly view shows a hero; all-time leads with its own panels
  const hero = useMemo(() => {
    if (scope !== 'yearly') return null
    return seasonStats?.hero ?? seasonStats?.races.find((r) => r.is_podigami) ?? null
  }, [scope, seasonStats])

  useEffect(() => {
    if (!modal) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setModal(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [modal])

  if (fullLoading && !fullData) return <LoadingSkeleton rows={4} />

  if (isError || !fullData) {
    return (
      <section className="page">
        <header className="page-header">
          <h1>Podigami</h1>
        </header>
        <p className="page-empty" role="alert">
          Could not load podigami data.{' '}
          <button type="button" className="what-if-clear" onClick={() => void refetch()}>
            Retry
          </button>
        </p>
      </section>
    )
  }

  const openRanked = (title: string, trios: PodigamiCombo[]) => setModal({ title, trios })

  return (
    <section className="page podigami-page">
      <header className="page-header">
        <div>
          <h1>Podigami</h1>
          <p className="page-subtitle">
            First-time driver trios on the Formula 1 podium since 1980 — finishing order does not
            matter.
          </p>
        </div>
        <div className="controls-stack">
          <ScopeToggle scope={scope} onChange={setScope} />
          {scope === 'yearly' && <SeasonNav season={season} onSelect={setSeason} />}
        </div>
      </header>

      {hero && <HeroPodigami race={hero} />}

      {scope === 'yearly' ? (
        seasonStats ? (
          <YearlyPanel seasonStats={seasonStats} onOpenRanked={openRanked} />
        ) : (
          <p>No podium data for {season}.</p>
        )
      ) : (
        <AllTimePanel data={fullData} onOpenRanked={openRanked} />
      )}

      <p className="podigami-footnote">
        Podigami stats cover Formula 1 Grands Prix from 1980 onward. A podigami is the first
        time a given trio of drivers share a podium; finishing order does not matter.
      </p>

      {modal && (
        <TrioRankListModal
          title={modal.title}
          trios={modal.trios}
          onClose={() => setModal(null)}
        />
      )}
    </section>
  )
}
