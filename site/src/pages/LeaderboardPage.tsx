import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api/client'
import { DriverAvatar } from '../components/DriverAvatar'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { WhatIfClauseText } from '../components/WhatIfClauseText'
import { WhatIfPointsClauseText } from '../components/WhatIfPointsClauseText'
import { lastName, ranksAtStage, sortSeriesAtStage, toLeaderboardChartData } from '../lib/leaderboard'
import { useLiveWhatIfAvailable } from '../lib/useLiveWhatIfAvailable'
import { isHostedWhatIfDraft } from '../lib/whatIfDefaults'
import { formatPoints, roundPoints } from '../lib/points'
import {
  adaptWhatIfDraftToSeason,
  clearWhatIfDraft,
  isPointsWhatIfDraft,
  isRemoveWhatIfDraft,
  loadWhatIfDraft,
  parseWhatIfFromSearchParams,
  saveWhatIfDraft,
  syncActiveWhatIfDraft,
  whatIfQueryKey,
  whatIfSearchParams,
} from '../lib/whatIfStorage'
import type { ChartSeries, LeaderboardStage, SeasonStatRow } from '../types'

const SEASONS = Array.from({ length: 2026 - 1980 + 1 }, (_, i) => 2026 - i)
const FORMULA15_START = 2021

const STAT_CATEGORIES = [
  { key: 'wins' as const, label: 'Wins' },
  { key: 'poles' as const, label: 'Poles' },
  { key: 'podiums' as const, label: 'Podiums' },
  { key: 'dnfs' as const, label: 'DNFs' },
]

function topByStat(
  rows: SeasonStatRow[],
  key: 'wins' | 'poles' | 'podiums' | 'dnfs',
  limit = 5,
) {
  return [...rows]
    .filter((r) => r[key] > 0)
    .sort((a, b) => b[key] - a[key] || a.name.localeCompare(b.name))
    .slice(0, limit)
}

interface TooltipEntry {
  dataKey?: string | number
  value?: number | string
  color?: string
  name?: string
  payload?: Record<string, number | string>
}

function stageGain(
  seriesById: Map<string, ChartSeries>,
  id: string,
  stageId: string,
  cumulative: number,
): number {
  const s = seriesById.get(id)
  if (!s) return roundPoints(cumulative)
  const idx = s.data.findIndex((d) => d.stageId === stageId)
  if (idx <= 0) return roundPoints(cumulative)
  const prev = s.data[idx - 1]?.points ?? 0
  return roundPoints(cumulative - prev)
}

function PosDelta({ delta }: { delta: number | null }) {
  if (delta == null || delta === 0) {
    return <span className="lb-tooltip-pos flat">—</span>
  }
  if (delta > 0) {
    return <span className="lb-tooltip-pos up">+{delta}</span>
  }
  return <span className="lb-tooltip-pos down">{delta}</span>
}

