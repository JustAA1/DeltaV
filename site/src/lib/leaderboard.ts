import type {
  ChartPoint,
  ChartSeries,
  LeaderboardEntity,
  LeaderboardStage,
  SeasonLeaderboard,
} from '../types'
import { roundPoints } from './points'

function stripGrandPrix(name: string): string {
  const base = name.replace('Grand Prix', '').replace(/\s+/g, ' ').trim()
  if (base === 'United States West') return 'US West'
  if (base === 'United States') return 'USA'
  return base
}

/** Stages to plot: prefer API-provided (includes sprints), else derive from rounds. */
export function getStages(lb: SeasonLeaderboard): LeaderboardStage[] {
  if (lb.stages?.length) return lb.stages
  return lb.rounds.map((round) => ({
    id: String(round),
    round,
    kind: 'race' as const,
    label: stripGrandPrix(lb.race_names[String(round)] ?? `R${round}`),
  }))
}

/** Race rounds whose GP result counts for FIA Art. 7.2 at (and including) this stage. */
export function raceRoundsIncluded(stages: LeaderboardStage[], stageId: string): Set<number> {
  const included = new Set<number>()
  for (const st of stages) {
    if (st.kind === 'race') included.add(st.round)
    if (st.id === stageId) break
  }
  return included
}

/** Histogram of finishing places (index 0 = P1 count) using only included race rounds. */
export function placeCounts(
  positions: Record<string, number | number[]> | undefined,
  includedRounds: Set<number>,
): number[] {
  const counts: number[] = []
  if (!positions) return counts
  for (const [rndStr, val] of Object.entries(positions)) {
    const rnd = Number(rndStr)
    if (!includedRounds.has(rnd)) continue
    const vals = Array.isArray(val) ? val : [val]
    for (const p of vals) {
      const idx = Number(p) - 1
      if (idx < 0 || !Number.isFinite(idx)) continue
      while (counts.length <= idx) counts.push(0)
      counts[idx] += 1
    }
  }
  return counts
}

/**
 * FIA Art. 7.2 dead-heat: more points wins; else most race wins, then 2nds, 3rds, …
 * Returns < 0 if `a` ranks ahead of `b`.
 */
export function compareF1Standings(
  a: { points: number; racePositions?: Record<string, number | number[]>; label: string },
  b: { points: number; racePositions?: Record<string, number | number[]>; label: string },
  includedRounds: Set<number>,
): number {
  if (a.points !== b.points) return b.points - a.points
  const ac = placeCounts(a.racePositions, includedRounds)
  const bc = placeCounts(b.racePositions, includedRounds)
  const max = Math.max(ac.length, bc.length)
  for (let i = 0; i < max; i++) {
    const av = ac[i] ?? 0
    const bv = bc[i] ?? 0
    if (av !== bv) return bv - av
  }
  return a.label.localeCompare(b.label)
}

function buildSeries(
  entities: LeaderboardEntity[],
  stages: LeaderboardStage[],
  secondDriverIds: Set<string>,
): ChartSeries[] {
  return entities.map((entity) => {
    const id = entity.team ? `${entity.team}-${entity.name}` : entity.name
    const data: ChartPoint[] = stages.map((stage) => ({
      stageId: stage.id,
      label: stage.label,
      round: stage.round,
      points: roundPoints(entity.points_by_round[stage.id] ?? 0),
    }))

    return {
      id,
      label: entity.name,
      color: entity.color,
      isSecondDriver: secondDriverIds.has(id),
      code: entity.code,
      team: entity.team,
      image: entity.image,
      racePositions: entity.race_positions,
      excludedStages: new Set(entity.excluded_stages ?? []),
      disqualified: Boolean(entity.disqualified),
      data,
    }
  })
}

/** Mark lower-scoring teammate per team as dashed line (F1 tiebreak aware). */
export function markSecondDrivers(
  drivers: LeaderboardEntity[],
  stages: LeaderboardStage[],
  lastStageId: string,
): Set<string> {
  const included = raceRoundsIncluded(stages, lastStageId)
  const byTeam = new Map<string, LeaderboardEntity[]>()
  for (const d of drivers) {
    const team = d.team ?? d.name
    if (!byTeam.has(team)) byTeam.set(team, [])
    byTeam.get(team)!.push(d)
  }

  const second = new Set<string>()
  for (const [, teammates] of byTeam) {
    if (teammates.length < 2) continue
    const scored = [...teammates].sort((a, b) =>
      compareF1Standings(
        {
          points: a.points_by_round[lastStageId] ?? 0,
          racePositions: a.race_positions,
          label: a.name,
        },
        {
          points: b.points_by_round[lastStageId] ?? 0,
          racePositions: b.race_positions,
          label: b.name,
        },
        included,
      ),
    )
    for (let i = 1; i < scored.length; i++) {
      const t = scored[i]
      second.add(`${t.team}-${t.name}`)
    }
  }
  return second
}

export function toLeaderboardChartData(
  lb: SeasonLeaderboard,
  mode: 'drivers' | 'constructors',
): { stages: LeaderboardStage[]; series: ChartSeries[] } {
  const stages = getStages(lb)
  const lastStageId = stages[stages.length - 1]?.id ?? ''

  if (mode === 'constructors') {
    return {
      stages,
      series: buildSeries(lb.constructors, stages, new Set()),
    }
  }

  const second = markSecondDrivers(lb.drivers, stages, lastStageId)
  return {
    stages,
    series: buildSeries(lb.drivers, stages, second),
  }
}

export function lastName(full: string): string {
  const parts = full.trim().split(/\s+/)
  return parts[parts.length - 1] || full
}

/** Rank map at a given stage (1-based), using FIA Art. 7.2 tiebreakers.
 *  Championship exclusions (DQ) are omitted from numbered places.
 */
export function ranksAtStage(
  series: ChartSeries[],
  stages: LeaderboardStage[],
  stageId: string,
): Map<string, number> {
  const included = raceRoundsIncluded(stages, stageId)
  const scored = series
    .filter((s) => !s.disqualified)
    .map((s) => ({
      id: s.id,
      points: s.data.find((d) => d.stageId === stageId)?.points ?? 0,
      racePositions: s.racePositions,
      label: s.label,
    }))
    .sort((a, b) => compareF1Standings(a, b, included))

  const ranks = new Map<string, number>()
  scored.forEach((row, i) => ranks.set(row.id, i + 1))
  return ranks
}

/** Sort series for standings at a stage (F1 tiebreak aware). */
export function sortSeriesAtStage(
  series: ChartSeries[],
  stages: LeaderboardStage[],
  stageId: string,
): ChartSeries[] {
  const included = raceRoundsIncluded(stages, stageId)
  return [...series].sort((a, b) =>
    compareF1Standings(
      {
        points: a.data.find((d) => d.stageId === stageId)?.points ?? 0,
        racePositions: a.racePositions,
        label: a.label,
      },
      {
        points: b.data.find((d) => d.stageId === stageId)?.points ?? 0,
        racePositions: b.racePositions,
        label: b.label,
      },
      included,
    ),
  )
}
