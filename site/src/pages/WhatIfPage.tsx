import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { WhatIfClauseText } from '../components/WhatIfClauseText'
import { WhatIfPointsClauseText } from '../components/WhatIfPointsClauseText'
import {
  DEFAULT_POINTS_FROM,
  DEFAULT_POINTS_SEASON,
  DEFAULT_WHAT_IF_SEASON,
  DEFAULT_WHAT_IF_TEAM,
  DEFAULT_WHAT_IF_TEAM_COLOR,
} from '../lib/whatIfDefaults'
import { useLiveWhatIfAvailable } from '../lib/useLiveWhatIfAvailable'
import {
  formatWhatIfNames,
  loadPointsWhatIfDraft,
  loadRemoveWhatIfDraft,
  savePointsWhatIfDraft,
  saveRemoveWhatIfDraft,
  saveWhatIfDraft,
  whatIfSearchParams,
  type WhatIfRemoval,
} from '../lib/whatIfStorage'

const SEASONS = Array.from({ length: 2026 - 1980 + 1 }, (_, i) => 2026 - i)
const FALLBACK_ACCENT = '#888888'

function textOnColor(hex: string): string {
  const h = hex.replace('#', '')
  if (h.length !== 6) return '#0a0a0c'
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.62 ? '#0a0a0c' : '#ffffff'
}

function championColor(
  champions: Record<string, { color: string }> | undefined,
  year: number,
): string {
  return champions?.[String(year)]?.color ?? FALLBACK_ACCENT
}

function initialRemoveState() {
  const draft = loadRemoveWhatIfDraft()
  if (draft) {
    return {
      season: draft.season,
      entityType: draft.removeType,
      selectedValues: draft.removes.map((r) =>
        draft.removeType === 'driver' ? r.id ?? r.name : r.name,
      ),
    }
  }
  return {
    season: DEFAULT_WHAT_IF_SEASON,
    entityType: 'team' as const,
    // Hardcoded default scenario: remove Mercedes from 2026
    selectedValues: [DEFAULT_WHAT_IF_TEAM],
  }
}

function initialPointsState() {
  const draft = loadPointsWhatIfDraft()
  if (draft) {
    return { season: draft.season, pointsFrom: draft.pointsFrom }
  }
  return { season: DEFAULT_POINTS_SEASON, pointsFrom: DEFAULT_POINTS_FROM }
}

function removalsFromSelection(
  entityType: 'driver' | 'team',
  selectedValues: string[],
  options: { drivers: { id: string; name: string }[]; teams: { name: string }[] } | undefined,
): WhatIfRemoval[] {
  if (selectedValues.length === 0) return []
  if (entityType === 'driver') {
    return selectedValues.map((value) => {
      const driver = options?.drivers.find((d) => d.id === value)
      return { id: value, name: driver?.name ?? value }
    })
  }
  return selectedValues.map((name) => ({ name }))
}

interface EntityChoice {
  value: string
  label: string
  color: string
}

