import { useState } from "react";
import { Link } from "react-router-dom";
import { COMMAND_CENTRE_SALES_SUBNAV } from "@/lib/nav";

const PILLS = [
  { n: "01", label: "Overview", count: 3, tab: "overview" },
  { n: "02", label: "Sales", count: 5, tab: "sales" },
  { n: "03", label: "Clients", count: 3, tab: "clients" },
  { n: "04", label: "Delivery", count: 5, tab: "delivery" },
  { n: "05", label: "Inventory", count: 3, tab: "inventory" },
  { n: "06", label: "Finance", count: 6, tab: "finance" },
  { n: "07", label: "People", count: 8, tab: "people" },
  { n: "08", label: "Control", count: 7, tab: "control" },
  { n: "09", label: "Product", count: 8, tab: "product" },
];

/**
 * Baseplate dual-tier shell: dark environment bar, primary numbered-pill nav,
 * and (for Overview/Sales) a sub-nav strip below it. Self-contained — this is
 * the Command Centre's own header, not a replacement for the app-wide
 * Sidebar/Topbar every other screen still uses.
 */
export default function Header({ activeTab = "overview", onTabChange }) {
  const [tab, setTab] = useState(activeTab);

  const selectTab = (t) => {
    setTab(t);
    onTabChange?.(t);
  };

  const showSubnav = tab === "overview" || tab === "sales";

  return (
    <div className="font-sans" data-testid="baseplate-header">
      {/* Baseplate bar */}
      <div className="h-8 bg-[#0B0D12] text-[11px] text-white/70 flex items-center justify-between px-4">
        <div className="flex items-center gap-1.5 font-mono uppercase tracking-wider">
          <span className="text-white font-semibold">BASEPLATE</span>
          <span className="text-white/30">/</span>
          <span>in_madio</span>
          <span className="text-white/30">/</span>
          <span>Madio — template org</span>
        </div>
        <div className="flex items-center gap-2 font-mono uppercase tracking-wider">
          <span>scope: unit</span>
          <span className="text-white/30">|</span>
          <span>FY 2026-27</span>
          <span className="text-white/30">|</span>
          <span>prod · release 4.2.0</span>
        </div>
      </div>

      {/* Primary nav */}
      <div className="h-16 bg-[#14161C] flex items-center justify-between px-4 gap-4">
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-[#EC3013] text-white flex items-center justify-center font-bold text-sm">M</div>
          <div className="text-white text-sm font-semibold hidden lg:block">Madio — template org</div>
        </div>

        <nav className="flex items-center gap-1 overflow-x-auto">
          {PILLS.map((p) => {
            const active = tab === p.tab;
            return (
              <button
                key={p.tab}
                type="button"
                onClick={() => selectTab(p.tab)}
                data-testid={`nav-pill-${p.tab}`}
                className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-semibold font-mono transition ${
                  active ? "bg-[#EC3013] text-white" : "text-white/60 hover:text-white hover:bg-white/5"
                }`}
              >
                {p.n} {p.label} <span className={active ? "text-white/80" : "text-white/40"}>({p.count})</span>
              </button>
            );
          })}
        </nav>

        <div className="flex items-center gap-2 shrink-0">
          <div className="w-8 h-8 rounded-full bg-white/10 text-white flex items-center justify-center font-bold text-xs">DH</div>
          <div className="hidden xl:block leading-tight">
            <div className="text-white text-xs font-semibold">Division Head</div>
            <div className="text-white/40 text-[10px]">Unit scope</div>
          </div>
        </div>
      </div>

      {/* Sub-nav strip */}
      {showSubnav && (
        <div className="h-11 bg-[#1B1E26] flex items-center gap-3 px-4" data-testid="subnav-strip">
          <span className="text-[10px] font-mono font-bold tracking-widest text-[#EC3013]">
            {tab.toUpperCase()}
          </span>
          {tab === "sales" && (
            <div className="flex items-center gap-1.5">
              {COMMAND_CENTRE_SALES_SUBNAV.map((s) => (
                <Link
                  key={s.code}
                  to={s.to}
                  className="px-2.5 py-1 rounded-md text-[11px] font-mono text-white/70 hover:text-white hover:bg-white/5 transition flex items-center gap-1"
                >
                  <span className="text-white/40">{s.code}</span> {s.label}
                  {s.isNew && <span className="text-[9px] px-1 rounded bg-[#EC3013] text-white font-bold">NEW</span>}
                </Link>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
