import type {
  ConstructorChampionsResponse,
  DriversResponse,
  PointsWhatIfRequest,
  PointsSystemChangesResponse,
  PodiumigamiResponse,
  RacePrediction,
  RaceReplay,
  RacesResponse,
  ReplaysIndex,
  SeasonLeaderboard,
  WhatIfOptions,
  WhatIfRequest,
} from '../types'
import {
  POINTS_SYSTEM_CHANGES,
  constructorChampionsFromLeaderboard,
  hostedWhatIfPath,
  loadHostedWhatIf,
  whatIfOptionsFromLeaderboard,
} from '../lib/whatIfDefaults'
import type { WhatIfDraft } from '../lib/whatIfStorage'

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(detail || `API ${path} failed: ${res.status}`)
  }
  return res.json() as Promise<T>
}

/** Full leaderboard file served statically for Vercel. */
interface LeaderboardFile {
  seasons: Record<string, SeasonLeaderboard>
}

let leaderboardFilePromise: Promise<LeaderboardFile> | null = null
let formula15FilePromise: Promise<LeaderboardFile> | null = null

function loadLeaderboardFile() {
  if (!leaderboardFilePromise) {
    leaderboardFilePromise = fetchJson<LeaderboardFile>('/api/leaderboard.json').catch((err) => {
      leaderboardFilePromise = null
      throw err
    })
  }
  return leaderboardFilePromise
}

function loadFormula15File() {
  if (!formula15FilePromise) {
    formula15FilePromise = fetchJson<LeaderboardFile>('/api/formula15.json').catch((err) => {
      formula15FilePromise = null
      throw err
    })
  }
  return formula15FilePromise
}

export const api = {
  drivers: () => fetchJson<DriversResponse>('/api/drivers.json'),

  races: () => fetchJson<RacesResponse>('/api/races.json'),

  predictions: (round: number) =>
    fetchJson<RacePrediction>(`/api/predictions_${round}.json`),

  replaysIndex: () => fetchJson<ReplaysIndex>('/api/replays_index.json'),

  replay: (season: number, round: number, session: 'R' | 'S' = 'R') =>
    fetchJson<RaceReplay>(
      session === 'S'
        ? `/api/replays/${season}_${round}_S.json`
        : `/api/replays/${season}_${round}.json`,
    ),

  leaderboard: async (season = 2026) => {
    const data = await loadLeaderboardFile()
    const lb = data.seasons?.[String(season)]
    if (!lb) throw new Error(`No leaderboard for season ${season}`)
    return lb
  },

  formula15: async (season = 2026) => {
    const data = await loadFormula15File()
    const lb = data.seasons?.[String(season)]
    if (!lb) throw new Error(`No Formula 1.5 leaderboard for season ${season}`)
    return lb
  },

  podiumigami: async (season?: number) => {
    const data = await fetchJson<PodiumigamiResponse>('/api/podiums.json')
    if (season == null) return data
    const seasonStats = data.by_season?.[String(season)]
    if (!seasonStats) throw new Error(`No podiumigami data for season ${season}`)
    return {
      from_year: data.from_year,
      hero: data.hero,
      all_time: data.all_time,
      by_season: data.by_season,
      season: seasonStats,
    }
  },

  // Static — no live API needed for the What If form defaults / dropdowns
  whatIfOptions: async (season: number): Promise<WhatIfOptions> =>
    whatIfOptionsFromLeaderboard(await loadLeaderboardFile(), season),

  whatIfConstructorChampions: async (): Promise<ConstructorChampionsResponse> =>
    constructorChampionsFromLeaderboard(await loadLeaderboardFile()),

  whatIfPointsSystemChanges: async (): Promise<PointsSystemChangesResponse> => {
    try {
      return await fetchJson<PointsSystemChangesResponse>('/api/points_system_changes.json')
    } catch {
      return POINTS_SYSTEM_CHANGES
    }
  },

  // Live endpoints — require local api/ (npm run dev + uvicorn)
  whatIf: (body: WhatIfRequest) =>
    fetchJson<SeasonLeaderboard>('/api/what-if', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  whatIfPointsSystem: (body: PointsWhatIfRequest) =>
    fetchJson<SeasonLeaderboard>('/api/what-if/points-system', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  /** Prefers live API; falls back to static JSON for hosted default scenarios. */
  whatIfDraft: async (draft: WhatIfDraft, liveAvailable: boolean): Promise<SeasonLeaderboard> => {
    if (liveAvailable) {
      if (draft.kind === 'points') {
        return api.whatIfPointsSystem({
          season: draft.season,
          points_from: draft.pointsFrom,
          championship: draft.championship,
        })
      }
      return api.whatIf({
        season: draft.season,
        removes: draft.removes.map((r) => ({
          type: draft.removeType,
          name: r.name,
          id: r.id,
        })),
        championship: draft.championship,
      })
    }
    if (hostedWhatIfPath(draft)) return loadHostedWhatIf(draft)
    throw new Error('This What If scenario needs the local DeltaV API')
  },
}
