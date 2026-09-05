import { NavLink } from "react-router-dom";
import { LayoutDashboard, Sparkles, Contact, Columns3, Menu } from "lucide-react";
import { useSidebar } from "@/context/SidebarContext";

// Sticky bottom nav for phones — the four most-used destinations plus
// "More", which opens the existing sidebar drawer for everything else.
// Desktop/tablet (lg+) keep the sidebar only; this never renders there.
const ITEMS = [
  { to: "/", label: "Home", icon: LayoutDashboard, end: true },
  { to: "/leads", label: "Leads", icon: Sparkles },
  { to: "/customers", label: "Customers", icon: Contact },
  { to: "/pipeline", label: "Pipeline", icon: Columns3 },
];

export default function BottomNav() {
  const { setOpen } = useSidebar();

  return (
    <nav
      className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-white/95 backdrop-blur-md border-t border-[var(--border)] flex items-stretch"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      data-testid="bottom-nav"
    >
      {ITEMS.map((it) => {
        const Icon = it.icon;
        return (
          <NavLink
            key={it.to}
            to={it.to}
            end={it.end}
            className={({ isActive }) =>
              `flex-1 flex flex-col items-center justify-center gap-0.5 py-2 text-[10px] font-medium ${
                isActive ? "text-[var(--brand)]" : "text-[var(--ink-3)]"
              }`
            }
            data-testid={`bottomnav-${it.label.toLowerCase()}`}
          >
            <Icon size={20} strokeWidth={1.8} />
            {it.label}
          </NavLink>
        );
      })}
      <button
        onClick={() => setOpen(true)}
        className="flex-1 flex flex-col items-center justify-center gap-0.5 py-2 text-[10px] font-medium text-[var(--ink-3)]"
        data-testid="bottomnav-more"
      >
        <Menu size={20} strokeWidth={1.8} />
        More
      </button>
    </nav>
  );
}
