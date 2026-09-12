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

// Format a Date as YYYY-MM-DD from its *local* calendar fields. Never use
// `d.toISOString().slice(0, 10)` for this: that renders in UTC, which for
// any timezone ahead of UTC (IST is +5:30) shifts the date back by a day —
// local midnight on the 12th is 18:30 UTC on the 11th. That bug made
// meetings scheduled for "today" render/save under the wrong day.
export const localDateStr = (d) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
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

// Margin badge color tier for the Project P&L dashboard: >45% green,
// 25-45% amber, <25% (including negative) red — shared between
// ProjectPnL.jsx's table and the mini margin chip embedded in Projects.jsx
// so the two never drift apart.
export const marginTone = (pct) => {
  if (pct > 45) return { text: "text-[var(--moss)]", bg: "bg-[var(--moss-soft)]" };
  if (pct >= 25) return { text: "text-[var(--warn,#B45309)]", bg: "bg-[var(--warn-soft,#FEF3C7)]" };
  return { text: "text-[var(--danger)]", bg: "bg-[var(--danger-soft)]" };
};

// e.g. "Today 10:15 AM" / "Yesterday 4:20 PM" / "25 Aug, 10:30 AM" — for
// timelines where the recent entries matter most (lead remarks history).
export const fmtRelativeDateTime = (s) => {
  if (!s) return "";
  try {
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    const time = d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
    // Compare calendar days, not elapsed hours: 11pm -> 1am is "Yesterday".
    const startOfDay = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const days = Math.round((startOfDay(new Date()) - startOfDay(d)) / 86400000);
    if (days === 0) return `Today ${time}`;
    if (days === 1) return `Yesterday ${time}`;
    const date = d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
    return `${date}, ${time}`;
  } catch {
    return s;
  }
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
