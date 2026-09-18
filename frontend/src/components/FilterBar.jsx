import { Search } from "lucide-react";

/** Search box + arbitrary filter controls row for a list page's toolbar.
 * `children` are the page's own filter controls (selects, chips, etc.) —
 * this component only standardizes the search input and layout. */
export default function FilterBar({ search, onSearchChange, searchPlaceholder = "Search", children }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {onSearchChange && (
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
          <input
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder}
            className="pl-8 pr-3 py-2 text-sm rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] outline-none focus:border-[var(--color-primary)] w-56"
          />
        </div>
      )}
      {children}
    </div>
  );
}
