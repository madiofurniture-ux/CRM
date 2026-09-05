export const inr = (n) => {
  if (n === null || n === undefined || isNaN(n)) return "₹0";
  const v = Number(n);
  if (Math.abs(v) >= 10000000) return `₹${(v / 10000000).toFixed(2)}Cr`;
  if (Math.abs(v) >= 100000) return `₹${(v / 100000).toFixed(2)}L`;
  if (Math.abs(v) >= 1000) return `₹${(v / 1000).toFixed(1)}k`;
  return `₹${v.toFixed(0)}`;
};

export const inrFull = (n) => {
  if (n === null || n === undefined || isNaN(n)) return "₹0";
  return "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });
};

export const fmtDate = (s) => {
  if (!s) return "—";
  try {
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "2-digit" });
  } catch {
    return s;
  }
};

// Margin badge color tier for the Project P&L dashboard: >40% green,
// 20-40% amber, <20% red — shared between ProjectPnL.jsx's table and the
// mini margin chip embedded in Projects.jsx so the two never drift apart.
export const marginTone = (pct) => {
  if (pct > 40) return { text: "text-[var(--moss)]", bg: "bg-[var(--moss-soft)]" };
  if (pct >= 20) return { text: "text-[var(--warn,#B45309)]", bg: "bg-[var(--warn-soft,#FEF3C7)]" };
  return { text: "text-[var(--danger)]", bg: "bg-[var(--danger-soft)]" };
};

// e.g. "25 Aug 2026, 10:30 AM" — used for dated entries like visitor remarks.
export const fmtDateTime = (s) => {
  if (!s) return "—";
  try {
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    const date = d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
    const time = d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
    return `${date}, ${time}`;
  } catch {
    return s;
  }
};
