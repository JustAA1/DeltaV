import { useEffect, useRef, type ReactNode } from 'react'
import type { RaceReplay } from '../../types'
import { isInPit, samplePos } from '../../lib/replayUtils'

const PITLANE_COLOR = 'rgba(120, 170, 220, 0.55)'
/** Space left between the docked panel and the drawn circuit. Matches the CSS. */
const INSET_GUTTER = 12

interface TrackMapProps {
  replay: RaceReplay
  t: number
  highlighted?: string | null
  selected?: string | null
  onHoverDriver?: (code: string | null) => void
  onSelectDriver?: (code: string) => void
  /** Panel docked inside the map's left edge; the circuit is drawn clear of it. */
  inset?: ReactNode
}

export function TrackMap({
  replay,
  t,
  highlighted,
  selected,
  onHoverDriver,
  onSelectDriver,
  inset,
}: TrackMapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const insetRef = useRef<HTMLDivElement>(null)
  const hitRef = useRef<{ code: string; x: number; y: number; r: number }[]>([])

  useEffect(() => {
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    if (!canvas || !wrap) return

    const draw = () => {
      const qw = replay.track.q_w || replay.track.q_max || 1000
      const qh = replay.track.q_h || replay.track.q_max || 1000

      // Width taken by the docked panel. It reports 0 once the panel drops back
      // into normal flow on narrow screens, so the circuit reclaims the space.
      const insetEl = insetRef.current
      const insetW =
        insetEl && getComputedStyle(insetEl).position === 'absolute'
          ? insetEl.offsetWidth + INSET_GUTTER * 2
          : 0

      const dpr = window.devicePixelRatio || 1
      const cssW = wrap.clientWidth
      // Height follows the circuit's real proportions, within sane bounds. The
      // floor rises with a docked panel so that panel has room to be useful.
      const minH = insetW > 0 ? 460 : 300
      const cssH = Math.max(minH, Math.min(620, Math.round((cssW * qh) / qw)))
      canvas.width = Math.floor(cssW * dpr)
      canvas.height = Math.floor(cssH * dpr)
      canvas.style.width = `${cssW}px`
      canvas.style.height = `${cssH}px`

      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, cssW, cssH)

      // One uniform scale for both axes so the track keeps its true shape
      const pad = 34
      const drawW = cssW - insetW
      const scale = Math.min((drawW - pad * 2) / qw, (cssH - pad * 2) / qh)
      const ox = insetW + (drawW - qw * scale) / 2
      const oy = (cssH - qh * scale) / 2
      const toXY = (x: number, y: number) => ({
        x: ox + x * scale,
        y: oy + (qh - y) * scale,
      })

      const cl = replay.track.centerline
      if (cl.length > 2) {
        const pts = cl.map(([x, y]) => toXY(x, y))
        // Smooth the outline through segment midpoints
        const tracePath = () => {
          ctx.beginPath()
          ctx.moveTo((pts[0].x + pts[pts.length - 1].x) / 2, (pts[0].y + pts[pts.length - 1].y) / 2)
          for (let i = 0; i < pts.length; i++) {
            const cur = pts[i]
            const next = pts[(i + 1) % pts.length]
            ctx.quadraticCurveTo(cur.x, cur.y, (cur.x + next.x) / 2, (cur.y + next.y) / 2)
          }
          ctx.closePath()
        }

        ctx.lineJoin = 'round'
        ctx.lineCap = 'round'

        ctx.strokeStyle = 'rgba(255,255,255,0.10)'
        ctx.lineWidth = 13
        tracePath()
        ctx.stroke()

        ctx.strokeStyle = 'rgba(255,255,255,0.42)'
        ctx.lineWidth = 2.25
        tracePath()
        ctx.stroke()
      }

      // Pit lane: an open path in its own colour so it never reads as the track
      const pl = replay.track.pitlane
      if (pl && pl.length > 1) {
        const pts = pl.map(([x, y]) => toXY(x, y))
        ctx.beginPath()
        ctx.moveTo(pts[0].x, pts[0].y)
        for (let i = 1; i < pts.length; i++) {
          const mid = { x: (pts[i - 1].x + pts[i].x) / 2, y: (pts[i - 1].y + pts[i].y) / 2 }
          ctx.quadraticCurveTo(pts[i - 1].x, pts[i - 1].y, mid.x, mid.y)
        }
        ctx.lineTo(pts[pts.length - 1].x, pts[pts.length - 1].y)
        ctx.setLineDash([5, 4])
        ctx.strokeStyle = PITLANE_COLOR
        ctx.lineWidth = 2
        ctx.stroke()
        ctx.setLineDash([])
      }

      // Corner numbers need a dark halo to stay legible over the track stroke
      ctx.font = '600 11.5px ui-sans-serif, system-ui, sans-serif'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.shadowColor = 'rgba(6, 8, 14, 0.95)'
      ctx.shadowBlur = 4
      ctx.fillStyle = 'rgba(190, 200, 215, 0.78)'
      for (const c of replay.track.corners) {
        const p = toXY(c.x, c.y)
        ctx.fillText(c.label, p.x, p.y)
      }
      ctx.shadowBlur = 0

      const hits: { code: string; x: number; y: number; r: number }[] = []
      const base = 6.5
      const ordered = [...replay.drivers]
      const front = selected ?? highlighted
      if (front) {
        ordered.sort((a, b) => {
          if (a.code === front) return 1
          if (b.code === front) return -1
          return 0
        })
      }

      for (const drv of ordered) {
        // Retired / non-starting cars leave the map
        if (t > drv.end_t_s + 1) continue
        const series = replay.pos[drv.code]
        if (!series) continue
        const pos = samplePos(series.x, series.y, t, replay.hz)
        if (!pos) continue

        const p = toXY(pos.x, pos.y)
        const isHi = highlighted === drv.code
        const isSel = selected === drv.code
        const r = isHi || isSel ? base + 1.5 : base
        const color = drv.color || '#888'
        const inPit = isInPit(replay.pit_windows?.[drv.code], t)

        // Soft outer glow fading to transparent at the edge
        const glowR = r * 1.8
        const glow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, glowR)
        glow.addColorStop(0, hexToRgba(color, isHi ? 0.6 : 0.38))
        glow.addColorStop(0.45, hexToRgba(color, isHi ? 0.2 : 0.12))
        glow.addColorStop(1, hexToRgba(color, 0))
        ctx.fillStyle = glow
        ctx.beginPath()
        ctx.arc(p.x, p.y, glowR, 0, Math.PI * 2)
        ctx.fill()

        if (inPit) {
          // Hollow and dimmed, so a car in the pits reads as parked, not racing
          ctx.fillStyle = 'rgba(10, 12, 18, 0.85)'
          ctx.beginPath()
          ctx.arc(p.x, p.y, r, 0, Math.PI * 2)
          ctx.fill()
          ctx.strokeStyle = hexToRgba(color, 0.9)
          ctx.lineWidth = 2
          ctx.beginPath()
          ctx.arc(p.x, p.y, r - 1, 0, Math.PI * 2)
          ctx.stroke()
        } else {
          // Solid core with a soft edge
          const core = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r)
          core.addColorStop(0, hexToRgba(color, 1))
          core.addColorStop(0.6, hexToRgba(color, 1))
          core.addColorStop(1, hexToRgba(color, 0.25))
          ctx.fillStyle = core
          ctx.beginPath()
          ctx.arc(p.x, p.y, r, 0, Math.PI * 2)
          ctx.fill()
        }

        if (isHi || isSel) {
          ctx.strokeStyle = isSel ? '#ffffff' : 'rgba(255,255,255,0.9)'
          ctx.lineWidth = isSel ? 2 : 1.5
          ctx.beginPath()
          ctx.arc(p.x, p.y, r + 2.5, 0, Math.PI * 2)
          ctx.stroke()
        }

        hits.push({ code: drv.code, x: p.x, y: p.y, r: r + 5 })
      }
      hitRef.current = hits
    }

    draw()
    const ro = new ResizeObserver(() => draw())
    ro.observe(wrap)
    return () => ro.disconnect()
  }, [replay, t, highlighted, selected])

  const hitTest = (e: React.MouseEvent<HTMLCanvasElement>): string | null => {
    const canvas = canvasRef.current
    if (!canvas) return null
    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    let best: { code: string; d: number } | null = null
    for (const h of hitRef.current) {
      const d = Math.hypot(h.x - x, h.y - y)
      if (d <= h.r && (!best || d < best.d)) best = { code: h.code, d }
    }
    return best?.code ?? null
  }

  const onMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    onHoverDriver?.(hitTest(e))
  }

  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const code = hitTest(e)
    if (code) onSelectDriver?.(code)
  }

  return (
    <div ref={wrapRef} className="replay-track-wrap">
      <div className="replay-track-stage">
        <canvas
          ref={canvasRef}
          className="replay-track-canvas"
          onMouseMove={onMove}
          onMouseLeave={() => onHoverDriver?.(null)}
          onClick={onClick}
          role="img"
          aria-label={`Track map for ${replay.event_name}`}
        />
        {inset && (
          <div ref={insetRef} className="replay-map-inset">
            {inset}
          </div>
        )}
      </div>
      {replay.track.pitlane && replay.track.pitlane.length > 1 && (
        <p className="replay-map-legend">
          <span className="replay-legend-chip" style={{ borderTopColor: PITLANE_COLOR }} />
          Pit lane
        </p>
      )}
    </div>
  )
}

function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace('#', '')
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
  const n = Number.parseInt(full, 16)
  if (Number.isNaN(n)) return `rgba(136,136,136,${alpha})`
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgba(${r},${g},${b},${alpha})`
}
