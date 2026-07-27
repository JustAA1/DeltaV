import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { PodiumDisplay } from '../components/PodiumDisplay'
import { TopTriosPodium, TrioRankListModal } from '../components/TrioPodium'
import { countryFlag } from '../lib/countryFlag'
import type {
  PodiumigamiCombo,
  PodiumigamiRace,
  PodiumigamiResponse,
  PodiumigamiSeasonStats,
} from '../types'

const SEASONS = Array.from({ length: 2026 - 1980 + 1 }, (_, i) => 2026 - i)
const DEFAULT_SEASON = 2026
const RACE_PAGE_SIZE = 5

type Scope = 'yearly' | 'alltime'

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
  const className = onClick ? 'podiumigami-stat is-clickable' : 'podiumigami-stat'
  if (onClick) {
    return (
      <button type="button" className={className} onClick={onClick}>
        <span className="podiumigami-stat-label">{label}</span>
        <span className="podiumigami-stat-value">{value}</span>
        {hint && <span className="podiumigami-stat-hint">{hint}</span>}
      </button>
    )
  }
  return (
    <div className={className}>
      <span className="podiumigami-stat-label">{label}</span>
      <span className="podiumigami-stat-value">{value}</span>
      {hint && <span className="podiumigami-stat-hint">{hint}</span>}
    </div>
  )
}

function lastOccurredLabel(year: number, eventName: string): string {
  return `Last occurred at the ${year} ${eventName}`
}

function RaceCard({ race }: { race: PodiumigamiRace }) {
  const flag = countryFlag(race.country)
  const prior =
    !race.is_podiumigami &&
    race.last_occurred_year != null &&
    race.last_occurred_event
      ? lastOccurredLabel(race.last_occurred_year, race.last_occurred_event)
      : null
  return (
    <article className="podiumigami-race-row is-compact">
      <div className="podiumigami-race-meta">
        {flag && (
          <span className="podiumigami-race-flag" aria-hidden>
            {flag}
          </span>
        )}
        <span className="podiumigami-race-event">{race.event_name}</span>
        <span className="podiumigami-race-year">{race.year}</span>
        {race.is_podiumigami ? (
          <span className="podiumigami-gold-badge">Podiumigami</span>
        ) : (
          <span className="podiumigami-race-badge">×{race.trio_count}</span>
        )}
      </div>
      <PodiumDisplay podium={race.podium} size="compact" className="podiumigami-race-podium" />
      {prior && <p className="podiumigami-last-occurred">{prior}</p>}
    </article>
  )
}

function chunkRaces(races: PodiumigamiRace[], size: number): PodiumigamiRace[][] {
  const pages: PodiumigamiRace[][] = []
  for (let i = 0; i < races.length; i += size) {
    pages.push(races.slice(i, i + size))
  }
  return pages
}

