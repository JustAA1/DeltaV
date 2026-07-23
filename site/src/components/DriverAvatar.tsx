import { useState } from 'react'
import type { DriverRecord } from '../types'

interface DriverAvatarProps {
  driver?: Pick<DriverRecord, 'code' | 'name' | 'color' | 'image'>
  code: string
  name: string
  color: string
  image?: string | null
  size?: number
}

export function DriverAvatar({ driver, code, name, color, image, size = 48 }: DriverAvatarProps) {
  const resolvedCode = driver?.code ?? code
  const resolvedName = driver?.name ?? name
  const resolvedColor = driver?.color ?? color
  const resolvedImage = driver?.image ?? image
  const [failed, setFailed] = useState(false)

  const initials = resolvedCode.slice(0, 3)
  const showImage = resolvedImage && !failed

  return (
    <div
      className="driver-avatar"
      style={{ width: size, height: size, borderColor: resolvedColor }}
      title={resolvedName}
    >
      {showImage ? (
        <img
          src={resolvedImage}
          alt={resolvedName}
          onError={() => setFailed(true)}
          loading="lazy"
        />
      ) : (
        <span className="driver-avatar-fallback" style={{ background: `${resolvedColor}33`, color: resolvedColor }}>
          {initials}
        </span>
      )}
    </div>
  )
}
