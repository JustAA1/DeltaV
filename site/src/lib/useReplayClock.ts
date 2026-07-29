import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReplaySpeed } from './replayUtils'

export interface ReplayClock {
  t: number
  playing: boolean
  speed: ReplaySpeed
  duration: number
  play: () => void
  pause: () => void
  toggle: () => void
  setSpeed: (speed: ReplaySpeed) => void
  seek: (t: number) => void
  reset: () => void
}

export function useReplayClock(duration: number, resetKey?: string | number): ReplayClock {
  const [t, setT] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeedState] = useState<ReplaySpeed>(5)

  const tRef = useRef(0)
  const playingRef = useRef(false)
  const speedRef = useRef<ReplaySpeed>(5)
  const durationRef = useRef(duration)
  const rafRef = useRef<number | null>(null)
  const lastTsRef = useRef<number | null>(null)

  useEffect(() => {
    durationRef.current = duration
    if (tRef.current > duration) {
      tRef.current = duration
      setT(duration)
      setPlaying(false)
      playingRef.current = false
    }
  }, [duration])

  const stopRaf = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    lastTsRef.current = null
  }, [])

  const tick = useCallback(
    (ts: number) => {
      if (!playingRef.current) return
      if (lastTsRef.current == null) lastTsRef.current = ts
      const dt = (ts - lastTsRef.current) / 1000
      lastTsRef.current = ts
      let next = tRef.current + dt * speedRef.current
      if (next >= durationRef.current) {
        next = durationRef.current
        tRef.current = next
        setT(next)
        playingRef.current = false
        setPlaying(false)
        stopRaf()
        return
      }
      tRef.current = next
      setT(next)
      rafRef.current = requestAnimationFrame(tick)
    },
    [stopRaf],
  )

  const play = useCallback(() => {
    if (durationRef.current <= 0) return
    if (tRef.current >= durationRef.current) {
      tRef.current = 0
      setT(0)
    }
    playingRef.current = true
    setPlaying(true)
    stopRaf()
    rafRef.current = requestAnimationFrame(tick)
  }, [stopRaf, tick])

  const pause = useCallback(() => {
    playingRef.current = false
    setPlaying(false)
    stopRaf()
  }, [stopRaf])

  const toggle = useCallback(() => {
    if (playingRef.current) pause()
    else play()
  }, [pause, play])

  const setSpeed = useCallback((s: ReplaySpeed) => {
    speedRef.current = s
    setSpeedState(s)
  }, [])

  const seek = useCallback((next: number) => {
    const clamped = Math.max(0, Math.min(durationRef.current, next))
    tRef.current = clamped
    setT(clamped)
    if (playingRef.current) {
      lastTsRef.current = null
    }
  }, [])

  const reset = useCallback(() => {
    pause()
    tRef.current = 0
    setT(0)
  }, [pause])

  // Reset clock when race identity changes
  useEffect(() => {
    pause()
    tRef.current = 0
    setT(0)
  }, [resetKey, duration, pause])

  useEffect(() => () => stopRaf(), [stopRaf])

  return { t, playing, speed, duration, play, pause, toggle, setSpeed, seek, reset }
}