function RaceCarousel({ races, title }: { races: PodiumigamiRace[]; title: string }) {
  const [page, setPage] = useState(0)
  const pages = useMemo(() => chunkRaces(races, RACE_PAGE_SIZE), [races])

  useEffect(() => {
    setPage(0)
  }, [races])

  if (races.length === 0) return null

  const pageIndex = Math.min(page, Math.max(0, pages.length - 1))
  const canPrev = pageIndex > 0
  const canNext = pageIndex < pages.length - 1
  const from = pageIndex * RACE_PAGE_SIZE + 1
  const to = Math.min(races.length, from + pages[pageIndex]!.length - 1)

  return (
    <section className="podiumigami-races">
      <div className="podiumigami-races-head">
        <h2>{title}</h2>
        {races.length > RACE_PAGE_SIZE && (
          <span className="podiumigami-races-range">
            {from}–{to} of {races.length}
          </span>
        )}
      </div>
      <div className="podiumigami-race-carousel">
        {canPrev && (
          <button
            type="button"
            className="podiumigami-carousel-arrow is-prev"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            aria-label="Previous podiums"
          >
            ‹
          </button>
        )}
        <div className="podiumigami-race-viewport">
          <div
            className="podiumigami-race-track"
            style={{ transform: `translate3d(-${pageIndex * 100}%, 0, 0)` }}
          >
            {pages.map((pageRaces, i) => (
              <div key={i} className="podiumigami-race-page" aria-hidden={i !== pageIndex}>
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
            className="podiumigami-carousel-arrow is-next"
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

function HeroPodiumigami({ race }: { race: PodiumigamiRace }) {
  return (
    <section className="podiumigami-hero">
      <div className="podiumigami-hero-head">
        <span className="podiumigami-hero-label">Most recent podiumigami</span>
        <h2>
          {race.event_name} <span className="podiumigami-hero-year">{race.year}</span>
        </h2>
        <p>First time this driver trio had ever shared a podium.</p>
      </div>
      <span className="podiumigami-gold-badge hero-badge">Podiumigami</span>
      <PodiumDisplay podium={race.podium} size="large" />
    </section>
  )
}

function YearlyPanel({
  seasonStats,
  onOpenRanked,
}: {
  seasonStats: PodiumigamiSeasonStats
  onOpenRanked: (title: string, trios: PodiumigamiCombo[]) => void
}) {
  return (
    <div className="podiumigami-panel">
      <div className="podiumigami-feature">
        <div className="podiumigami-feature-head">
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

      <div className="podiumigami-stat-grid">
        <StatCard label="Races" value={seasonStats.total_races} />
        <StatCard
          label="Podiumigamis"
          value={seasonStats.podiumigamis}
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
  data: PodiumigamiResponse
  onOpenRanked: (title: string, trios: PodiumigamiCombo[]) => void
}) {
  const at = data.all_time
  const oneTimePct = at.podiumigamis
    ? Math.round((at.one_time_only / at.podiumigamis) * 100)
    : 0

  return (
    <div className="podiumigami-panel">
      <div className="podiumigami-feature">
        <div className="podiumigami-feature-head">
          <h2>Most common trios since 1980</h2>
          <p>Top three driver trios of all time (finishing order ignored).</p>
        </div>
        <TopTriosPodium
          trios={at.top_trios}
          onOpenAll={() => onOpenRanked('All trios since 1980', at.all_trios_ranked)}
        />
      </div>

      <div className="podiumigami-stat-grid">
        <StatCard label="Total races" value={at.total_races} />
        <StatCard
          label="Podiumigamis"
          value={at.podiumigamis}
          hint="Click to see all ranked"
          onClick={() => onOpenRanked('All trios since 1980', at.all_trios_ranked)}
        />
        <StatCard label="One-time only" value={at.one_time_only} hint={`${oneTimePct}% of trios`} />
      </div>

      <div className="podiumigami-list-card">
        <h3>By decade</h3>
        <p className="podiumigami-section-desc">Click a decade to see its most common trios.</p>
        <div className="podiumigami-decade-grid">
          {at.decade_breakdown.map((row) => (
            <button
              key={row.decade}
              type="button"
              className="podiumigami-decade is-clickable"
              onClick={() => onOpenRanked(`Most common trios — ${row.decade}`, row.all_trios_ranked)}
            >
              <span className="podiumigami-decade-label">{row.decade}</span>
              <span>{row.races} races</span>
              <span>{row.podiumigamis} podiumigamis</span>
            </button>
          ))}
        </div>
      </div>

      <RaceCarousel races={at.recent_races} title="Recent podiums" />
    </div>
  )
}

export function PodiumigamiPage() {
  const [scope, setScope] = useState<Scope>('yearly')
  const [season, setSeason] = useState(DEFAULT_SEASON)
  const [modal, setModal] = useState<{ title: string; trios: PodiumigamiCombo[] } | null>(null)

  const { data: fullData, isLoading: fullLoading, isError, refetch } = useQuery({
    queryKey: ['podiumigami'],
    queryFn: () => api.podiumigami(),
  })

  const seasonStats = useMemo(() => {
    return fullData?.by_season?.[String(season)] ?? null
  }, [fullData, season])

  const hero = useMemo(() => {
    if (scope === 'yearly') {
      return (
        seasonStats?.hero ??
        seasonStats?.races.find((r) => r.is_podiumigami) ??
        null
      )
    }
    return fullData?.hero ?? null
  }, [scope, seasonStats, fullData?.hero])

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
          <h1>Podiumigami</h1>
        </header>
        <p className="page-empty" role="alert">
          Could not load podiumigami data.{' '}
          <button type="button" className="what-if-clear" onClick={() => void refetch()}>
            Retry
          </button>
        </p>
      </section>
    )
  }

  const openRanked = (title: string, trios: PodiumigamiCombo[]) => setModal({ title, trios })

  return (
    <section className="page podiumigami-page">
      <header className="page-header">
        <div>
          <h1>Podiumigami</h1>
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

      {hero && <HeroPodiumigami race={hero} />}

      {scope === 'yearly' ? (
        seasonStats ? (
          <YearlyPanel seasonStats={seasonStats} onOpenRanked={openRanked} />
        ) : (
          <p>No podium data for {season}.</p>
        )
      ) : (
        <AllTimePanel data={fullData} onOpenRanked={openRanked} />
      )}

      <p className="podiumigami-footnote">
        Podiumigami stats cover Formula 1 Grands Prix from 1980 onward. A podiumigami is the first
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
