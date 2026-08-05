/** Shared season so nav can disable Formula 1.5 on pre-2021 seasons. */

let currentSeason = 2026
const listeners = new Set<() => void>()

export function getLeaderboardSeason() {
  return currentSeason
}

export function setLeaderboardSeason(season: number) {
  if (season === currentSeason) return
  currentSeason = season
  listeners.forEach((listener) => listener())
}

export function subscribeLeaderboardSeason(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
