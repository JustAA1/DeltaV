import { useEffect, useMemo, useRef } from 'react'
import type { RaceReplay } from '../../types'
import { feedAccent, formatRaceTime } from '../../lib/replayUtils'

const MAX_ENTRIES = 60

export function RaceFeed({ replay, t }: { replay: RaceReplay; t: number }) {
  const listRef = useRef<HTMLOListElement>(null)

  const entries = useMemo(() => {
    const shown = replay.feed.filter((f) => f.t_s <= t)
    return shown.slice(-MAX_ENTRIES).reverse()
  }, [replay.feed, t])

  // Keep the newest message in view as the clock advances
  useEffect(() => {
    listRef.current?.scrollTo({ top: 0 })
  }, [entries.length])

  return (
    <div className="replay-panel">
      <div className="replay-panel-head">
        <h2>Race feed</h2>
        <span className="replay-panel-sub">Race control</span>
      </div>
      {entries.length === 0 ? (
        <p className="replay-feed-empty">Waiting for lights out…</p>
      ) : (
        <ol className="replay-feed" ref={listRef}>
          {entries.map((f, i) => (
            <li key={`${f.t_s}-${i}`} className="replay-feed-row">
              <span className="replay-feed-time">
                {f.lap != null && f.lap > 0 ? `L${f.lap}` : formatRaceTime(f.t_s)}
              </span>
              <span className="replay-feed-dot" style={{ background: feedAccent(f) }} />
              <span className="replay-feed-msg">{f.message}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
