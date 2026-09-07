import { useEffect, useRef, useState } from "react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { X, Pencil, Trash2, Search, Users as UsersIcon } from "lucide-react";

export default function Teams() {
  const [rows, setRows] = useState([]);
  const [users, setUsers] = useState([]);
  const [q, setQ] = useState("");
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(null);
  const empty = { name: "", description: "", active: true };
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);
  const previousFocusRef = useRef(null);

  useEffect(() => {
    if (show) previousFocusRef.current = document.activeElement;
    else previousFocusRef.current?.focus?.();
  }, [show]);

  const load = async () => {
    const { data } = await api.get("/teams");
    setRows(data);
    const { data: u } = await api.get("/users/directory");
    setUsers(u);
  };
  useEffect(() => { load(); }, []);

  const openNew = () => { setEditing(null); setForm(empty); setShow(true); };
  const openEdit = (t) => { setEditing(t); setForm({ name: t.name, description: t.description || "", active: t.active }); setShow(true); };

  const save = async () => {
    if (saving || !form.name.trim()) return;
    setSaving(true);
    try {
      if (editing) await api.put(`/teams/${editing.id}`, form);
      else await api.post("/teams", form);
      toast.success(editing ? "Team updated" : "Team created");
      setShow(false);
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const remove = async (t) => {
    if (!window.confirm(`Delete team "${t.name}"?`)) return;
    try { await api.delete(`/teams/${t.id}`); toast.success("Team deleted"); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const memberCount = (teamId) => users.filter((u) => u.team_id === teamId).length;
  const initials = (name) => name.trim().slice(0, 2).toUpperCase();
  const activeCount = rows.filter((t) => t.active).length;
  const visible = rows.filter((t) => t.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <Topbar title="Teams" subtitle={`${rows.length} teams`} onAdd={openNew} addLabel="Invite Teammate" />
      <div className="p-6 space-y-6" data-testid="teams-page">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-4">
            <div className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)]">Active Teams</div>
            <div className="font-heading font-bold text-2xl text-[var(--ink)] mt-1">{activeCount}</div>
          </div>
          <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-4">
            <div className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)]">Clear Access</div>
            <div className="text-sm text-[var(--ink-2)] mt-1">Every teammate sees exactly what their role grants — no guesswork.</div>
          </div>
          <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-4">
            <div className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)]">Shared Ownership</div>
            <div className="text-sm text-[var(--ink-2)] mt-1">Teams keep accounts, deals, and follow-ups visible to the whole group.</div>
          </div>
        </div>

        <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-5">
          <div className="flex items-center justify-between gap-3 mb-4">
            <h2 className="font-heading font-bold text-[var(--ink)] tracking-tight">Roles and access</h2>
            <div className="relative w-56">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-3)]" />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search teams…"
                className="w-full pl-8 pr-3 py-1.5 rounded-full border border-[var(--border)] bg-[var(--surface-2)] text-sm outline-none focus:border-[var(--brand)]" />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {visible.map((t) => (
              <div key={t.id} className="flex items-start gap-3 border border-[var(--border)] rounded-2xl p-4" data-testid={`team-${t.id}`}>
                <div className="w-11 h-11 rounded-full bg-[var(--brand)] flex items-center justify-center text-white font-heading font-bold text-sm shrink-0">
                  {initials(t.name)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <div className="font-heading font-semibold text-[var(--ink)] truncate">{t.name}</div>
                    <span className={`shrink-0 text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full ${t.active ? "bg-blue-600 text-white" : "bg-[var(--surface-2)] text-[var(--ink-3)]"}`}>
                      {t.active ? "Active" : "Inactive"}
                    </span>
                  </div>
                  {t.description && <div className="text-sm text-[var(--ink-2)] mt-0.5">{t.description}</div>}
                  <div className="flex items-center gap-1 text-xs text-[var(--ink-3)] mt-1.5">
                    <UsersIcon size={12} /> {memberCount(t.id)} member{memberCount(t.id) === 1 ? "" : "s"}
                  </div>
                </div>
                <div className="flex gap-1 shrink-0">
                  <button onClick={() => openEdit(t)} aria-label={`Edit ${t.name}`} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]"><Pencil size={13} /></button>
                  <button onClick={() => remove(t)} aria-label={`Delete ${t.name}`} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button>
                </div>
              </div>
            ))}
            {visible.length === 0 && <div className="col-span-2 text-center py-10 text-[var(--ink-3)]">No teams found</div>}
          </div>
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)} onKeyDown={(e) => e.key === "Escape" && setShow(false)}>
          <div role="dialog" aria-modal="true" aria-labelledby="team-modal-title" className="bg-white rounded-xl border border-[var(--border)] w-full max-w-md shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 id="team-modal-title" className="font-heading font-semibold text-lg">{editing ? "Edit Team" : "New Team"}</h3>
              <button onClick={() => setShow(false)} aria-label="Close" className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label htmlFor="team-name" className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">
                  Name <span aria-hidden="true">*</span>
                </label>
                <input id="team-name" required aria-required="true" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Sales" className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" />
              </div>
              <div>
                <label htmlFor="team-description" className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Description</label>
                <input id="team-description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} className="accent-[var(--brand)]" />
                Active
              </label>
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary disabled:opacity-60" onClick={save} disabled={saving} data-testid="team-save">{saving ? "Saving…" : editing ? "Save Changes" : "Create Team"}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
