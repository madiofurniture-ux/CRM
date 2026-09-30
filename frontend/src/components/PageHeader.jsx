/** Page title row — eyebrow/title/subtitle on the left, real actions
 * (period selector, refresh, etc.) on the right. Used first by the
 * Overview page's greeting; generic enough for any page's header. */
export default function PageHeader({ eyebrow, title, subtitle, actions }) {
  return (
    <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
      <div>
        {eyebrow && (
          <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--color-text-muted)] mb-1">
            {eyebrow}
          </div>
        )}
        <h1 className="text-2xl font-bold text-[var(--color-text)]">{title}</h1>
        {subtitle && <p className="text-sm text-[var(--color-text-muted)] mt-1 max-w-xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
