import type {
  ConstructorChampionsResponse,
  DriversResponse,
  PointsWhatIfRequest,
  PointsSystemChangesResponse,
  PodiumigamiResponse,
  RacePrediction,
  RacesResponse,
  SeasonLeaderboard,
  WhatIfOptions,
  WhatIfRequest,
} from '../types'
import {
  POINTS_SYSTEM_CHANGES,
  constructorChampionsFromLeaderboard,
  whatIfOptionsFromLeaderboard,
} from '../lib/whatIfDefaults'

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

function loadLeaderboardFile() {
  if (!leaderboardFilePromise) {
    leaderboardFilePromise = fetchJson<LeaderboardFile>('/api/leaderboard.json')
  }
  return leaderboardFilePromise
}

export const api = {
  drivers: () => fetchJson<DriversResponse>('/api/drivers.json'),

  races: () => fetchJson<RacesResponse>('/api/races.json'),

  predictions: (round: number) =>
    fetchJson<RacePrediction>(`/api/predictions_${round}.json`),

  leaderboard: async (season = 2026) => {
    const data = await loadLeaderboardFile()
    const lb = data.seasons?.[String(season)]
    if (!lb) throw new Error(`No leaderboard for season ${season}`)
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

  whatIfPointsSystemChanges: async (): Promise<PointsSystemChangesResponse> =>
    POINTS_SYSTEM_CHANGES,

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
}
