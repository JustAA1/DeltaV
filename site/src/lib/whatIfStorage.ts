export interface WhatIfRemoval {
  name: string
  id?: string
}

export type RemoveWhatIfDraft = {
  kind: 'remove'
  season: number
  removeType: 'driver' | 'team'
  removes: WhatIfRemoval[]
  championship?: 'drivers' | 'constructors'
}

export type PointsWhatIfDraft = {
  kind: 'points'
  season: number
  pointsFrom: number
  championship?: 'drivers' | 'constructors'
}

export type WhatIfDraft = RemoveWhatIfDraft | PointsWhatIfDraft

const REMOVE_DRAFT_KEY = 'deltav-what-if-remove-draft'
const POINTS_DRAFT_KEY = 'deltav-what-if-points-draft'
const ACTIVE_DRAFT_KEY = 'deltav-what-if-draft'
const LEGACY_REMOVE_DRAFT_KEY = 'apex-what-if-remove-draft'
const LEGACY_POINTS_DRAFT_KEY = 'apex-what-if-points-draft'
const LEGACY_ACTIVE_DRAFT_KEY = 'apex-what-if-draft'
const REMOVE_SEP = '|'

function migrateLegacyKey(legacy: string, next: string) {
  try {
    const existing = sessionStorage.getItem(next)
    if (existing) {
      sessionStorage.removeItem(legacy)
      return
    }
    const old = sessionStorage.getItem(legacy)
    if (old) {
      sessionStorage.setItem(next, old)
      sessionStorage.removeItem(legacy)
    }
  } catch {
    /* ignore */
  }
}

migrateLegacyKey(LEGACY_REMOVE_DRAFT_KEY, REMOVE_DRAFT_KEY)
migrateLegacyKey(LEGACY_POINTS_DRAFT_KEY, POINTS_DRAFT_KEY)
migrateLegacyKey(LEGACY_ACTIVE_DRAFT_KEY, ACTIVE_DRAFT_KEY)

/** Pipe-separated, URI-encoded names/ids for URL params. */
export function encodeRemoveList(values: string[]): string {
  return values.map((v) => encodeURIComponent(v)).join(REMOVE_SEP)
}

export function decodeRemoveList(param: string): string[] {
  if (!param) return []
  return param
    .split(REMOVE_SEP)
    .map((s) => {
      try {
        return decodeURIComponent(s)
      } catch {
        return s
      }
    })
    .filter(Boolean)
}

export function formatWhatIfNames(names: string[]): string {
  const list = names.filter(Boolean)
  if (list.length === 0) return ''
  if (list.length === 1) return list[0]
  if (list.length === 2) return `${list[0]} and ${list[1]}`
  return `${list.slice(0, -1).join(', ')}, and ${list[list.length - 1]}`
}

function migrateStoredDraft(parsed: Record<string, unknown>): WhatIfDraft | null {
  if (parsed.kind === 'points' && parsed.season && parsed.pointsFrom) {
    return {
      kind: 'points',
      season: Number(parsed.season),
      pointsFrom: Number(parsed.pointsFrom),
      championship: parsed.championship as PointsWhatIfDraft['championship'],
    }
  }

  if (Array.isArray(parsed.removes) && parsed.removes.length > 0) {
    return {
      kind: 'remove',
      season: Number(parsed.season),
      removeType: (parsed.removeType as RemoveWhatIfDraft['removeType']) || 'driver',
      removes: parsed.removes as WhatIfRemoval[],
      championship: parsed.championship as RemoveWhatIfDraft['championship'],
    }
  }

  const removeName = typeof parsed.removeName === 'string' ? parsed.removeName : ''
  if (!removeName || !parsed.season) return null
  return {
    kind: 'remove',
    season: Number(parsed.season),
    removeType: (parsed.removeType as RemoveWhatIfDraft['removeType']) || 'driver',
    removes: [
      {
        name: removeName,
        id: typeof parsed.removeId === 'string' ? parsed.removeId : undefined,
      },
    ],
    championship: parsed.championship as RemoveWhatIfDraft['championship'],
  }
}

