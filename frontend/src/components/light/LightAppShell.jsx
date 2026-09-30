import { useState } from "react";
import LightSidebar from "@/components/light/LightSidebar";
import LightTopbar from "@/components/light/LightTopbar";

/** The light theme's app shell: spacious left sidebar (desktop) that
 * collapses to icon-only on tablet and to an overlay drawer on mobile, plus
 * a top bar. Wraps `children` exactly like the baseplate Layout wraps its
 * page slot — same page content, different chrome, per
 * docs/LIGHT_THEME_MIGRATION_PLAN.md's "no duplicated pages" rule. */
export default function LightAppShell({ children }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="min-h-screen flex bg-[var(--color-bg)]" data-testid="light-app-shell">
      {/* Desktop/tablet sidebar */}
      <div className="hidden md:block shrink-0">
        <LightSidebar collapsed={collapsed} />
      </div>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
          <div className="relative z-10 h-full">
            <LightSidebar onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      )}

      <div className="flex-1 min-w-0 flex flex-col">
        <LightTopbar
          onToggleSidebar={() => {
            // Narrow viewports open the drawer; md+ toggles icon-only collapse.
            if (window.innerWidth < 768) setMobileOpen((v) => !v);
            else setCollapsed((v) => !v);
          }}
        />
        <main id="main-content" tabIndex={-1} className="flex-1 min-w-0 outline-none overflow-x-hidden">
          {children}
        </main>
      </div>
    </div>
  );
}
