import { Link } from 'react-router-dom'
import { DriverAvatar } from '../DriverAvatar'
import type { DriverRecord, ReplaysIndexRace } from '../../types'
import {
  formatDuration,
  formatEventDate,
  outlinePath,
  replayPath,
  sessionOf,
} from '../../lib/replayUtils'

interface ReplayCardProps {
  race: ReplaysIndexRace
  /** Only used for the winner's photo; name and team come from the index. */
  driver?: DriverRecord
}

export function ReplayCard({ race, driver }: ReplayCardProps) {
  const path = outlinePath(race.outline ?? [], race.q_h || 1000)
  const pad = 30
  const isSprint = sessionOf(race) === 'S'

  return (
    <Link to={replayPath(race)} className={`replay-card${isSprint ? ' is-sprint' : ''}`}>
      <div className="replay-card-body">
        <div className="replay-card-tags">
          <span className="replay-card-round">Round {String(race.round).padStart(2, '0')}</span>
          {isSprint && <span className="replay-card-sprint">Sprint</span>}
        </div>
        <h2 className="replay-card-title">{race.event_name}</h2>
        <p className="replay-card-place">
          {race.circuit}
          {race.event_date && <> · {formatEventDate(race.event_date)}</>}
        </p>
        <dl className="replay-card-stats">
          <div>
            <dt>Laps</dt>
            <dd>{race.total_laps}</dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd>{formatDuration(race.duration_s)}</dd>
          </div>
        </dl>
        {race.winner && (
          <div className="replay-card-winner">
            <DriverAvatar
              code={race.winner.code}
              name={race.winner.name}
              color={race.winner.color || driver?.color || '#888'}
              image={driver?.image ?? null}
              size={34}
            />
            <div className="replay-card-winner-text">
              <span className="replay-card-winner-label">Winner</span>
              <span className="replay-card-winner-name">{race.winner.name}</span>
            </div>
          </div>
        )}
      </div>
      {path && (
        <svg
          className="replay-card-map"
          viewBox={`${-pad} ${-pad} ${(race.q_w || 1000) + pad * 2} ${(race.q_h || 1000) + pad * 2}`}
          aria-hidden
        >
          <path d={path} />
        </svg>
      )}
    </Link>
  )
}
