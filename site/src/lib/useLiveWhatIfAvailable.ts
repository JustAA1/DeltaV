import { useEffect, useState } from 'react'
import { IS_PRODUCTION_BUILD, whatIfForceFlag } from '../config'

export type LiveWhatIfStatus = 'checking' | 'available' | 'unavailable'

/**
 * Whether POST /api/what-if* can succeed right now.
 * Production builds are always unavailable unless VITE_WHAT_IF_API overrides.
 */
export function useLiveWhatIfAvailable(): {
  status: LiveWhatIfStatus
  available: boolean
} {
  const forced = whatIfForceFlag()
  const [status, setStatus] = useState<LiveWhatIfStatus>(() => {
    if (forced === true) return 'available'
    if (forced === false || IS_PRODUCTION_BUILD) return 'unavailable'
    return 'checking'
  })

  useEffect(() => {
    if (forced === true) {
      setStatus('available')
      return
    }
    if (forced === false || IS_PRODUCTION_BUILD) {
      setStatus('unavailable')
      return
    }

    let cancelled = false
    const ctrl = new AbortController()
    const timer = window.setTimeout(() => ctrl.abort(), 2500)

    fetch('/api/health', { signal: ctrl.signal })
      .then(async (res) => {
        if (cancelled) return
        if (!res.ok) {
          setStatus('unavailable')
          return
        }
        const body = (await res.json().catch(() => null)) as { status?: string } | null
        setStatus(body?.status === 'ok' ? 'available' : 'unavailable')
      })
      .catch(() => {
        if (!cancelled) setStatus('unavailable')
      })
      .finally(() => window.clearTimeout(timer))

    return () => {
      cancelled = true
      ctrl.abort()
      window.clearTimeout(timer)
    }
  }, [forced])

  return { status, available: status === 'available' }
}
