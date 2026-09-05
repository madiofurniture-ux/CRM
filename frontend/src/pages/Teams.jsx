import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { X, Pencil, Trash2 } from "lucide-react";

export default function Teams() {
  const [rows, setRows] = useState([]);
  const [users, setUsers] = useState([]);
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(null);
  const empty = { name: "", description: "", active: true };
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);

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

  return (
    <>
      <Topbar title="Teams" subtitle={`${rows.length} teams`} onAdd={openNew} addLabel="New Team" />
      <div className="p-6" data-testid="teams-page">
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="px-4 py-2.5">Name</th>
                  <th className="px-4 py-2.5">Description</th>
                  <th className="px-4 py-2.5">Members</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {rows.map((t) => (
                  <tr key={t.id} className="border-t border-[var(--border-light)]" data-testid={`team-${t.id}`}>
                    <td className="px-4 py-3 font-medium">{t.name}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{t.description}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{memberCount(t.id)}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${t.active ? "bg-[var(--moss-soft)] text-[var(--moss)]" : "bg-[var(--surface-2)] text-[var(--ink-3)]"}`}>
                        {t.active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right flex justify-end gap-1">
                      <button onClick={() => openEdit(t)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]"><Pencil size={13} /></button>
                      <button onClick={() => remove(t)} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button>
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && <tr><td colSpan="5" className="text-center py-10 text-[var(--ink-3)]">No teams yet</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div className="bg-white rounded-xl border border-[var(--border)] w-full max-w-md shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">{editing ? "Edit Team" : "New Team"}</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Name *</label>
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Sales" className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" />
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Description</label>
                <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" />
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