function renderTooltip(
  active: boolean | undefined,
  payload: readonly TooltipEntry[] | undefined,
  label: unknown,
  labelById: Map<string, string>,
  seriesById: Map<string, ChartSeries>,
  series: ChartSeries[],
  stages: LeaderboardStage[],
  mode: 'drivers' | 'constructors',
) {
  if (!active || !payload?.length) return null

  const stageId = String(payload[0]?.payload?.stageId ?? '')
  const stageIdx = stages.findIndex((s) => s.id === stageId)
  const prevStageId = stageIdx > 0 ? stages[stageIdx - 1]?.id : undefined

  const visibleIds = new Set(
    payload.filter((p) => typeof p.value === 'number').map((p) => String(p.dataKey ?? p.name ?? '')),
  )
  const ordered = sortSeriesAtStage(series, stages, stageId).filter((s) => visibleIds.has(s.id))
  const tooltipRows = mode === 'drivers' ? ordered.slice(0, 10) : ordered
  const ranks = ranksAtStage(series, stages, stageId)
  const prevRanks = prevStageId
    ? ranksAtStage(series, stages, prevStageId)
    : new Map<string, number>()

  const colorById = new Map<string, string>()
  for (const p of payload) {
    const key = String(p.dataKey ?? p.name ?? '')
    if (p.color) colorById.set(key, p.color)
  }

  return (
    <div className="lb-tooltip">
      <div className="lb-tooltip-title">{String(label ?? '')}</div>
      <div className="lb-tooltip-rows">
        {tooltipRows.map((s) => {
          const total = s.data.find((d) => d.stageId === stageId)?.points ?? 0
          const gain = stageGain(seriesById, s.id, stageId, total)
          const rank = ranks.get(s.id) ?? 0
          const prev = prevRanks.get(s.id)
          const delta = prev != null && rank ? prev - rank : null
          return (
            <div key={s.id} className="lb-tooltip-row">
              <PosDelta delta={delta} />
              <span
                className="lb-tooltip-dot"
                style={{ background: colorById.get(s.id) ?? s.color }}
              />
              <span className="lb-tooltip-name">{labelById.get(s.id) ?? s.label}</span>
              <span className="lb-tooltip-val">
                {formatPoints(total)}
                <span className="lb-tooltip-gain">+{formatPoints(gain)}</span>
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function EntityThumb({
  series,
  mode,
}: {
  series: ChartSeries
  mode: 'drivers' | 'constructors'
}) {
  if (mode === 'constructors') {
    return (
      <span className="standings-color-bar" style={{ background: series.color }} aria-hidden />
    )
  }

  const raw = (series.code ?? '').toUpperCase()
  // Historical Jolpica rows may use long Ergast ids (e.g. MICHAEL_SCHUMACHER);
  // prefer a real radio code, else the family-name tricode.
  const code = raw.length === 3 ? raw : lastName(series.label).slice(0, 3).toUpperCase()
  return (
    <DriverAvatar
      code={code}
      name={series.label}
      color={series.color}
      image={series.image}
      size={32}
    />
  )
}

function EvoBadge({ delta }: { delta: number | null }) {
  if (delta === null) {
    return <span className="evo flat">—</span>
  }
  if (delta === 0) {
    return <span className="evo flat">0</span>
  }
  if (delta > 0) {
    return (
      <span className="evo up">
        ▲ {delta}
      </span>
    )
  }
  return (
    <span className="evo down">
      ▼ {Math.abs(delta)}
    </span>
  )
}

/** Tick every race; only label a subset when the calendar is dense. */
function RaceAxisTick({
  x,
  y,
  payload,
  index,
  visibleTicksCount,
  labelStep,
}: {
  x?: number | string
  y?: number | string
  payload?: { value?: string }
  index?: number
  visibleTicksCount?: number
  labelStep: number
}) {
  if (x == null || y == null) return null
  const xNum = typeof x === 'number' ? x : Number(x)
  const yNum = typeof y === 'number' ? y : Number(y)
  if (!Number.isFinite(xNum) || !Number.isFinite(yNum)) return null
  const i = index ?? 0
  const last = (visibleTicksCount ?? 1) - 1
  const showLabel = labelStep <= 1 || i === 0 || i === last || i % labelStep === 0

  return (
    <g transform={`translate(${xNum},${yNum})`}>
      <line x1={0} y1={0} x2={0} y2={6} stroke="#666" strokeWidth={1} />
      {showLabel && (
        <text
          dy={14}
          dx={-4}
          textAnchor="end"
          fill="#999"
          fontSize={11}
          transform="rotate(-20)"
        >
          {payload?.value ?? ''}
        </text>
      )}
    </g>
  )
}

function SeasonNav({
  season,
  olderSeason,
  newerSeason,
  onShift,
  onSelect,
}: {
  season: number
  olderSeason: number | null
  newerSeason: number | null
  onShift: (next: number | null) => void
  onSelect: (next: number) => void
}) {
  return (
    <div className="season-nav" role="group" aria-label="Season">
      <button
        type="button"
        className="season-arrow"
        onClick={() => onShift(olderSeason)}
        disabled={olderSeason == null}
        aria-label={olderSeason != null ? `Go to ${olderSeason}` : 'No earlier season'}
      >
        ‹
      </button>
      <label className="season-select">
        <span className="visually-hidden">Season</span>
        <select
          value={season}
          onChange={(e) => {
            onSelect(Number(e.target.value))
            e.currentTarget.blur()
          }}
        >
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
        onClick={() => onShift(newerSeason)}
        disabled={newerSeason == null}
        aria-label={newerSeason != null ? `Go to ${newerSeason}` : 'No later season'}
      >
        ›
      </button>
    </div>
  )
}

function StandingsModeToggle({
  mode,
  onChange,
  className,
}: {
  mode: 'drivers' | 'constructors'
  onChange: (mode: 'drivers' | 'constructors') => void
  className?: string
}) {
  const handleSelect = (next: 'drivers' | 'constructors') => {
    if (next === mode) return
    onChange(next)
  }

  return (
    <div className={className ? `toggle-group ${className}` : 'toggle-group'} role="group" aria-label="Standings type">
      <button
        type="button"
        className={mode === 'drivers' ? 'toggle active' : 'toggle'}
        onClick={(e) => {
          handleSelect('drivers')
          e.currentTarget.blur()
        }}
      >
        Drivers
      </button>
      <button
        type="button"
        className={mode === 'constructors' ? 'toggle active' : 'toggle'}
        onClick={(e) => {
          handleSelect('constructors')
          e.currentTarget.blur()
        }}
      >
        Constructors
      </button>
    </div>
  )
}

function Formula15Toggle({
  active,
  onChange,
  className,
}: {
  active: boolean
  onChange: (active: boolean) => void
  className?: string
}) {
  return (
    <div
      className={className ? `toggle-group ${className}` : 'toggle-group'}
      role="group"
      aria-label="Formula 1.5 standings"
    >
      <button
        type="button"
        className={active ? 'toggle active' : 'toggle'}
        aria-pressed={active}
        onClick={(e) => {
          onChange(!active)
          e.currentTarget.blur()
        }}
      >
        Formula 1.5
      </button>
    </div>
  )
}

export function LeaderboardPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const { available: liveWhatIf } = useLiveWhatIfAvailable()
  const requestedWhatIf = useMemo(() => parseWhatIfFromSearchParams(searchParams), [searchParams])
  const hostedWhatIf = isHostedWhatIfDraft(requestedWhatIf)
  const whatIfRunnable = liveWhatIf || hostedWhatIf
  const whatIfBlocked = Boolean(requestedWhatIf) && !whatIfRunnable
  const whatIfFromUrl = whatIfRunnable ? requestedWhatIf : null
  const whatIfActive = whatIfFromUrl !== null
  const whatIfSeason = whatIfFromUrl?.season ?? 2026
  const whatIfChampionship = whatIfFromUrl?.championship ?? 'drivers'
  const whatIfRemoves = whatIfFromUrl && isRemoveWhatIfDraft(whatIfFromUrl) ? whatIfFromUrl.removes : []
  const whatIfQueryKeyStr = useMemo(
    () => (whatIfFromUrl ? whatIfQueryKey(whatIfFromUrl) : ''),
    [whatIfFromUrl],
  )

  const [season, setSeason] = useState(requestedWhatIf?.season ?? 2026)
  const [mode, setMode] = useState<'drivers' | 'constructors'>(
    requestedWhatIf?.championship ?? (whatIfActive ? whatIfChampionship : 'drivers'),
  )
  const [formula15, setFormula15] = useState(false)
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const scrollLockRef = useRef<number | null>(null)

  const formula15Available = season >= FORMULA15_START && !whatIfActive && !whatIfBlocked
  const formula15Active = formula15 && season >= FORMULA15_START && !whatIfActive

  // Keep active scenario in sync with the URL while viewing the leaderboard
  useEffect(() => {
    if (!whatIfFromUrl) return
    syncActiveWhatIfDraft(whatIfFromUrl)
  }, [whatIfFromUrl])

  // What If and Formula 1.5 are mutually exclusive
  useEffect(() => {
    if (whatIfActive || whatIfBlocked) setFormula15(false)
  }, [whatIfActive, whatIfBlocked])

  // Drop Formula 1.5 when navigating to a season before it exists
  useEffect(() => {
    if (season < FORMULA15_START) setFormula15(false)
  }, [season])

  // Restore saved what-if when Leaderboard nav drops query params
  useEffect(() => {
    // Never overwrite an explicit What If URL (including blocked custom links)
    if (requestedWhatIf) return
    if (whatIfActive && whatIfFromUrl) return
    if (formula15) return
    const draft = loadWhatIfDraft()
    if (!draft) return
    // Hosted site: only restore precomputed default scenarios
    if (!liveWhatIf && !isHostedWhatIfDraft(draft)) return
    navigate(`/leaderboard?${whatIfSearchParams(draft).toString()}`, {
      replace: true,
      preventScrollReset: true,
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- restore once when API/draft becomes available
  }, [liveWhatIf, requestedWhatIf, formula15])

  useEffect(() => {
    if (requestedWhatIf) {
      setSeason(requestedWhatIf.season)
      if (requestedWhatIf.championship) setMode(requestedWhatIf.championship)
      return
    }
    if (!whatIfActive) return
    setSeason(whatIfSeason)
    setMode(whatIfChampionship)
  }, [requestedWhatIf, whatIfActive, whatIfSeason, whatIfChampionship, whatIfQueryKeyStr])

  useEffect(() => {
    if (whatIfActive) {
      setHidden(new Set())
    }
  }, [whatIfActive, whatIfSeason, whatIfQueryKeyStr])

  useEffect(() => {
    if (formula15Active) setHidden(new Set())
  }, [formula15Active, season])

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: whatIfActive
      ? ['what-if', season, whatIfQueryKeyStr, liveWhatIf ? 'live' : 'hosted']
      : formula15Active
        ? ['formula15', season]
        : ['leaderboard', season],
    queryFn: () => {
      if (whatIfFromUrl) {
        return api.whatIfDraft(
          { ...whatIfFromUrl, championship: whatIfChampionship, season },
          liveWhatIf,
        )
      }
      if (formula15Active) return api.formula15(season)
      return api.leaderboard(season)
    },
    enabled: whatIfActive
      ? isPointsWhatIfDraft(whatIfFromUrl!) || whatIfRemoves.length > 0
      : true,
    placeholderData: keepPreviousData,
  })

  const whatIfPointsMeta = data?.what_if?.kind === 'points' ? data.what_if : null

  const whatIfClauseEntities = useMemo(() => {
    if (whatIfPointsMeta) return []
    const fromApi = data?.what_if?.kind !== 'points' ? data?.what_if?.removes : undefined
    if (fromApi?.length) {
      return fromApi.map((r) => ({
        name: r.name,
        color: r.color ?? '#888888',
      }))
    }
    if (whatIfRemoves.length > 0) {
      return whatIfRemoves.map((r) => ({ name: r.name, color: '#888888' }))
    }
    return []
  }, [data?.what_if, whatIfRemoves, whatIfPointsMeta])

  const whatIfActiveClause = whatIfPointsMeta != null || whatIfClauseEntities.length > 0
  const whatIfClauseSeason = data?.what_if?.season ?? whatIfSeason

  const clearWhatIf = () => {
    clearWhatIfDraft()
    navigate('/leaderboard', { preventScrollReset: true })
  }

  const setFormula15Mode = (next: boolean) => {
    if (next === formula15) return
    scrollLockRef.current = window.scrollY
    setHidden(new Set())
    if (next) {
      clearWhatIfDraft()
      if (whatIfActive || requestedWhatIf) {
        navigate('/leaderboard', { preventScrollReset: true })
      }
    }
    setFormula15(next)
  }

  const setModeWithWhatIf = (next: 'drivers' | 'constructors') => {
    if (next === mode) return
    scrollLockRef.current = window.scrollY
    setMode(next)
    if (whatIfActive && whatIfFromUrl) {
      const draft = { ...whatIfFromUrl, championship: next }
      syncActiveWhatIfDraft(draft)
      navigate(`/leaderboard?${whatIfSearchParams(draft).toString()}`, {
        replace: true,
        preventScrollReset: true,
      })
    }
  }

  useLayoutEffect(() => {
    if (scrollLockRef.current == null) return
    const y = scrollLockRef.current
    scrollLockRef.current = null
    window.scrollTo(0, y)
  }, [mode, formula15])

  const applySeasonChange = async (next: number) => {
    if (next === season) return
    setHidden(new Set())
    if (next < FORMULA15_START) setFormula15(false)

    if (!whatIfFromUrl) {
      setSeason(next)
      return
    }

    let options
    if (isRemoveWhatIfDraft(whatIfFromUrl)) {
      try {
        options = await queryClient.fetchQuery({
          queryKey: ['what-if-options', next],
          queryFn: () => api.whatIfOptions(next),
        })
      } catch {
        setSeason(next)
        clearWhatIfDraft()
        navigate('/leaderboard', { preventScrollReset: true })
        return
      }
    }

    const adapted = adaptWhatIfDraftToSeason(
      { ...whatIfFromUrl, championship: mode },
      next,
      options,
    )

    setSeason(next)

    if (!adapted) {
      clearWhatIfDraft()
      navigate('/leaderboard', { preventScrollReset: true })
      return
    }

    // Hosted-only: don't leave a custom whatif=1 URL that falls back to official standings
    if (!liveWhatIf && !isHostedWhatIfDraft(adapted)) {
      clearWhatIfDraft()
      navigate('/leaderboard', { preventScrollReset: true })
      return
    }

    saveWhatIfDraft(adapted)
    navigate(`/leaderboard?${whatIfSearchParams(adapted).toString()}`, {
      replace: true,
      preventScrollReset: true,
    })
  }

  const selectSeason = (next: number) => {
    void applySeasonChange(next)
  }

  const { stages, series } = useMemo(
    () => (data ? toLeaderboardChartData(data, mode) : { stages: [], series: [] }),
    [data, mode],
  )

  const lastStageId = stages[stages.length - 1]?.id
  const prevStageId = stages.length > 1 ? stages[stages.length - 2]?.id : undefined

  const standings = useMemo(() => {
    if (!lastStageId) return []
    return sortSeriesAtStage(series, stages, lastStageId)
  }, [series, stages, lastStageId])

  const officialRanks = useMemo(
    () => (lastStageId ? ranksAtStage(series, stages, lastStageId) : new Map<string, number>()),
    [series, stages, lastStageId],
  )

  const prevRanks = useMemo(
    () => (prevStageId ? ranksAtStage(series, stages, prevStageId) : new Map<string, number>()),
    [series, stages, prevStageId],
  )

  const leaderPts =
    standings.find((s) => !s.disqualified)?.data.find((d) => d.stageId === lastStageId)?.points ?? 0

  const labelById = useMemo(() => {
    const m = new Map<string, string>()
    for (const s of series) m.set(s.id, s.label)
    return m
  }, [series])

  const seriesById = useMemo(() => {
    const m = new Map<string, ChartSeries>()
    for (const s of series) m.set(s.id, s)
    return m
  }, [series])

  const chartRows = useMemo(() => {
    return stages.map((stage) => {
      const row: Record<string, number | string> = {
        stageId: stage.id,
        label: stage.label,
      }
      for (const s of series) {
        const pt = s.data.find((d) => d.stageId === stage.id)
        row[s.id] = pt?.points ?? 0
      }
      return row
    })
  }, [stages, series])

  const yMax = useMemo(() => {
    let max = 0
    for (const s of standings) {
      if (hidden.has(s.id)) continue
      for (const pt of s.data) {
        if (pt.points > max) max = pt.points
      }
    }
    if (max <= 0) return 50
    const step = max > 400 ? 50 : max > 200 ? 25 : 10
    return Math.ceil((max * 1.05) / step) * step
  }, [standings, hidden])

  const xLabelStep = useMemo(() => {
    const n = stages.length
    if (n <= 14) return 1
    if (n <= 20) return 2
    if (n <= 28) return 3
    return Math.ceil(n / 10)
  }, [stages.length])

  const statRows = useMemo(() => {
    if (!data?.stats) return []
    return mode === 'drivers' ? data.stats.drivers : data.stats.constructors
  }, [data?.stats, mode])

  const chartNotes = useMemo(() => {
    const notes = data?.notes ?? []
    if (mode === 'drivers') return notes
    return notes.filter((note) => !note.includes('Grey markers'))
  }, [data?.notes, mode])

  const modeLabel = mode === 'drivers' ? 'Drivers' : 'Constructors'
  const championshipTitle = formula15Active
    ? `Formula 1.5 ${modeLabel} Championship`
    : `${modeLabel} Championship`
  const standingsTitle = formula15Active
    ? `${season} Formula 1.5 ${mode === 'drivers' ? 'Driver' : 'Constructor'} Standings`
    : `${season} ${mode === 'drivers' ? 'Driver' : 'Constructor'} Standings`
  const statsTitle = formula15Active
    ? `${season} Formula 1.5 Season Statistics`
    : `${season} Season Statistics`

  const toggle = (id: string) =>
    setHidden((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  if (isLoading && !data) return <LoadingSkeleton rows={3} />

  if (error) {
    return (
      <section className="page">
        <header className="page-header">
          <h1>Championship</h1>
        </header>
        <p className="what-if-error">Could not load this scenario. Try adjusting your selection.</p>
        <button type="button" className="what-if-submit" onClick={clearWhatIf}>
          Back to normal standings
        </button>
      </section>
    )
  }

  const seasonIndex = SEASONS.indexOf(season)
  const olderSeason = seasonIndex >= 0 && seasonIndex < SEASONS.length - 1 ? SEASONS[seasonIndex + 1] : null
  const newerSeason = seasonIndex > 0 ? SEASONS[seasonIndex - 1] : null

  const shiftSeason = (next: number | null) => {
    if (next == null) return
    selectSeason(next)
  }

  const whatIfClauseEl = whatIfActiveClause ? (
    <>
      {' '}
      {whatIfPointsMeta ? (
        <WhatIfPointsClauseText
          prefix="if "
          season={whatIfPointsMeta.season}
          pointsFrom={whatIfPointsMeta.points_from}
          seasonColor={whatIfPointsMeta.season_color}
          pointsFromColor={whatIfPointsMeta.points_from_color}
        />
      ) : (
        <WhatIfClauseText
          prefix="if "
          entities={whatIfClauseEntities}
          season={whatIfClauseSeason}
        />
      )}
    </>
  ) : null

  const whatIfStatsClauseEl =
    whatIfPointsMeta == null && whatIfClauseEntities.length > 0 ? (
      <>
        {' '}
        <WhatIfClauseText
          prefix="if "
          entities={whatIfClauseEntities}
          season={whatIfClauseSeason}
        />
      </>
    ) : null

  const renderLine = (s: ChartSeries) => {
    if (hidden.has(s.id)) return null
    const hasExcluded = mode === 'drivers' && (s.excludedStages?.size ?? 0) > 0
    return (
      <Line
        key={s.id}
        type="monotone"
        dataKey={s.id}
        name={s.label}
        stroke={s.color}
        strokeWidth={2.5}
        strokeDasharray={s.isSecondDriver ? '6 4' : undefined}
        dot={
          hasExcluded
            ? (props: { cx?: number; cy?: number; payload?: { stageId?: string } }) => {
                const { cx, cy, payload } = props
                if (cx == null || cy == null) return null
                const stageId = String(payload?.stageId ?? '')
                if (!s.excludedStages?.has(stageId)) return null
                return (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={4}
                    fill="#6b6b76"
                    stroke="#9a9aa8"
                    strokeWidth={1}
                  />
                )
              }
            : false
        }
        activeDot={{ r: 5 }}
        animationDuration={500}
        connectNulls
      />
    )
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1 className={whatIfActiveClause ? 'what-if-title' : undefined}>
            {championshipTitle}
            {!formula15Active && whatIfClauseEl}
          </h1>
          {whatIfBlocked && (
            <p className="what-if-local-only lb-what-if-blocked" role="status">
              Alternate standings can only be accessed when the site is run locally. Clone the repo
              to view alternative standings.
            </p>
          )}
          {(whatIfActiveClause || whatIfBlocked) && (
            <button type="button" className="what-if-clear" onClick={clearWhatIf}>
              Clear scenario
            </button>
          )}
        </div>
        <div className="controls-stack">
          <SeasonNav
            season={season}
            olderSeason={olderSeason}
            newerSeason={newerSeason}
            onShift={shiftSeason}
            onSelect={selectSeason}
          />
          <StandingsModeToggle mode={mode} onChange={setModeWithWhatIf} />
          {formula15Available && (
            <Formula15Toggle active={formula15Active} onChange={setFormula15Mode} />
          )}
        </div>
      </header>

      <div className={`lb-layout${isFetching ? ' is-fetching' : ''}`}>
        <div className="chart-panel leaderboard-chart">
          <ResponsiveContainer width="100%" height={520}>
            <LineChart
              key={`${season}-${mode}-${formula15Active ? 'f15' : 'f1'}`}
              data={chartRows}
              margin={{ top: 12, right: 16, left: 8, bottom: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#22222a" vertical={false} />
              <XAxis
                dataKey="label"
                stroke="#666"
                interval={0}
                tick={(props) => <RaceAxisTick {...props} labelStep={xLabelStep} />}
                height={64}
                padding={{ left: 16, right: 8 }}
              />
              <YAxis
                stroke="#666"
                tick={{ fill: '#999' }}
                width={40}
                domain={[0, yMax]}
                allowDataOverflow
              />
              <Tooltip
                content={({ active, payload, label }) =>
                  renderTooltip(
                    active,
                    payload as unknown as TooltipEntry[] | undefined,
                    label,
                    labelById,
                    seriesById,
                    series,
                    stages,
                    mode,
                  )
                }
                cursor={{ stroke: '#444', strokeWidth: 1 }}
              />
              {standings.map(renderLine)}
            </LineChart>
          </ResponsiveContainer>
          {(chartNotes.length > 0) && (
            <div className="scoring-rule-notes">
              {chartNotes.map((note) => (
                <p key={note} className="scoring-rule-note">
                  {note}
                </p>
              ))}
            </div>
          )}
        </div>

        <aside className="standings-panel">
          <div className="standings-head">
            <h3>
              {standingsTitle}
            </h3>
          </div>

          <div className="standings-table-head">
            <span>Pos.</span>
            <span>{mode === 'drivers' ? 'Driver' : 'Team'}</span>
            <span className="right">Points</span>
            <span className="right">Evo.</span>
          </div>

          <div className="standings-table">
            {standings.map((s) => {
              const pts = s.data.find((d) => d.stageId === lastStageId)?.points ?? 0
              const pos = s.disqualified ? null : (officialRanks.get(s.id) ?? null)
              const gap = pos == null || pos === 1 ? null : pts - leaderPts
              const prev = prevRanks.get(s.id)
              const evo = s.disqualified || pos == null || prev == null ? null : prev - pos
              const isHidden = hidden.has(s.id)

              return (
                <button
                  type="button"
                  key={s.id}
                  className={`standings-row ${isHidden ? 'is-hidden' : ''} ${s.disqualified ? 'is-dq' : ''}`}
                  onClick={() => toggle(s.id)}
                  aria-pressed={!isHidden}
                  style={{ borderLeftColor: s.color }}
                >
                  <span className={`standings-pos ${s.disqualified ? 'dq' : ''}`}>
                    {s.disqualified ? 'DQ' : pos}
                  </span>
                  <span className="standings-entity">
                    <EntityThumb series={s} mode={mode} />
                    <span className="standings-name">
                      {mode === 'drivers' ? lastName(s.label) : s.label}
                    </span>
                  </span>
                  <span className="standings-pts-block">
                    <span className="standings-pts">{formatPoints(pts)}</span>
                    {gap != null && <span className="standings-gap">{formatPoints(gap)}</span>}
                  </span>
                  <span className="standings-evo">
                    <EvoBadge delta={evo} />
                  </span>
                </button>
              )
            })}
          </div>
        </aside>
      </div>

      <section
        className={`lb-stats-section${isFetching ? ' is-fetching' : ''}`}
        aria-label={statsTitle}
      >
        <div className="lb-stats-head">
          <h3>
            {statsTitle}
            {!formula15Active && whatIfStatsClauseEl}
          </h3>
          <div className="lb-stats-controls">
            <SeasonNav
              season={season}
              olderSeason={olderSeason}
              newerSeason={newerSeason}
              onShift={shiftSeason}
              onSelect={selectSeason}
            />
            <div className="lb-stats-toggles">
              <StandingsModeToggle mode={mode} onChange={setModeWithWhatIf} className="lb-stats-toggle" />
              {formula15Available && (
                <Formula15Toggle
                  active={formula15Active}
                  onChange={setFormula15Mode}
                  className="lb-stats-toggle"
                />
              )}
            </div>
          </div>
        </div>
        <div className="lb-stats-grid">
          {STAT_CATEGORIES.map(({ key, label }) => {
            const leaders = topByStat(statRows, key)
            return (
              <div key={key} className="lb-stat-card">
                <h4 className="lb-stat-card-title">Most {label}</h4>
                {leaders.length === 0 ? (
                  <p className="lb-stat-empty">—</p>
                ) : (
                  <ol className="lb-stat-list">
                    {leaders.map((row, i) => {
                      const rowKey = mode === 'drivers' ? row.id ?? row.name : row.name
                      const displayName =
                        mode === 'drivers' ? lastName(row.name) : row.name
                      return (
                        <li key={rowKey} className="lb-stat-row">
                          <span className="lb-stat-rank">{i + 1}</span>
                          <span
                            className="lb-stats-swatch"
                            style={{ background: row.color }}
                            aria-hidden
                          />
                          <span className="lb-stat-name">{displayName}</span>
                          <span className="lb-stat-val">{row[key]}</span>
                        </li>
                      )
                    })}
                  </ol>
                )}
              </div>
            )
          })}
        </div>
      </section>
    </section>
  )
}
