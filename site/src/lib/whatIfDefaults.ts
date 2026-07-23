import type {
  ConstructorChampionsResponse,
  PointsSystemChangesResponse,
  WhatIfOptions,
} from '../types'

/** Default remove-from-grid scenario shown on What If. */
export const DEFAULT_WHAT_IF_SEASON = 2026
export const DEFAULT_WHAT_IF_TEAM = 'Mercedes'
export const DEFAULT_WHAT_IF_TEAM_COLOR = '#27F4D2'

/** Default points-system swap scenario. */
export const DEFAULT_POINTS_SEASON = 2021
export const DEFAULT_POINTS_FROM = 2007

/**
 * Hardcoded points-era labels (mirrors pipeline/points_rules.py).
 * Used so the What If points card works without a live API GET.
 */
export const POINTS_SYSTEM_CHANGES: PointsSystemChangesResponse = {
  changes: {
    '1980': '9-6-4-3-2-1',
    '1991': 'Top 6 scored',
    '2003': 'Top 8 scored',
    '2010': '25-point system',
  },
  seasonChanges: {
    '1980': 'Best 5 from first 7, best 5 from the rest',
    '1981': 'Best 11 races counted',
    '1991': 'Top 6 scored',
    '2003': 'Top 8 scored',
    '2010': '25-point system',
  },
  systems: Object.fromEntries(
    Array.from({ length: 2026 - 1980 + 1 }, (_, i) => {
      const year = 1980 + i
      const key =
        year >= 2010
          ? '25,18,15,12,10,8,6,4,2,1'
          : year >= 2003
            ? '10,8,6,5,4,3,2,1'
            : year >= 1991
              ? '10,6,4,3,2,1'
              : '9,6,4,3,2,1'
      return [String(year), key]
    }),
  ),
}

interface LeaderboardFileSeason {
  drivers?: { code?: string; name?: string; team?: string; color?: string }[]
  constructors?: { name?: string; color?: string; disqualified?: boolean }[]
}

interface LeaderboardFile {
  seasons: Record<string, LeaderboardFileSeason>
}

export function whatIfOptionsFromLeaderboard(
  data: LeaderboardFile,
  season: number,
): WhatIfOptions {
  const lb = data.seasons[String(season)]
  if (!lb) throw new Error(`No leaderboard for season ${season}`)
  return {
    season,
    drivers: (lb.drivers ?? [])
      .filter((d) => d.code || d.name)
      .map((d) => ({
        id: String(d.code || d.name),
        name: String(d.name || d.code || ''),
        team: String(d.team || ''),
        color: String(d.color || '#888888'),
      })),
    teams: (lb.constructors ?? [])
      .filter((t) => t.name)
      .map((t) => ({
        name: String(t.name),
        color: String(t.color || '#888888'),
      })),
  }
}

export function constructorChampionsFromLeaderboard(
  data: LeaderboardFile,
): ConstructorChampionsResponse {
  const champions: ConstructorChampionsResponse['champions'] = {}
  for (const [year, lb] of Object.entries(data.seasons)) {
    const constructors = lb.constructors ?? []
    const top =
      constructors.find((t) => !(t as { disqualified?: boolean }).disqualified) ?? constructors[0]
    if (top?.name) {
      champions[year] = {
        name: top.name,
        color: top.color || '#888888',
      }
    }
  }
  return { champions }
}
