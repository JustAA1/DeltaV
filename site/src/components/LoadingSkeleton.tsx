export function LoadingSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="skeleton-grid">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton-card" />
      ))}
    </div>
  )
}
