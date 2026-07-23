import { Fragment } from 'react'

export interface WhatIfClauseEntity {
  name: string
  color: string
}

function entitySeparator(index: number, total: number): string {
  if (index === 0) return ''
  if (index === total - 1) return total === 2 ? ' and ' : ', and '
  return ', '
}

export function WhatIfClauseText({
  entities,
  season,
  prefix = '',
  className,
}: {
  entities: WhatIfClauseEntity[]
  season: number
  prefix?: string
  className?: string
}) {
  if (entities.length === 0) return null

  return (
    <span className={className ? `what-if-clause ${className}` : 'what-if-clause'}>
      {prefix}
      {entities.map((entity, index) => (
        <Fragment key={`${entity.name}-${index}`}>
          {entitySeparator(index, entities.length)}
          <span className="what-if-clause-entity" style={{ color: entity.color }}>
            {entity.name}
          </span>
        </Fragment>
      ))}
      {" didn't race in "}
      <span className="what-if-clause-season">{season}</span>
    </span>
  )
}
