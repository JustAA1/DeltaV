/** Shared helpers for the Replays UI. */

export const COMPOUND_COLORS: Record<string, string> = {
  SOFT: '#FF3333',
  MEDIUM: '#F0C300',
  HARD: '#E8E8E8',
  INTERMEDIATE: '#39B54A',
  INTER: '#39B54A',
  WET: '#00A0E2',
  UNKNOWN: '#6b7280',
}

export const FLAG_COLORS: Record<string, string> = {
  SC: 'rgba(255, 184, 0, 0.35)',
  VSC: 'rgba(255, 214, 10, 0.28)',
  RED: 'rgba(220, 38, 38, 0.4)',
}

export const FLAG_LABEL_COLORS: Record<string, string> = {
  SC: '#FFB800',
  VSC: '#F5D76E',
  RED: '#EF4444',
}

export const REPLAY_SPEEDS = [1, 2, 5, 10, 20] as const
export type ReplaySpeed = (typeof REPLAY_SPEEDS)[number]

export function compoundColor(compound: string): string {
  return COMPOUND_COLORS[compound.toUpperCase()] ?? COMPOUND_COLORS.UNKNOWN
}

export function formatRaceTime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
  }
  return `${m}:${String(sec).padStart(2, '0')}`
}

/** Coarse duration for race cards, e.g. "1h 24m". */
export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds / 60))
  const h = Math.floor(total / 60)
  const m = total % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

export function formatEventDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(`${iso}T12:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

/** R = Grand Prix, S = Sprint. Older index rows omit the field. */
export function sessionOf(race: { session?: string | null }): 'R' | 'S' {
  return race.session === 'S' ? 'S' : 'R'
}

/** Most recent first; race before sprint on the same weekend. */
export function sortReplays<T extends { round: number; session?: string | null }>(races: T[]): T[] {
  return [...races].sort((a, b) => {
    if (a.round !== b.round) return b.round - a.round
    return (sessionOf(a) === 'R' ? 0 : 1) - (sessionOf(b) === 'R' ? 0 : 1)
  })
}

export function replayPath(race: {
  season: number
  round: number
  session?: string | null
}): string {
  const base = `/replays/${race.season}/${race.round}`
  return sessionOf(race) === 'S' ? `${base}/sprint` : base
}

/** Build an SVG path for a quantized outline, flipping Y for screen space. */
export function outlinePath(points: [number, number][], qh: number): string {
  if (points.length < 2) return ''
  return points
    .map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x} ${qh - y}`)
    .join(' ')
    .concat(' Z')
}

/** Scale the pipeline applies to `prog`; must match PROG_SCALE in replays.py. */
export const PROG_SCALE = 1000

/** Interpolate race progress (thousandths of a lap) into fractional laps. */
export function sampleProgress(series: number[], t: number, hz: number): number | null {
  if (!series.length) return null
  const frame = t * hz
  const i0 = Math.floor(frame)
  if (i0 < 0 || i0 >= series.length) return null
  const p0 = series[i0]
  if (p0 < 0) return null
  const i1 = Math.min(i0 + 1, series.length - 1)
  const p1 = series[i1]
  if (p1 < 0) return p0 / PROG_SCALE
  return (p0 + (p1 - p0) * (frame - i0)) / PROG_SCALE
}

/**
 * Time at which a car first reached a given race progress.
 *
 * Inverting the car-ahead's own progress curve gives a real F1-style interval —
 * "how long ago was the car ahead where I am now" — instead of multiplying a
 * progress delta by one average lap time, which is wrong whenever the two cars
 * are lapping at different paces.
 */
export function timeAtProgress(series: number[], progress: number, hz: number): number | null {
  const target = progress * PROG_SCALE
  let lo = 0
  let hi = series.length - 1
  // prog is monotonic where it is defined, so binary search holds
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (series[mid] < 0 || series[mid] < target) lo = mid + 1
    else hi = mid
  }
  if (series[lo] < 0 || series[lo] < target) return null
  if (lo === 0) return 0
  const prev = series[lo - 1]
  if (prev < 0) return lo / hz
  const span = series[lo] - prev
  const frac = span > 0 ? (target - prev) / span : 0
  return (lo - 1 + frac) / hz
}

/** Whether a car is in the pit lane at time `t`. */
export function isInPit(windows: [number, number][] | undefined, t: number): boolean {
  if (!windows) return false
  return windows.some(([a, b]) => t >= a && t <= b)
}

/** Accent color for a race control message. */
export function feedAccent(entry: { flag: string; category: string; message: string }): string {
  const flag = entry.flag.toUpperCase()
  if (flag === 'RED') return '#EF4444'
  if (flag === 'DOUBLE YELLOW' || flag === 'YELLOW') return '#FFB800'
  if (flag === 'GREEN' || flag === 'CLEAR') return '#39B54A'
  if (flag === 'CHEQUERED') return '#E8E8E8'
  if (entry.category === 'SafetyCar') return '#FFB800'
  if (/DELETED|PENALTY|INVESTIGAT|STEWARD/i.test(entry.message)) return '#F97316'
  return '#6b7280'
}

/** Interpolate car position between 1 Hz samples for smoother playback. */
export function samplePos(
  xs: number[],
  ys: number[],
  t: number,
  hz: number,
): { x: number; y: number } | null {
  if (!xs.length || !ys.length) return null
  const frame = t * hz
  const i0 = Math.floor(frame)
  if (i0 < 0 || i0 >= xs.length) return null
  const x0 = xs[i0]
  const y0 = ys[i0]
  if (x0 < 0 || y0 < 0) return null
  const i1 = Math.min(i0 + 1, xs.length - 1)
  const x1 = xs[i1]
  const y1 = ys[i1]
  if (x1 < 0 || y1 < 0) return { x: x0, y: y0 }
  const frac = frame - i0
  return { x: x0 + (x1 - x0) * frac, y: y0 + (y1 - y0) * frac }
}
