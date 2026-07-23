import { DriverAvatar } from './DriverAvatar'
import type { PodiumigamiCombo, PodiumigamiTrioDriver } from '../types'

function lastName(full: string): string {
  const parts = full.trim().split(/\s+/)
  return parts[parts.length - 1] || full
}

function displayCode(code: string, name: string): string {
  const raw = code.toUpperCase()
  return raw.length === 3 ? raw : lastName(name).slice(0, 3).toUpperCase()
}

export function TrioIcons({
  drivers,
  size = 28,
  showNames = true,
}: {
  drivers: PodiumigamiTrioDriver[]
  size?: number
  showNames?: boolean
}) {
  return (
    <div className="trio-icons">
      <div className="trio-icons-avatars">
        {drivers.map((d) => (
          <DriverAvatar
            key={d.code}
            code={displayCode(d.code, d.name)}
            name={d.name}
            color={d.color}
            image={d.image}
            size={size}
          />
        ))}
      </div>
      {showNames && (
        <p className="trio-icons-names">
          {drivers.map((d) => lastName(d.name)).join(' · ')}
        </p>
      )}
    </div>
  )
}

/** Large podium where P1/P2/P3 slots are the 1st/2nd/3rd most common trios. */
export function TopTriosPodium({
  trios,
  onOpenAll,
}: {
  trios: PodiumigamiCombo[]
  onOpenAll?: () => void
}) {
  const slots = [
    { rank: 2, trio: trios[1] },
    { rank: 1, trio: trios[0] },
    { rank: 3, trio: trios[2] },
  ]

  return (
    <button
      type="button"
      className="top-trios-podium-btn"
      onClick={onOpenAll}
      aria-label="View all ranked podiumigamis"
    >
      <div className="podium top-trios-podium">
        {slots.map(({ rank, trio }) => (
          <article
            key={rank}
            className={`podium-card podium-${rank} top-trio-slot${trio ? '' : ' is-empty'}`}
            style={{ borderTopColor: trio?.drivers[0]?.color ?? '#666' }}
          >
            <div className="podium-pos">#{rank}</div>
            {trio ? (
              <>
                <TrioIcons
                  drivers={trio.drivers}
                  size={rank === 1 ? 36 : rank === 2 ? 30 : 26}
                />
                {trio.is_podiumigami ? (
                  <span className="podiumigami-gold-badge">Podiumigami</span>
                ) : (
                  <span className="podium-badge">×{trio.count}</span>
                )}
              </>
            ) : (
              <p className="top-trio-empty">—</p>
            )}
          </article>
        ))}
      </div>
      {onOpenAll && <span className="top-trios-see-all">See all ranked trios</span>}
    </button>
  )
}

export function TrioRankListModal({
  title,
  trios,
  onClose,
}: {
  title: string
  trios: PodiumigamiCombo[]
  onClose: () => void
}) {
  return (
    <div className="trio-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="trio-modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="trio-modal-head">
          <h2>{title}</h2>
          <button type="button" className="trio-modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        <ol className="trio-rank-list">
          {trios.map((trio, i) => (
            <li key={trio.key} className="trio-rank-row">
              <span className="trio-rank-pos">{i + 1}</span>
              <TrioIcons drivers={trio.drivers} size={24} />
              <div className="trio-rank-meta">
                {trio.is_podiumigami ? (
                  <span className="podiumigami-gold-badge">Podiumigami</span>
                ) : (
                  <span className="trio-rank-count">×{trio.count}</span>
                )}
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  )
}
