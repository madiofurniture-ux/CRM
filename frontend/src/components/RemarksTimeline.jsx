import { useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { fmtRelativeDateTime } from "@/lib/format";

// Two initials max, e.g. "Priya Nair" -> "PN". A legacy entry has no recorded
// author (see normalize_remarks_history server-side) — show a neutral dot
// rather than guessing who wrote it.
const initials = (name) => {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "·";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
};

/**
 * Append-only remarks history for a Lead: [{id, text, created_at, author_name}].
 *
 * Deliberately not RemarksEditor (used by Visitors) — that one is an editable
 * {id, text, at} list with no author. This is an audit trail: entries are
 * added, never edited or deleted, and each records who wrote it.
 *
 * Entries are appended in memory and persisted with the parent form's save,
 * so adding one never closes or resets the modal around it.
 */
export default function RemarksTimeline({ entries, onAdd, authorName = "", testPrefix = "lf-remark" }) {
  const [draft, setDraft] = useState("");

  const list = useMemo(() => (Array.isArray(entries) ? entries : []), [entries]);
  const sorted = useMemo(
    () => [...list].sort((a, b) => String(a.created_at || "").localeCompare(String(b.created_at || ""))),
    [list]
  );

  const add = () => {
    const text = draft.trim();
    if (!text) return;
    // id/created_at/author_name are re-stamped server-side on save; these are
    // only so the entry can render and key itself before that round-trip.
    onAdd({
      id: typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `r-${Date.now()}`,
      text,
      created_at: new Date().toISOString(),
      author_name: authorName,
    });
    setDraft("");
  };

  return (
    <div>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Remarks</label>
      <div
        className="max-h-44 overflow-y-auto space-y-2 border border-[var(--border-light)] rounded-lg p-2 bg-[var(--surface-2)] mb-2"
        data-testid={`${testPrefix}-list`}
      >
        {sorted.length === 0 && <div className="text-xs text-[var(--ink-3)] px-1 py-2">No remarks yet</div>}
        {sorted.map((r, i) => (
          <div key={r.id || i} className="flex items-start gap-2">
            <span
              className="shrink-0 mt-0.5 w-6 h-6 rounded-full bg-[var(--brand-soft)] text-[var(--brand)] text-[10px] font-semibold flex items-center justify-center"
              title={r.author_name || "Unknown author"}
            >
              {initials(r.author_name)}
            </span>
            <div className="min-w-0 flex-1 bg-white border border-[var(--border-light)] rounded-lg px-3 py-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[11px] font-medium text-[var(--ink-2)] truncate">{r.author_name || "—"}</span>
                <span className="text-[10px] text-[var(--ink-3)] shrink-0">{fmtRelativeDateTime(r.created_at)}</span>
              </div>
              <div className="text-sm text-[var(--ink)] break-words whitespace-pre-wrap">{r.text}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder="Add a new remark…"
          className="flex-1 px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]"
          data-testid={`${testPrefix}-draft`}
        />
        <button type="button" onClick={add} disabled={!draft.trim()} className="btn-ghost shrink-0 disabled:opacity-50" data-testid={`${testPrefix}-add`}>
          <Plus size={14} /> Add
        </button>
      </div>
    </div>
  );
}
