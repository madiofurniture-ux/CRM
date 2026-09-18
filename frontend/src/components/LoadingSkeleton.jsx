/** Generic pulsing placeholder block — `lines` stacked bars of `width`. */
export default function LoadingSkeleton({ lines = 1, width = "100%", height = "1rem", className = "" }) {
  return (
    <div className={`space-y-2 ${className}`} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="bg-[var(--color-surface-muted)] rounded animate-pulse"
          style={{ width, height }}
        />
      ))}
    </div>
  );
}
