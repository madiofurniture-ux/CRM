/** A titled content panel — the light-theme equivalent of the ad-hoc
 * `bg-white border rounded-2xl p-6` blocks pages currently hand-roll.
 * Token-driven, so it's correct under both themes. */
export default function SectionCard({ title, subtitle, action, children, className = "" }) {
  return (
    <div
      className={`bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-6 ${className}`}
    >
      {(title || action) && (
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            {title && <div className="font-semibold text-[var(--color-text)]">{title}</div>}
            {subtitle && <div className="text-xs text-[var(--color-text-muted)] mt-0.5">{subtitle}</div>}
          </div>
          {action}
        </div>
      )}
      {children}
    </div>
  );
}
