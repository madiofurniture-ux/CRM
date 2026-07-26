import { Search, Plus, Menu } from "lucide-react";
import { useDrawer } from "@/components/Layout";

export default function Topbar({ title, subtitle, onAdd, addLabel = "New", actions }) {
  const { open } = useDrawer();
  return (
    <div className="sticky top-0 z-30 bg-white/85 backdrop-blur-md border-b border-[var(--border)] flex items-center px-3 md:px-6 gap-2 md:gap-4 h-14 md:h-16" data-testid="topbar">
      <button onClick={open} className="lg:hidden p-2 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink)] shrink-0" data-testid="menu-btn">
        <Menu size={18} strokeWidth={2} />
      </button>

      <div className="flex-1 min-w-0">
        <h1 className="font-heading text-base md:text-[20px] font-semibold text-[var(--ink)] tracking-tight leading-tight truncate">
          {title}
        </h1>
        {subtitle && <div className="text-[11px] md:text-xs text-[var(--ink-3)] mt-0.5 truncate">{subtitle}</div>}
      </div>

      <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--surface-2)] border border-[var(--border)] w-56 lg:w-72">
        <Search size={14} className="text-[var(--ink-3)]" strokeWidth={1.7} />
        <input
          placeholder="Search…"
          className="bg-transparent outline-none text-sm flex-1 placeholder:text-[var(--ink-3)]"
          data-testid="global-search-input"
        />
        <kbd className="hidden lg:inline text-[10px] font-mono text-[var(--ink-3)] px-1.5 py-0.5 rounded border border-[var(--border)]">⌘K</kbd>
      </div>

      {actions}

      {onAdd && (
        <button onClick={onAdd} className="btn-primary" data-testid="topbar-add-btn">
          <Plus size={15} strokeWidth={2} />
          <span className="hidden sm:inline">{addLabel}</span>
        </button>
      )}
    </div>
  );
}
