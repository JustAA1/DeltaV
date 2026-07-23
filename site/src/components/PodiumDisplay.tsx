import { DriverAvatar } from './DriverAvatar'

export interface PodiumDriver {
  position: number
  code: string
  name: string
  team: string
  color: string
  image?: string | null
}

interface PodiumDisplayProps {
  podium: PodiumDriver[]
  /** Optional badge under each driver (e.g. occurrence count). */
  badge?: string | ((driver: PodiumDriver) => string | null)
  size?: 'default' | 'large' | 'compact'
  className?: string
}

function lastName(full: string): string {
  const parts = full.trim().split(/\s+/)
  return parts[parts.length - 1] || full
}

function displayCode(code: string, name: string): string {
  const raw = code.toUpperCase()
  return raw.length === 3 ? raw : lastName(name).slice(0, 3).toUpperCase()
}

function avatarSizeForPosition(position: number, size: 'default' | 'large' | 'compact'): number {
  if (size === 'compact') {
    if (position === 1) return 40
    if (position === 2) return 34
    return 28
  }
  if (size === 'large') {
    if (position === 1) return 88
    if (position === 2) return 72
    return 60
  }
  if (position === 1) return 72
  if (position === 2) return 60
  return 52
}

export function PodiumDisplay({
  podium,
  badge,
  size = 'default',
  className,
}: PodiumDisplayProps) {
  const ordered = [2, 1, 3]
    .map((pos) => podium.find((d) => d.position === pos))
    .filter((d): d is PodiumDriver => d != null)

  return (
    <div className={className ? `podium ${className}` : 'podium'}>
      {ordered.map((driver) => {
        const badgeText =
          typeof badge === 'function' ? badge(driver) : badge ?? null
        return (
          <article
            key={`${driver.code}-${driver.position}`}
            className={`podium-card podium-${driver.position}${size === 'large' ? ' podium-card-lg' : ''}${size === 'compact' ? ' podium-card-compact' : ''}`}
            style={{ borderTopColor: driver.color }}
          >
            <div className="podium-pos">P{driver.position}</div>
            <DriverAvatar
              code={displayCode(driver.code, driver.name)}
              name={driver.name}
              color={driver.color}
              image={driver.image}
              size={avatarSizeForPosition(driver.position, size)}
            />
            <h3>{size === 'compact' ? lastName(driver.name) : driver.name}</h3>
            {size !== 'compact' && (
              <p className="team-label" style={{ color: driver.color }}>
                {driver.team}
              </p>
            )}
            {badgeText && <span className="podium-badge">{badgeText}</span>}
          </article>
        )
      })}
    </div>
  )
}