function WhatIfEntityMultiSelect({
  choices,
  selectedValues,
  onChange,
  disabled,
  placeholder,
  ariaLabel,
}: {
  choices: EntityChoice[]
  selectedValues: string[]
  onChange: (next: string[]) => void
  disabled?: boolean
  placeholder: string
  ariaLabel: string
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  const selectedSet = useMemo(() => new Set(selectedValues), [selectedValues])
  const selectedLabels = choices.filter((c) => selectedSet.has(c.value)).map((c) => c.label)
  const triggerLabel =
    selectedLabels.length > 0 ? formatWhatIfNames(selectedLabels) : placeholder

  useEffect(() => {
    setOpen(false)
  }, [choices, disabled])

  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const toggleValue = (value: string) => {
    onChange(
      selectedSet.has(value)
        ? selectedValues.filter((v) => v !== value)
        : [...selectedValues, value],
    )
  }

  return (
    <div className={`what-if-multiselect${open ? ' is-open' : ''}`} ref={rootRef}>
      <button
        type="button"
        className="what-if-multiselect-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span className={selectedLabels.length === 0 ? 'what-if-multiselect-placeholder' : undefined}>
          {triggerLabel}
        </span>
      </button>
      {open && (
        <div className="what-if-multiselect-menu" role="listbox" aria-multiselectable aria-label={ariaLabel}>
          {choices.map((c) => {
            const checked = selectedSet.has(c.value)
            return (
              <button
                key={c.value}
                type="button"
                role="option"
                aria-selected={checked}
                className={`what-if-multiselect-option${checked ? ' is-selected' : ''}`}
                onClick={() => toggleValue(c.value)}
              >
                <span className="what-if-multiselect-check" aria-hidden>
                  {checked ? '✓' : ''}
                </span>
                <span className="what-if-entity-swatch" style={{ background: c.color }} aria-hidden />
                <span className="what-if-entity-label">{c.label}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function YearSelect({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (year: number) => void
}) {
  return (
    <label className="what-if-field">
      <span className="what-if-field-label">{label}</span>
      <select value={value} onChange={(e) => onChange(Number(e.target.value))}>
        {SEASONS.map((y) => (
          <option key={y} value={y}>
            {y}
          </option>
        ))}
      </select>
    </label>
  )
}

function PointsSystemYearSelect({
  label,
  value,
  onChange,
  yearNotes,
}: {
  label: string
  value: number
  onChange: (year: number) => void
  yearNotes: Record<string, string>
}) {
  return (
    <label className="what-if-field">
      <span className="what-if-field-label">{label}</span>
      <select
        className="what-if-points-year-select"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      >
        {SEASONS.map((y) => {
          const note = yearNotes[String(y)]
          return (
            <option key={y} value={y}>
              {note ? `${y} — ${note}` : y}
            </option>
          )
        })}
      </select>
    </label>
  )
}

export function WhatIfPage() {
  const navigate = useNavigate()
  const { available: liveWhatIf, status: liveStatus } = useLiveWhatIfAvailable()
  const initialDefaultApplied = useRef(Boolean(loadRemoveWhatIfDraft()))
  const removeFormTouched = useRef(false)
  const removeInit = initialRemoveState()
  const pointsInit = initialPointsState()

  const [season, setSeason] = useState(removeInit.season)
  const [entityType, setEntityType] = useState<'driver' | 'team'>(removeInit.entityType)
  const [selectedValues, setSelectedValues] = useState<string[]>(removeInit.selectedValues)

  const [pointsSeason, setPointsSeason] = useState(pointsInit.season)
  const [pointsFrom, setPointsFrom] = useState(pointsInit.pointsFrom)

  const { data: options, isLoading } = useQuery({
    queryKey: ['what-if-options', season],
    queryFn: () => api.whatIfOptions(season),
  })

  const { data: championsData } = useQuery({
    queryKey: ['constructor-champions'],
    queryFn: () => api.whatIfConstructorChampions(),
  })

  const { data: pointsSystemChangesData } = useQuery({
    queryKey: ['points-system-changes'],
    queryFn: () => api.whatIfPointsSystemChanges(),
  })

  const pointsSystemChanges = pointsSystemChangesData?.changes ?? {}
  const pointsSeasonChanges = pointsSystemChangesData?.seasonChanges ?? {}
  const pointsSystemKeys = pointsSystemChangesData?.systems ?? {}

  const champions = championsData?.champions

  const entityChoices = useMemo(() => {
    if (!options) {
      // Show hardcoded default team before leaderboard options resolve
      if (entityType === 'team' && season === DEFAULT_WHAT_IF_SEASON) {
        return [
          {
            value: DEFAULT_WHAT_IF_TEAM,
            label: DEFAULT_WHAT_IF_TEAM,
            color: DEFAULT_WHAT_IF_TEAM_COLOR,
          },
        ]
      }
      return []
    }
    return entityType === 'driver'
      ? options.drivers.map((d) => ({
          value: d.id,
          label: d.name,
          color: d.color,
        }))
      : options.teams.map((t) => ({
          value: t.name,
          label: t.name,
          color: t.color,
        }))
  }, [options, entityType, season])

  const selectedSet = useMemo(() => new Set(selectedValues), [selectedValues])
  const selectedChoices = useMemo(
    () => entityChoices.filter((c) => selectedSet.has(c.value)),
    [entityChoices, selectedSet],
  )

  useEffect(() => {
    if (initialDefaultApplied.current || entityType !== 'team') return
    if (season !== DEFAULT_WHAT_IF_SEASON || selectedValues.length > 0) return
    setSelectedValues([DEFAULT_WHAT_IF_TEAM])
    initialDefaultApplied.current = true
  }, [entityType, season, selectedValues.length])

  useEffect(() => {
    if (!options || selectedValues.length === 0 || entityChoices.length === 0) return
    const valid = new Set(entityChoices.map((c) => c.value))
    const filtered = selectedValues.filter((v) => valid.has(v))
    if (filtered.length !== selectedValues.length) setSelectedValues(filtered)
  }, [options, entityChoices, selectedValues])

  const removals = useMemo(
    () => removalsFromSelection(entityType, selectedValues, options),
    [entityType, selectedValues, options],
  )

  const clauseEntities = useMemo(
    () => selectedChoices.map((c) => ({ name: c.label, color: c.color })),
    [selectedChoices],
  )

  const removeAccent = selectedChoices[0]?.color ?? FALLBACK_ACCENT
  const pointsSeasonColor = championColor(champions, pointsSeason)
  const pointsFromColor = championColor(champions, pointsFrom)
  const samePointsSystem = useMemo(() => {
    const seasonKey = pointsSystemKeys[String(pointsSeason)]
    const fromKey = pointsSystemKeys[String(pointsFrom)]
    if (seasonKey && fromKey) return seasonKey === fromKey
    return pointsSeason === pointsFrom
  }, [pointsSystemKeys, pointsSeason, pointsFrom])

  const canSubmitRemove = removals.length > 0

  const markRemoveTouched = () => {
    removeFormTouched.current = true
  }

  useEffect(() => {
    if (!removeFormTouched.current || removals.length === 0) return
    saveRemoveWhatIfDraft({ kind: 'remove', season, removeType: entityType, removes: removals })
  }, [season, entityType, removals])

  useEffect(() => {
    savePointsWhatIfDraft({ kind: 'points', season: pointsSeason, pointsFrom })
  }, [pointsSeason, pointsFrom])

  const handleRemoveSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!liveWhatIf || !canSubmitRemove) return
    const draft = { kind: 'remove' as const, season, removeType: entityType, removes: removals }
    saveWhatIfDraft(draft)
    navigate(`/leaderboard?${whatIfSearchParams(draft).toString()}`)
  }

  const handlePointsSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!liveWhatIf) return
    const draft = { kind: 'points' as const, season: pointsSeason, pointsFrom }
    saveWhatIfDraft(draft)
    navigate(`/leaderboard?${whatIfSearchParams(draft).toString()}`)
  }

  const removeCardStyle = {
    '--what-if-accent': removeAccent,
    '--what-if-accent-text': textOnColor(removeAccent),
  } as React.CSSProperties

  const pointsCardStyle = {
    '--what-if-accent': pointsSeasonColor,
    '--what-if-accent-text': textOnColor(pointsSeasonColor),
  } as React.CSSProperties

  const removePlaceholder = entityType === 'driver' ? '<select drivers>' : '<select teams>'

  return (
    <section className="page what-if-page">
      <div className="what-if-inner">
        <header className="what-if-header">
          <h1>What If?</h1>
          <p className="what-if-subtitle">
            Explore alternate championships by removing drivers and teams, or swapping in a different
            era&apos;s points system.
          </p>
          {!liveWhatIf && (
            <p className="what-if-local-only" role="status">
              {liveStatus === 'checking'
                ? 'Checking for the local DeltaV API…'
                : (
                  <>
                    Alternate standings need the local DeltaV API. Clone the repo, run{' '}
                    <code>api/</code> (<code>uvicorn</code> on port 8000) and{' '}
                    <code>site/</code> with <code>npm run dev</code>, then use View alternate
                    standings here.
                  </>
                )}
            </p>
          )}
        </header>

        <div className="what-if-scenarios">
          <form className="what-if-card" style={removeCardStyle} onSubmit={handleRemoveSubmit}>
            <div className="what-if-card-head">
              <h2 className="what-if-card-title">Remove from grid</h2>
              <p className="what-if-card-desc">See how the season plays out without them.</p>
            </div>

            <div className="what-if-preview" aria-live="polite">
              <span className="what-if-scenario-label">Scenario</span>
              <p className="what-if-scenario-text">
                What if{' '}
                {clauseEntities.length > 0 ? (
                  <>
                    <WhatIfClauseText entities={clauseEntities} season={season} />?
                  </>
                ) : (
                  <>
                    <span className="what-if-placeholder">{removePlaceholder}</span> didn&apos;t race in{' '}
                    <span className="what-if-clause-season">{season}</span>?
                  </>
                )}
              </p>
            </div>

            <div className="what-if-fields">
              <YearSelect
                label="Year"
                value={season}
                onChange={(year) => {
                  markRemoveTouched()
                  setSeason(year)
                }}
              />

              <label className="what-if-field">
                <span className="what-if-field-label">Remove</span>
                <select
                  value={entityType}
                  onChange={(e) => {
                    markRemoveTouched()
                    setEntityType(e.target.value as 'driver' | 'team')
                    setSelectedValues([])
                  }}
                >
                  <option value="team">Teams</option>
                  <option value="driver">Drivers</option>
                </select>
              </label>

              <label className="what-if-field what-if-field-span">
                <span className="what-if-field-label">
                  {entityType === 'driver' ? 'Drivers' : 'Teams'}
                </span>
                {isLoading && entityChoices.length === 0 ? (
                  <div className="what-if-entity-loading what-if-select-like">Loading…</div>
                ) : entityChoices.length === 0 ? (
                  <div className="what-if-entity-loading what-if-select-like">No options for this season.</div>
                ) : (
                  <WhatIfEntityMultiSelect
                    choices={entityChoices}
                    selectedValues={selectedValues}
                    onChange={(next) => {
                      markRemoveTouched()
                      setSelectedValues(next)
                    }}
                    placeholder={entityType === 'driver' ? 'Select drivers' : 'Select teams'}
                    ariaLabel={entityType === 'driver' ? 'Drivers' : 'Teams'}
                  />
                )}
              </label>
            </div>

            <button
              type="submit"
              className="what-if-submit"
              disabled={!liveWhatIf || !canSubmitRemove}
              title={
                liveWhatIf
                  ? undefined
                  : 'Run DeltaV locally (api + npm run dev) to view alternate standings'
              }
            >
              {liveWhatIf ? 'View alternate standings' : 'Available locally only'}
            </button>
          </form>

          <form className="what-if-card" style={pointsCardStyle} onSubmit={handlePointsSubmit}>
            <div className="what-if-card-head">
              <h2 className="what-if-card-title">Swap points system</h2>
              <p className="what-if-card-desc">Replay a season with another year&apos;s scoring rules.</p>
            </div>

            <div className="what-if-preview" aria-live="polite">
              <span className="what-if-scenario-label">Scenario</span>
              <p className="what-if-scenario-text">
                What if{' '}
                <WhatIfPointsClauseText
                  season={pointsSeason}
                  pointsFrom={pointsFrom}
                  seasonColor={pointsSeasonColor}
                  pointsFromColor={pointsFromColor}
                />
                ?
              </p>
            </div>

            <div className="what-if-fields">
              <PointsSystemYearSelect
                label="Season"
                value={pointsSeason}
                onChange={setPointsSeason}
                yearNotes={pointsSeasonChanges}
              />
              <PointsSystemYearSelect
                label="Points system from"
                value={pointsFrom}
                onChange={setPointsFrom}
                yearNotes={pointsSystemChanges}
              />
            </div>

            {samePointsSystem && (
              <p className="what-if-warning" role="status">
                This season already used that points system — results won&apos;t change.
              </p>
            )}

            <button
              type="submit"
              className="what-if-submit"
              disabled={!liveWhatIf}
              title={
                liveWhatIf
                  ? undefined
                  : 'Run DeltaV locally (api + npm run dev) to view alternate standings'
              }
            >
              {liveWhatIf ? 'View alternate standings' : 'Available locally only'}
            </button>
          </form>
        </div>
      </div>
    </section>
  )
}
