const MAP = {
  New: { bg: "bg-[var(--surface-2)]", text: "text-[var(--ink-2)]", dot: "bg-[var(--ink-3)]" },
  Contacted: { bg: "bg-blue-50", text: "text-blue-700", dot: "bg-blue-500" },
  Qualified: { bg: "bg-[var(--moss-soft)]", text: "text-[var(--moss)]", dot: "bg-[var(--moss)]" },
  Quoted: { bg: "bg-[var(--warn-soft)]", text: "text-[var(--warn)]", dot: "bg-[var(--warn)]" },
  Negotiation: { bg: "bg-[var(--brand-soft)]", text: "text-[var(--brand)]", dot: "bg-[var(--brand)]" },
  Won: { bg: "bg-[var(--moss-soft)]", text: "text-[var(--moss)]", dot: "bg-[var(--moss)]" },
  Delivered: { bg: "bg-[var(--moss-soft)]", text: "text-[var(--moss)]", dot: "bg-[var(--moss)]" },
  Lost: { bg: "bg-[var(--danger-soft)]", text: "text-[var(--danger)]", dot: "bg-[var(--danger)]" },
  Partial: { bg: "bg-[var(--warn-soft)]", text: "text-[var(--warn)]", dot: "bg-[var(--warn)]" },
  "In Stock": { bg: "bg-[var(--moss-soft)]", text: "text-[var(--moss)]", dot: "bg-[var(--moss)]" },
  Display: { bg: "bg-blue-50", text: "text-blue-700", dot: "bg-blue-500" },
  Sold: { bg: "bg-[var(--surface-2)]", text: "text-[var(--ink-2)]", dot: "bg-[var(--ink-3)]" },
  Missing: { bg: "bg-[var(--danger-soft)]", text: "text-[var(--danger)]", dot: "bg-[var(--danger)]" },
  Reserved: { bg: "bg-[var(--warn-soft)]", text: "text-[var(--warn)]", dot: "bg-[var(--warn)]" },
  Low: { bg: "bg-[var(--surface-2)]", text: "text-[var(--ink-2)]", dot: "bg-[var(--ink-3)]" },
  Medium: { bg: "bg-[var(--warn-soft)]", text: "text-[var(--warn)]", dot: "bg-[var(--warn)]" },
  High: { bg: "bg-[var(--danger-soft)]", text: "text-[var(--danger)]", dot: "bg-[var(--danger)]" },
  // Quote sales-status axis
  Draft: { bg: "bg-[var(--surface-2)]", text: "text-[var(--ink-2)]", dot: "bg-[var(--ink-3)]" },
  Sent: { bg: "bg-[var(--warn-soft)]", text: "text-[var(--warn)]", dot: "bg-[var(--warn)]" },
  Expired: { bg: "bg-blue-50", text: "text-blue-700", dot: "bg-blue-500" },
  // Ops stages seen on quotes / sales
  "Adv Received": { bg: "bg-[var(--moss-soft)]", text: "text-[var(--moss)]", dot: "bg-[var(--moss)]" },
  "Design & Lock": { bg: "bg-[var(--moss-soft)]", text: "text-[var(--moss)]", dot: "bg-[var(--moss)]" },
  "Site Not Ready": { bg: "bg-[var(--warn-soft)]", text: "text-[var(--warn)]", dot: "bg-[var(--warn)]" },
  Rescheduled: { bg: "bg-[var(--warn-soft)]", text: "text-[var(--warn)]", dot: "bg-[var(--warn)]" },
  Cancelled: { bg: "bg-[var(--danger-soft)]", text: "text-[var(--danger)]", dot: "bg-[var(--danger)]" },
  Confirmed: { bg: "bg-blue-50", text: "text-blue-700", dot: "bg-blue-500" },
  "Payment Received": { bg: "bg-[var(--moss-soft)]", text: "text-[var(--moss)]", dot: "bg-[var(--moss)]" },
  // Lead stages
  "Follow-Up": { bg: "bg-blue-50", text: "text-blue-700", dot: "bg-blue-500" },
  Dormant: { bg: "bg-[var(--surface-2)]", text: "text-[var(--ink-2)]", dot: "bg-[var(--ink-3)]" },
  Converted: { bg: "bg-[var(--moss-soft)]", text: "text-[var(--moss)]", dot: "bg-[var(--moss)]" },
};

export default function StageBadge({ stage }) {
  const m = MAP[stage] || MAP.New;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium ${m.bg} ${m.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${m.dot}`} />
      {stage || "—"}
    </span>
  );
}