export function loadRemoveWhatIfDraft(): RemoveWhatIfDraft | null {
  try {
    const raw = sessionStorage.getItem(REMOVE_DRAFT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Record<string, unknown>
    const draft = migrateStoredDraft({ ...parsed, kind: 'remove' })
    return draft && isRemoveWhatIfDraft(draft) ? draft : null
  } catch {
    return null
  }
}

export function loadPointsWhatIfDraft(): PointsWhatIfDraft | null {
  try {
    const raw = sessionStorage.getItem(POINTS_DRAFT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Record<string, unknown>
    if (parsed.kind === 'points' && parsed.season && parsed.pointsFrom) {
      return {
        kind: 'points',
        season: Number(parsed.season),
        pointsFrom: Number(parsed.pointsFrom),
        championship: parsed.championship as PointsWhatIfDraft['championship'],
      }
    }
    return null
  } catch {
    return null
  }
}

export function saveRemoveWhatIfDraft(draft: RemoveWhatIfDraft): void {
  try {
    sessionStorage.setItem(REMOVE_DRAFT_KEY, JSON.stringify(draft))
  } catch {
    // ignore
  }
}

export function savePointsWhatIfDraft(draft: PointsWhatIfDraft): void {
  try {
    sessionStorage.setItem(POINTS_DRAFT_KEY, JSON.stringify(draft))
  } catch {
    // ignore
  }
}

export function loadWhatIfDraft(): WhatIfDraft | null {
  try {
    const raw = sessionStorage.getItem(ACTIVE_DRAFT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Record<string, unknown>
    const draft = migrateStoredDraft(parsed)
    if (!draft) return null
    if (isRemoveWhatIfDraft(draft) && !draft.removes.length) return null
    return draft
  } catch {
    return null
  }
}

export function saveWhatIfDraft(draft: WhatIfDraft): void {
  saveActiveWhatIfDraft(draft)
  if (isRemoveWhatIfDraft(draft)) {
    saveRemoveWhatIfDraft(draft)
  } else if (isPointsWhatIfDraft(draft)) {
    savePointsWhatIfDraft(draft)
  }
}

export function saveActiveWhatIfDraft(draft: WhatIfDraft): void {
  try {
    sessionStorage.setItem(ACTIVE_DRAFT_KEY, JSON.stringify(draft))
  } catch {
    // ignore
  }
}

export function clearWhatIfDraft(): void {
  try {
    sessionStorage.removeItem(ACTIVE_DRAFT_KEY)
  } catch {
    // ignore
  }
}

export function whatIfSearchParams(draft: WhatIfDraft): URLSearchParams {
  const params = new URLSearchParams()
  params.set('whatif', '1')
  params.set('season', String(draft.season))
  if (draft.championship) params.set('championship', draft.championship)

  if (draft.kind === 'points') {
    params.set('scenario', 'points')
    params.set('pointsFrom', String(draft.pointsFrom))
    return params
  }

  params.set('removeType', draft.removeType)
  params.set('removeNames', encodeRemoveList(draft.removes.map((r) => r.name)))
  if (draft.removeType === 'driver') {
    const ids = draft.removes.map((r) => r.id).filter(Boolean) as string[]
    if (ids.length === draft.removes.length) {
      params.set('removeIds', encodeRemoveList(ids))
    }
  }
  return params
}

export function parseWhatIfFromSearchParams(params: URLSearchParams): WhatIfDraft | null {
  if (params.get('whatif') !== '1') return null
  const season = Number(params.get('season') || 2026)
  const championship = (params.get('championship') || 'drivers') as 'drivers' | 'constructors'

  if (params.get('scenario') === 'points') {
    const pointsFrom = Number(params.get('pointsFrom') || season)
    return { kind: 'points', season, pointsFrom, championship }
  }

  const names = decodeRemoveList(params.get('removeNames') || params.get('removeName') || '')
  if (!names.length) return null
  const removeType = (params.get('removeType') || 'driver') as 'driver' | 'team'
  const ids = decodeRemoveList(params.get('removeIds') || params.get('removeId') || '')
  const removes: WhatIfRemoval[] = names.map((name, i) => ({
    name,
    id: removeType === 'driver' ? ids[i] : undefined,
  }))
  return { kind: 'remove', season, removeType, removes, championship }
}

export function leaderboardWhatIfHref(draft: WhatIfDraft | null = loadWhatIfDraft()): string {
  if (!draft) return '/leaderboard'
  if (isRemoveWhatIfDraft(draft) && !draft.removes.length) return '/leaderboard'
  return `/leaderboard?${whatIfSearchParams(draft).toString()}`
}

/** Persist the scenario currently shown on the leaderboard (not What If form drafts). */
export function syncActiveWhatIfDraft(draft: WhatIfDraft): void {
  saveActiveWhatIfDraft(draft)
}

export function whatIfQueryKey(draft: WhatIfDraft): string {
  if (draft.kind === 'points') {
    return `points:${draft.season}:${draft.pointsFrom}`
  }
  const parts = draft.removes.map((r) =>
    draft.removeType === 'driver' ? r.id ?? r.name : r.name,
  )
  return `remove:${draft.removeType}:${parts.sort().join(',')}`
}

export function isRemoveWhatIfDraft(draft: WhatIfDraft): draft is RemoveWhatIfDraft {
  return draft.kind === 'remove'
}

export function isPointsWhatIfDraft(draft: WhatIfDraft): draft is PointsWhatIfDraft {
  return draft.kind === 'points'
}

function normWhatIfText(text: string): string {
  return text.toLowerCase().trim().replace(/\s+/g, ' ')
}

export interface WhatIfSeasonOptions {
  drivers: { id: string; name: string }[]
  teams: { name: string }[]
}

/** Map a removal target onto a different season, if that entity raced there. */
export function resolveRemoveForSeason(
  remove: WhatIfRemoval,
  removeType: 'driver' | 'team',
  options: WhatIfSeasonOptions,
): WhatIfRemoval | null {
  if (removeType === 'driver') {
    if (remove.id) {
      const byId = options.drivers.find((d) => d.id === remove.id)
      if (byId) return { id: byId.id, name: byId.name }
    }
    const target = normWhatIfText(remove.name)
    const byName = options.drivers.find(
      (d) => normWhatIfText(d.name) === target || normWhatIfText(d.id) === target,
    )
    if (byName) return { id: byName.id, name: byName.name }
    return null
  }

  const target = normWhatIfText(remove.name)
  const team = options.teams.find((t) => {
    const name = normWhatIfText(t.name)
    return name === target || name.includes(target) || target.includes(name)
  })
  return team ? { name: team.name } : null
}

/** Keep a what-if scenario when changing season; return null if it no longer applies. */
export function adaptWhatIfDraftToSeason(
  draft: WhatIfDraft,
  season: number,
  options?: WhatIfSeasonOptions,
): WhatIfDraft | null {
  if (draft.kind === 'points') {
    return { ...draft, season }
  }

  if (!options || draft.removes.length === 0) return null

  const removes: WhatIfRemoval[] = []
  for (const remove of draft.removes) {
    const resolved = resolveRemoveForSeason(remove, draft.removeType, options)
    if (!resolved) return null
    removes.push(resolved)
  }

  return { ...draft, season, removes }
}
