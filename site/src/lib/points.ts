/** Round championship points to at most one decimal place. */
export function roundPoints(value: number): number {
  return Math.round(value * 10) / 10
}

/** Format points for display (no trailing .0 on whole numbers). */
export function formatPoints(value: number): string {
  const rounded = roundPoints(value)
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
}
