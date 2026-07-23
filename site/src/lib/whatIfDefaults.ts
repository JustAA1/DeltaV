import type {
  ConstructorChampionsResponse,
  PointsSystemChangesResponse,
  SeasonLeaderboard,
  WhatIfOptions,
} from '../types'
import type { PointsWhatIfDraft, RemoveWhatIfDraft, WhatIfDraft } from './whatIfStorage'
import pointsSystemChangesFallback from './pointsSystemChanges.fallback.json'

/** Default remove-from-grid scenario shown on What If. */
export const DEFAULT_WHAT_IF_SEASON = 2026
export const DEFAULT_WHAT_IF_TEAM = 'Mercedes'
export const DEFAULT_WHAT_IF_TEAM_COLOR = '#27F4D2'

/** Default points-system swap scenario. */
export const DEFAULT_POINTS_SEASON = 2021
export const DEFAULT_POINTS_FROM = 2007

/** Static precomputed payloads for hosted default scenarios (no live API). */
export const DEFAULT_REMOVE_WHAT_IF_PATH = '/api/whatif_remove_2026_mercedes.json'
export const DEFAULT_POINTS_WHAT_IF_PATH = '/api/whatif_points_2021_from_2007.json'

export function isDefaultRemoveSelection(
  season: number,
  entityType: 'driver' | 'team',
  selectedValues: string[],
): boolean {
  if (season !== DEFAULT_WHAT_IF_SEASON || entityType !== 'team' || selectedValues.length !== 1) {
    return false
  }
  const value = selectedValues[0].trim().toLowerCase()
  return value === DEFAULT_WHAT_IF_TEAM.toLowerCase()
}

export function isDefaultPointsSelection(season: number, pointsFrom: number): boolean {
  return season === DEFAULT_POINTS_SEASON && pointsFrom === DEFAULT_POINTS_FROM
}

export function isDefaultRemoveDraft(draft: RemoveWhatIfDraft): boolean {
  return isDefaultRemoveSelection(
    draft.season,
    draft.removeType,
    draft.removes.map((r) => (draft.removeType === 'driver' ? r.id ?? r.name : r.name)),
  )
}

export function isDefaultPointsDraft(draft: PointsWhatIfDraft): boolean {
  return isDefaultPointsSelection(draft.season, draft.pointsFrom)
}

/** Whether this scenario can be served from static JSON without the local API. */
export function isHostedWhatIfDraft(draft: WhatIfDraft | null | undefined): boolean {
  if (!draft) return false
  if (draft.kind === 'points') return isDefaultPointsDraft(draft)
  return isDefaultRemoveDraft(draft)
}

export function hostedWhatIfPath(draft: WhatIfDraft): string | null {
  if (draft.kind === 'points' && isDefaultPointsDraft(draft)) return DEFAULT_POINTS_WHAT_IF_PATH
  if (draft.kind === 'remove' && isDefaultRemoveDraft(draft)) return DEFAULT_REMOVE_WHAT_IF_PATH
  return null
}

export async function loadHostedWhatIf(draft: WhatIfDraft): Promise<SeasonLeaderboard> {
  const path = hostedWhatIfPath(draft)
  if (!path) throw new Error('No hosted What If payload for this scenario')
  const res = await fetch(path)
  if (!res.ok) throw new Error(`Failed to load ${path}`)
  return res.json() as Promise<SeasonLeaderboard>
}

/**
 * Fallback points-era labels (generated from pipeline/points_rules.py).
 * Prefer `/api/points_system_changes.json` when present.
 */
export const POINTS_SYSTEM_CHANGES: PointsSystemChangesResponse =
  pointsSystemChangesFallback as PointsSystemChangesResponse

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
