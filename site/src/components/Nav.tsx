import { useEffect, useId, useRef, useState, useSyncExternalStore } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  getLeaderboardSeason,
  subscribeLeaderboardSeason,
} from '../lib/leaderboardSeason'
import { useLiveWhatIfAvailable } from '../lib/useLiveWhatIfAvailable'
import { isHostedWhatIfDraft } from '../lib/whatIfDefaults'
import { clearWhatIfDraft, leaderboardWhatIfHref, loadWhatIfDraft } from '../lib/whatIfStorage'

const FORMULA15_START = 2021
const FORMULA15_END = 2026

function GitHubIcon() {
  return (
    <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  )
}

function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      {open ? (
        <>
          <path d="M6 6l12 12" />
          <path d="M18 6L6 18" />
        </>
      ) : (
        <>
          <path d="M4 7h16" />
          <path d="M4 12h16" />
          <path d="M4 17h16" />
        </>
      )}
    </svg>
  )
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`nav-dropdown-chevron${open ? ' is-open' : ''}`}
      viewBox="0 0 12 12"
      width="10"
      height="10"
      aria-hidden
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M2.5 4.5L6 8l3.5-3.5" />
    </svg>
  )
}

export function Nav() {
  const location = useLocation()
  const navigate = useNavigate()
  const menuId = useId()
  const dropdownId = useId()
  const rootRef = useRef<HTMLElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const menuToggleRef = useRef<HTMLButtonElement>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [lbOpen, setLbOpen] = useState(false)
  const { available: liveWhatIf } = useLiveWhatIfAvailable()
  const season = useSyncExternalStore(
    subscribeLeaderboardSeason,
    getLeaderboardSeason,
    getLeaderboardSeason,
  )
  const draft = loadWhatIfDraft()
  const leaderboardHref =
    liveWhatIf || isHostedWhatIfDraft(draft) ? leaderboardWhatIfHref(draft) : '/leaderboard'
  const onLeaderboard =
    location.pathname === '/' || location.pathname === '/leaderboard'
  const formula15Active = onLeaderboard && new URLSearchParams(location.search).get('f15') === '1'
  const reversedActive = onLeaderboard && new URLSearchParams(location.search).get('rev') === '1'
  const leaderboardActive = onLeaderboard
  const lbLabel = !onLeaderboard
    ? 'Leaderboards'
    : reversedActive
      ? 'Reversed'
      : formula15Active
        ? 'Formula 1.5'
        : 'Formula 1'
  const formula15Disabled = onLeaderboard && !formula15Active && !reversedActive && season < FORMULA15_START
  const normalLeaderboardActive = leaderboardActive && !formula15Active && !reversedActive

  useEffect(() => {
    setMenuOpen(false)
    setLbOpen(false)
  }, [location.pathname, location.search])

  useEffect(() => {
    if (!menuOpen) return

    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (lbOpen) {
          setLbOpen(false)
          return
        }
        setMenuOpen(false)
        menuToggleRef.current?.focus()
      }
    }
    const onPointerDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) {
        setMenuOpen(false)
        setLbOpen(false)
      }
    }

    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('mousedown', onPointerDown)

    const firstLink = rootRef.current?.querySelector<HTMLElement>('.nav-links a, .nav-links .nav-link')
    firstLink?.focus()

    return () => {
      document.body.style.overflow = prevOverflow
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('mousedown', onPointerDown)
    }
  }, [menuOpen, lbOpen])

  useEffect(() => {
    if (!lbOpen || menuOpen) return

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setLbOpen(false)
    }
    const onPointerDown = (e: MouseEvent) => {
      if (!dropdownRef.current?.contains(e.target as Node)) setLbOpen(false)
    }

    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('mousedown', onPointerDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('mousedown', onPointerDown)
    }
  }, [lbOpen, menuOpen])

  const goLeaderboard = (e: React.MouseEvent) => {
    e.preventDefault()
    setLbOpen(false)
    setMenuOpen(false)
    navigate(leaderboardHref, { preventScrollReset: true })
  }

  const goFormula15 = (e: React.MouseEvent) => {
    e.preventDefault()
    if (formula15Disabled) return
    clearWhatIfDraft()
    setLbOpen(false)
    setMenuOpen(false)
    navigate('/leaderboard?f15=1', { preventScrollReset: true })
  }

  const goReversed = (e: React.MouseEvent) => {
    e.preventDefault()
    clearWhatIfDraft()
    setLbOpen(false)
    setMenuOpen(false)
    navigate('/leaderboard?rev=1', { preventScrollReset: true })
  }

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? 'nav-link active' : 'nav-link'

  return (
    <header ref={rootRef} className={`site-nav${menuOpen ? ' is-open' : ''}`}>
      <div className="nav-inner">
        <div className="brand">
          <span className="brand-mark" aria-hidden />
          <span className="brand-text">DeltaV</span>
        </div>

        <div className="nav-actions">
          <a
            className="nav-github"
            href="https://github.com/JustAA1/DeltaV"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="DeltaV on GitHub"
            title="GitHub"
          >
            <GitHubIcon />
          </a>
          <button
            ref={menuToggleRef}
            type="button"
            className="nav-menu-toggle"
            aria-expanded={menuOpen}
            aria-controls={menuId}
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <MenuIcon open={menuOpen} />
          </button>
        </div>

        <nav id={menuId} className="nav-links" aria-label="Main">
          <div
            ref={dropdownRef}
            className={`nav-dropdown${lbOpen ? ' is-open' : ''}`}
          >
            <button
              type="button"
              className={leaderboardActive ? 'nav-link nav-dropdown-trigger active' : 'nav-link nav-dropdown-trigger'}
              aria-expanded={lbOpen}
              aria-controls={dropdownId}
              aria-haspopup="menu"
              onClick={() => setLbOpen((open) => !open)}
            >
              <span>{lbLabel}</span>
              <ChevronIcon open={lbOpen} />
            </button>
            <div id={dropdownId} className="nav-dropdown-menu" role="menu" hidden={!lbOpen}>
              <a
                href={leaderboardHref}
                role="menuitem"
                className={normalLeaderboardActive ? 'nav-dropdown-item is-active' : 'nav-dropdown-item'}
                onClick={goLeaderboard}
              >
                Formula 1
              </a>
              {formula15Disabled ? (
                <div
                  className="nav-dropdown-item is-disabled"
                  role="menuitem"
                  aria-disabled="true"
                >
                  <span>Formula 1.5</span>
                  <span className="nav-dropdown-tag">for {FORMULA15_START}–{FORMULA15_END}</span>
                </div>
              ) : (
                <a
                  href="/leaderboard?f15=1"
                  role="menuitem"
                  className={
                    formula15Active
                      ? 'nav-dropdown-item nav-dropdown-item-stack is-active'
                      : 'nav-dropdown-item nav-dropdown-item-stack'
                  }
                  onClick={goFormula15}
                >
                  <span>Formula 1.5</span>
                  <span className="nav-dropdown-tag">for {FORMULA15_START}–{FORMULA15_END}</span>
                </a>
              )}
              <a
                href="/leaderboard?rev=1"
                role="menuitem"
                className={
                  reversedActive
                    ? 'nav-dropdown-item nav-dropdown-item-stack is-active'
                    : 'nav-dropdown-item nav-dropdown-item-stack'
                }
                onClick={goReversed}
              >
                <span>Reversed</span>
                <span className="nav-dropdown-tag">excludes DNFs</span>
              </a>
            </div>
          </div>
          <NavLink to="/replays" className={linkClass} onClick={() => setMenuOpen(false)}>
            Replays
          </NavLink>
          <NavLink to="/podiumigami" className={linkClass} onClick={() => setMenuOpen(false)}>
            Podiumigami
          </NavLink>
          <NavLink to="/what-if" className={linkClass} onClick={() => setMenuOpen(false)}>
            What If?
          </NavLink>
        </nav>
      </div>
    </header>
  )
}
