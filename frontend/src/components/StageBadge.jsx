// Aura Blue stage-pill mapping: New/Contacted ~ Discovery, Qualified stays
// cobalt, Quoted ~ Proposal (amber), Negotiation ~ Closing (indigo).
const MAP = {
  New: { bg: "bg-blue-100", text: "text-blue-700", dot: "bg-blue-500" },
  Contacted: { bg: "bg-blue-100", text: "text-blue-700", dot: "bg-blue-500" },
  Qualified: { bg: "bg-blue-600", text: "text-white", dot: "bg-white" },
  Quoted: { bg: "bg-amber-100", text: "text-amber-800", dot: "bg-amber-600" },
  Negotiation: { bg: "bg-indigo-900", text: "text-white", dot: "bg-indigo-300" },
  Won: { bg: "bg-[var(--moss-soft)]", text: "text-[var(--moss)]", dot: "bg-[var(--moss)]" },
  Delivered: { bg: "bg-[var(--moss-soft)]", text: "text-[var(--moss)]", dot: "bg-[var(--moss)]" },
  Lost: { bg: "bg-[var(--danger-soft)]", text: "text-[var(--danger)]", dot: "bg-[var(--danger)]" },
  Partial: { bg: "bg-[var(--warn-soft)]", text: "text-[var(--warn)]", dot: "bg-[var(--warn)]" },
  "In Stock": { bg: "bg-[var(--moss-soft)]", text: "text-[var(--moss)]", dot: "bg-[var(--moss)]" },
  Display: { bg: "bg-blue-100", text: "text-blue-700", dot: "bg-blue-500" },
  Sold: { bg: "bg-[var(--surface-2)]", text: "text-[var(--ink-2)]", dot: "bg-[var(--ink-3)]" },
  Missing: { bg: "bg-[var(--danger-soft)]", text: "text-[var(--danger)]", dot: "bg-[var(--danger)]" },
  Reserved: { bg: "bg-[var(--warn-soft)]", text: "text-[var(--warn)]", dot: "bg-[var(--warn)]" },
  Low: { bg: "bg-[var(--surface-2)]", text: "text-[var(--ink-2)]", dot: "bg-[var(--ink-3)]" },
  Medium: { bg: "bg-blue-500", text: "text-white", dot: "bg-white" },
  High: { bg: "bg-orange-600", text: "text-white", dot: "bg-white" },
};

import { memo } from "react";

function StageBadge({ stage }) {
  const m = MAP[stage] || MAP.New;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium ${m.bg} ${m.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${m.dot}`} />
      {stage || "—"}
    </span>
  );
}

export default memo(StageBadge);
