import { Search, Plus, Menu } from "lucide-react";
import { useSidebar } from "@/context/SidebarContext";

export default function Topbar({ title, subtitle, onAdd, addLabel = "New", actions }) {
  const { setOpen } = useSidebar();
  return (
    <div className="sticky top-0 z-30 h-16 bg-white/85 backdrop-blur-md border-b border-[var(--border)] flex items-center px-3 sm:px-6 gap-2 sm:gap-4" data-testid="topbar">
      <button
        onClick={() => setOpen(true)}
        className="p-2 -ml-1 rounded-md hover:bg-[var(--surface-2)] text-[var(--ink-2)] lg:hidden shrink-0"
        aria-label="Open menu"
        data-testid="sidebar-open-btn"
      >
        <Menu size={20} strokeWidth={1.7} />
      </button>

      <div className="flex-1 min-w-0">
        <h1 className="font-heading text-[17px] sm:text-[20px] font-semibold text-[var(--ink)] tracking-tight leading-tight truncate">
          {title}
        </h1>
        {subtitle && <div className="hidden sm:block text-xs text-[var(--ink-3)] mt-0.5">{subtitle}</div>}
      </div>

      <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--surface-2)] border border-[var(--border)] w-72">
        <Search size={14} className="text-[var(--ink-3)]" strokeWidth={1.7} />
        <input
          placeholder="Search…"
          className="bg-transparent outline-none text-sm flex-1 placeholder:text-[var(--ink-3)]"
          data-testid="global-search-input"
        />
        <kbd className="text-[10px] font-mono text-[var(--ink-3)] px-1.5 py-0.5 rounded border border-[var(--border)]">⌘K</kbd>
      </div>

      {actions}

      {onAdd && (
        <button onClick={onAdd} className="btn-primary shrink-0 px-3 sm:px-4" data-testid="topbar-add-btn">
          <Plus size={15} strokeWidth={2} />
          <span className="hidden sm:inline">{addLabel}</span>
        </button>
      )}
    </div>
  );
}
