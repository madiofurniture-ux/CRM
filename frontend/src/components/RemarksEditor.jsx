import { useMemo, useState } from "react";
import { Pencil, Trash2, Plus } from "lucide-react";
import { fmtDate } from "@/lib/format";

// `remarks` is either the legacy plain string or the newer list of dated
// entries ({id, text, at}). Always normalize to a list for editing/display.
export function toRemarksArray(remarks) {
  if (Array.isArray(remarks)) {
    return remarks
      .map((r) => (typeof r === "string" ? { id: r, text: r, at: null } : r))
      .filter((r) => r && String(r.text || "").trim());
  }
  if (typeof remarks === "string" && remarks.trim()) {
    return [{ id: "legacy", text: remarks.trim(), at: null }];
  }
  return [];
}

function newRemarkId() {
  return typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `r-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * Multi-entry, dated remarks: add / inline-edit / delete (with confirm),
 * newest first. Shared by Visitors and Leads.
 *
 * remarks: legacy string or [{id, text, at}]
 * onChange(nextRemarksArray)
 */
export default function RemarksEditor({ remarks, onChange, testPrefix = "remark" }) {
  const [draft, setDraft] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editingText, setEditingText] = useState("");

  const list = useMemo(() => toRemarksArray(remarks), [remarks]);
  const sorted = useMemo(
    () => [...list].sort((a, b) => String(b.at || "").localeCompare(String(a.at || ""))),
    [list]
  );

  const add = () => {
    const text = draft.trim();
    if (!text) return;
    onChange([{ id: newRemarkId(), text, at: new Date().toISOString() }, ...list]);
    setDraft("");
  };
  const startEdit = (r) => { setEditingId(r.id); setEditingText(r.text); };
  const cancelEdit = () => { setEditingId(null); setEditingText(""); };
  const saveEdit = () => {
    const text = editingText.trim();
    if (!text) return;
    onChange(list.map((r) => (r.id === editingId ? { ...r, text } : r)));
    cancelEdit();
  };
  const del = (id) => {
    if (!window.confirm("Delete this remark?")) return;
    onChange(list.filter((r) => r.id !== id));
    if (editingId === id) cancelEdit();
  };

  return (
    <div>
      <div className="flex gap-2 mb-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder="Add a remark…"
          className="flex-1 px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]"
          data-testid={`${testPrefix}-draft`}
        />
        <button type="button" onClick={add} className="btn-ghost shrink-0" data-testid={`${testPrefix}-add`}>
          <Plus size={14} /> Add Remark
        </button>
      </div>
      <div className="max-h-52 overflow-y-auto space-y-2 border border-[var(--border-light)] rounded-lg p-2 bg-[var(--surface-2)]" data-testid={`${testPrefix}-list`}>
        {sorted.length === 0 && <div className="text-xs text-[var(--ink-3)] px-1 py-2">No remarks yet</div>}
        {sorted.map((r, i) => (
          <div key={r.id || i} className="bg-white border border-[var(--border-light)] rounded-md px-3 py-2">
            {editingId === r.id ? (
              <div className="flex gap-2">
                <input
                  autoFocus
                  value={editingText}
                  onChange={(e) => setEditingText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); saveEdit(); } if (e.key === "Escape") cancelEdit(); }}
                  className="flex-1 px-2 py-1 rounded-md border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]"
                  data-testid={`${testPrefix}-edit-input-${r.id}`}
                />
                <button type="button" onClick={saveEdit} className="btn-primary px-2 py-1 text-xs" data-testid={`${testPrefix}-save-${r.id}`}>Save</button>
                <button type="button" onClick={cancelEdit} className="btn-ghost px-2 py-1 text-xs">Cancel</button>
              </div>
            ) : (
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-[11px] text-[var(--ink-3)]">{r.at ? fmtDate(r.at) : "Earlier"}</div>
                  <div className="text-sm text-[var(--ink)] break-words">{r.text}</div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button type="button" onClick={() => startEdit(r)} className="p-1 rounded hover:bg-[var(--surface-2)] text-[var(--ink-2)]" title="Edit remark" data-testid={`${testPrefix}-edit-${r.id}`}><Pencil size={12} /></button>
                  <button type="button" onClick={() => del(r.id)} className="p-1 rounded hover:bg-[var(--danger-soft)] text-[var(--danger)]" title="Delete remark" data-testid={`${testPrefix}-delete-${r.id}`}><Trash2 size={12} /></button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
