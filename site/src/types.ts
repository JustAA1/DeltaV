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
  /** Prior occurrence of this trio (null on first-ever / podiumigami). */
  last_occurred_year?: number | null
  last_occurred_event?: string | null
}

export interface PodiumigamiCombo {
  key: string
  count: number
  is_podiumigami: boolean
  podium: PodiumDriver[]
  drivers: PodiumigamiTrioDriver[]
  first_year?: number | null
  last_year?: number | null
  last_event_name?: string | null
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

/* ── Race replays ── */

export interface ReplayCorner {
  n: number
  label: string
  x: number
  y: number
}

export interface ReplayTrack {
  rotation: number
  q_max: number
  /** Quantized box size — preserves the circuit's true aspect ratio. */
  q_w: number
  q_h: number
  centerline: [number, number][]
  outline: [number, number][]
  corners: ReplayCorner[]
  /** Open pit-lane path. Absent where the position feed is too coarse to derive one. */
  pitlane?: [number, number][]
}

export interface ReplayDriver {
  code: string
  name: string
  team: string
  number: number
  color: string
  status: string
  classified: string
  finished: boolean
  started: boolean
  finish_position: number | null
  grid: number | null
  /** Race-relative second the car was last racing (retirement / chequered flag). */
  end_t_s: number
}

export interface ReplayDriverPos {
  x: number[]
  y: number[]
}

export interface ReplayStint {
  code: string
  stint: number
  compound: string
  start_lap: number
  end_lap: number
  t_start_s: number
  t_end_s: number
}

export interface ReplayPit {
  code: string
  t_s: number
  lap: number
}

export interface ReplayFlag {
  type: 'SC' | 'VSC' | 'RED' | string
  t_start_s: number
  t_end_s: number
}

export interface ReplayLapMarker {
  lap: number
  t_s: number
}

export interface ReplayFeedEntry {
  t_s: number
  category: string
  flag: string
  scope: string
  lap: number | null
  message: string
}

export interface RaceReplay {
  season: number
  round: number
  /** R = Grand Prix, S = Sprint. Absent on older race files → treat as R. */
  session?: 'R' | 'S'
  event_name: string
  circuit: string
  country: string
  event_date: string
  hz: number
  duration_s: number
  total_laps: number
  track: ReplayTrack
  drivers: ReplayDriver[]
  pos: Record<string, ReplayDriverPos>
  /** Race progress in hundredths of a lap per frame; -1 = not running. */
  prog: Record<string, number[]>
  /** Race-relative [entry, exit] spans each car spent in the pit lane. */
  pit_windows: Record<string, [number, number][]>
  /** Present when the position feed was too unreliable to rank cars by. */
  order_source?: 'timing'
  stints: ReplayStint[]
  pits: ReplayPit[]
  flags: ReplayFlag[]
  lap_markers: ReplayLapMarker[]
  feed: ReplayFeedEntry[]
}

export interface ReplaysIndexRace {
  season: number
  round: number
  /** R = Grand Prix, S = Sprint. */
  session: 'R' | 'S'
  event_name: string
  circuit: string
  country: string
  event_date: string
  duration_s: number
  total_laps: number
  driver_count: number
  winner?: ReplayWinner
  q_w: number
  q_h: number
  outline: [number, number][]
  file: string
}

export interface ReplayWinner {
  code: string
  name: string
  team: string
  color: string
}

export interface ReplaysIndex {
  season: number
  races: ReplaysIndexRace[]
}
