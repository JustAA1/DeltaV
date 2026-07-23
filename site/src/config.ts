/**
 * Live What If compute (POST /api/what-if*) needs the local `api/` server.
 *
 * - Production / Vercel builds: always unavailable (static host).
 * - Dev: probed via GET /api/health (Vite proxies to uvicorn).
 * - Override: VITE_WHAT_IF_API=1 forces available; =0 forces off.
 */
const FORCE = import.meta.env.VITE_WHAT_IF_API

export const IS_PRODUCTION_BUILD = import.meta.env.PROD

export function whatIfForceFlag(): boolean | null {
  if (FORCE === '1' || FORCE === 'true') return true
  if (FORCE === '0' || FORCE === 'false') return false
  return null
}
