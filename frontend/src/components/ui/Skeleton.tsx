/** Placeholder block shown while content loads, so layouts don't jump. */
export function Skeleton({ className = "h-4 w-full" }: { className?: string }) {
  return <div aria-hidden className={`animate-pulse rounded-md bg-line/60 ${className}`} />;
}

export function SkeletonList({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="rounded-card border border-line bg-surface p-4">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="mt-2 h-3 w-2/3" />
        </div>
      ))}
    </div>
  );
}
