export function WhatIfPointsClauseText({
  season,
  pointsFrom,
  seasonColor,
  pointsFromColor,
  prefix = '',
  className,
}: {
  season: number
  pointsFrom: number
  seasonColor: string
  pointsFromColor: string
  prefix?: string
  className?: string
}) {
  return (
    <span className={className ? `what-if-clause ${className}` : 'what-if-clause'}>
      {prefix}
      <span className="what-if-clause-entity" style={{ color: seasonColor }}>
        {season}
      </span>
      {' had the points system from '}
      <span className="what-if-clause-entity" style={{ color: pointsFromColor }}>
        {pointsFrom}
      </span>
    </span>
  )
}
