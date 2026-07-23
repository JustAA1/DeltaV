/** API types matching pipeline/outputs JSON shapes. */

export interface DriverRecord {
  code: string
  name: string
  team: string
  number: number
  color: string
  image: string | null
}

export interface DriversResponse {
  season: number
  drivers: DriverRecord[]
  /** Optional GP name map from assets pipeline. */
  races?: Record<string, string>
}

export interface PredictionEntry {
  driver_code: string
  driver_name: string
  team: string
  predicted_position: number
  confidence: number
}

export interface RacePrediction {
  round: number
  season: number
  event_name: string
  upcoming?: boolean
  metrics?: {
    spearman: number
    podium_hit_rate: number
    mean_position_error: number
    winner_correct: boolean
  }
  predictions: PredictionEntry[]
  actual?: ActualResult[]
}

export interface ActualResult {
  driver_code: string
  name: string
  team: string
  position: number
}

export interface BacktestRace {
  round: number
  season: number
  event_name: string
  metrics: {
    spearman: number
    podium_hit_rate: number
    mean_position_error: number
    winner_correct: boolean
  }
  predictions: PredictionEntry[]
  actual: ActualResult[]
}

export interface BacktestSummary {
  races_evaluated: number
  mean_spearman: number
  mean_podium_hit_rate: number
  mean_position_error: number
  winner_hit_rate: number
  note?: string
}

export interface BacktestResponse {
  season: number
  races: BacktestRace[]
  summary: BacktestSummary
}

export interface LeaderboardEntity {
  name: string
  code?: string
  team?: string
  color: string
  /** Driver headshot or constructor logo path (e.g. /drivers/ver.png). */
  image?: string | null
  /** Cumulative points keyed by stage id (e.g. "10" for a race, "10S" for a sprint). */
  points_by_round: Record<string, number>
  /**
   * Race finishing positions only (FIA Art. 7.2). Drivers: round → position.
   * Constructors: round → list of car positions that round.
   */
  race_positions?: Record<string, number | number[]>
  /** Stage ids whose race points were dropped under a best-N scoring rule. */
  excluded_stages?: string[]
  /** Excluded from the official championship (e.g. 1997 Schumacher, 2007 McLaren). */
  disqualified?: boolean
}

export interface LeaderboardStage {
  id: string
  round: number
  kind: 'race' | 'sprint'
  label: string
}

export interface ScoringRule {
  best_n: number
  applies_to: 'drivers' | 'constructors'
  note: string
}

export interface SeasonStatRow {
  name: string
  id?: string
  team?: string
  color: string
  wins: number
  poles: number
  podiums: number
  dnfs: number
}

export interface SeasonStats {
  drivers: SeasonStatRow[]
  constructors: SeasonStatRow[]
}

export interface SeasonLeaderboard {
  season: number
  rounds: number[]
  stages?: LeaderboardStage[]
  race_names: Record<string, string>
  scoring_rule?: ScoringRule | null
  /** Human-readable championship quirks for this season. */
  notes?: string[]
  drivers: LeaderboardEntity[]
  constructors: LeaderboardEntity[]
  stats?: SeasonStats
  what_if?: WhatIfMeta
}

export interface RemoveWhatIfMeta {
  kind?: 'remove'
  clause: string
  season: number
  removes: {
    type: 'driver' | 'team'
    name: string
    id?: string
    color?: string
  }[]
  remove: {
    type: 'driver' | 'team'
    name: string
    id?: string
    color?: string
  }
  championship: 'drivers' | 'constructors'
  color?: string
}

export interface PointsWhatIfMeta {
  kind: 'points'
  clause: string
  season: number
  points_from: number
  season_color: string
  points_from_color: string
  championship: 'drivers' | 'constructors'
  color?: string
}

export type WhatIfMeta = RemoveWhatIfMeta | PointsWhatIfMeta

export interface ConstructorChampionsResponse {
  champions: Record<string, { name: string; color: string }>
}

export interface PointsSystemChangesResponse {
  changes: Record<string, string>
  seasonChanges: Record<string, string>
  systems: Record<string, string>
}

export interface PointsWhatIfRequest {
  season: number
  points_from: number
  championship?: 'drivers' | 'constructors'
}

export interface WhatIfOptions {
  season: number
  drivers: { id: string; name: string; team: string; color: string }[]
  teams: { name: string; color: string }[]
}

export interface WhatIfRequest {
  season: number
  removes: {
    type: 'driver' | 'team'
    name: string
    id?: string
  }[]
  championship?: 'drivers' | 'constructors'
}

export interface RacesResponse {
  season: number
  races: { round: number; event_name: string; season: number }[]
}

export interface ChartPoint {
  stageId: string
  label: string
  round: number
  points: number
}

export interface ChartSeries {
  id: string
  label: string
  color: string
  isSecondDriver: boolean
  code?: string
  team?: string
  image?: string | null
  racePositions?: Record<string, number | number[]>
  excludedStages?: Set<string>
  disqualified?: boolean
  data: ChartPoint[]
}

export interface PodiumDriver {
  position: number
  code: string
  name: string
  team: string
  color: string
  image?: string | null
}

export interface PodiumigamiTrioDriver {
  code: string
  name: string
  team: string
  color: string
  image?: string | null
  position?: number
}

export interface PodiumigamiRace {
  year: number
  round: number
  event_name: string
  country?: string
  podium: PodiumDriver[]
  key: string
  is_podiumigami: boolean
  occurrence: number
  occurrence_in_year: number
  trio_count: number
}

export interface PodiumigamiCombo {
  key: string
  count: number
  is_podiumigami: boolean
  podium: PodiumDriver[]
  drivers: PodiumigamiTrioDriver[]
  first_year?: number | null
  last_year?: number | null
}

export interface PodiumigamiSeasonStats {
  year: number
  total_races: number
  podiumigamis: number
  top_trios: PodiumigamiCombo[]
  all_trios_ranked: PodiumigamiCombo[]
  races: PodiumigamiRace[]
  hero?: PodiumigamiRace | null
}

export interface PodiumigamiDecadeStats {
  decade: string
  races: number
  podiumigamis: number
  top_trios: PodiumigamiCombo[]
  all_trios_ranked: PodiumigamiCombo[]
}

export interface PodiumigamiAllTime {
  total_races: number
  podiumigamis: number
  one_time_only: number
  top_trios: PodiumigamiCombo[]
  all_trios_ranked: PodiumigamiCombo[]
  decade_breakdown: PodiumigamiDecadeStats[]
  recent_races: PodiumigamiRace[]
}

export interface PodiumigamiResponse {
  from_year: number
  hero: PodiumigamiRace | null
  all_time: PodiumigamiAllTime
  by_season: Record<string, PodiumigamiSeasonStats>
  season?: PodiumigamiSeasonStats
}
