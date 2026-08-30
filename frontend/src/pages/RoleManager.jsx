import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Shield, Trash2, X, Plus } from "lucide-react";

const ALL_PAGES = [
  { id: "dashboard", label: "Dashboard" },
  { id: "pipeline", label: "Pipeline" },
  { id: "quotes", label: "Quotations" },
  { id: "sales", label: "Sales" },
  { id: "visitors", label: "Visitors" },
  { id: "leads", label: "Leads" },
  { id: "architects", label: "Architects" },
  { id: "inventory", label: "Inventory" },
  { id: "inv-analytics", label: "Inventory Analytics" },
  { id: "tasks", label: "Tasks" },
];

const COLORS = ["#C85A32", "#4A5D4E", "#D48B30", "#B24040", "#1A1D1A", "#5C7AA1"];

export default function RoleManager() {
  const { user: me, tenant } = useAuth();
  const [users, setUsers] = useState([]);
  const [show, setShow] = useState(false);
  // A disabled module can't be granted to anyone — no point offering it here.
  const pages = tenant?.enabled_modules
    ? ALL_PAGES.filter((p) => tenant.enabled_modules.includes(p.id))
    : ALL_PAGES;
  const empty = { username: "", name: "", pin: "", role: "user", icon: "U", color: "#C85A32", pages: pages.map((p) => p.id) };
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = async () => { const { data } = await api.get("/auth/users"); setUsers(data); };
  useEffect(() => { load(); }, []);

  const openNew = () => { setEditing(null); setForm(empty); setShow(true); };
  const openEdit = (u) => {
    setEditing(u);
    setForm({ username: u.username, name: u.name, pin: "", role: u.role, icon: u.icon, color: u.color, pages: u.pages ?? pages.map((p) => p.id) });
    setShow(true);
  };

  const togglePage = (id) => {
    setForm((f) => ({ ...f, pages: f.pages.includes(id) ? f.pages.filter((x) => x !== id) : [...f.pages, id] }));
  };

  const save = async () => {
    if (saving) return;
    setSaving(true);
    try {
      if (editing) {
        const payload = { name: form.name, role: form.role, icon: form.icon, color: form.color, pages: form.role === "admin" ? null : form.pages };
        if (form.pin) payload.pin = form.pin;
        await api.put(`/auth/users/${editing.id}`, payload);
        toast.success("User updated");
      } else {
        if (!/^\d{4,}$/.test(form.pin)) { toast.error("PIN must be 4+ digits"); return; }
        await api.post("/auth/users", { ...form, pages: form.role === "admin" ? null : form.pages });
        toast.success("User created");
      }
      setShow(false);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (u) => {
    if (u.id === me.id) { toast.error("Can't delete yourself"); return; }
    if (!window.confirm(`Delete user "${u.name}"?`)) return;
    await api.delete(`/auth/users/${u.id}`);
    toast.success("Deleted");
    load();
  };

  return (
    <>
      <Topbar title="Role Manager" subtitle="Manage who can access what" onAdd={openNew} addLabel="Add User" />
      <div className="p-6" data-testid="roles-page">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {users.map((u) => (
            <div key={u.id} className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5" data-testid={`user-${u.id}`}>
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl flex items-center justify-center text-white font-heading font-bold" style={{ background: u.color }}>{u.icon}</div>
                  <div>
                    <div className="font-heading font-semibold text-[var(--ink)]">{u.name}</div>
                    <div className="text-xs font-mono text-[var(--ink-3)]">@{u.username}</div>
                  </div>
                </div>
                {u.role === "admin" && (
                  <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider font-bold text-[var(--brand)]">
                    <Shield size={11} /> Admin
                  </span>
                )}
              </div>
              <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-2">Pages</div>
              <div className="flex flex-wrap gap-1">
                {u.pages == null ? (
                  <span className="text-xs px-2 py-1 rounded bg-[var(--brand-soft)] text-[var(--brand)] font-medium">All pages</span>
                ) : (
                  u.pages.map((p) => (
                    <span key={p} className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--surface-2)] text-[var(--ink-2)] font-medium">{p}</span>
                  ))
                )}
              </div>
              <div className="mt-4 pt-3 border-t border-[var(--border-light)] flex gap-2">
                <button onClick={() => openEdit(u)} className="btn-ghost text-xs flex-1" data-testid={`edit-${u.id}`}>Edit</button>
                <button onClick={() => remove(u)} className="p-2 rounded-lg hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div className="bg-white rounded-xl border w-full max-w-xl max-h-[85vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">{editing ? "Edit User" : "Add User"}</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-4 overflow-y-auto">
              <F l="Username" v={form.username} oc={(v) => setForm({ ...form, username: v })} disabled={!!editing} t2="ru-username" />
              <F l="Full name" v={form.name} oc={(v) => setForm({ ...form, name: v })} t2="ru-name" />
              <F l={editing ? "New PIN (leave blank to keep)" : "PIN (4 digits)"} v={form.pin} oc={(v) => setForm({ ...form, pin: v })} t="password" t2="ru-pin" />
              <F l="Avatar label (2 chars)" v={form.icon} oc={(v) => setForm({ ...form, icon: v.slice(0, 2).toUpperCase() })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Role</label>
                <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Color</label>
                <div className="flex gap-2">
                  {COLORS.map((c) => (
                    <button key={c} onClick={() => setForm({ ...form, color: c })} className={`w-7 h-7 rounded-md ${form.color === c ? "ring-2 ring-offset-2 ring-[var(--ink)]" : ""}`} style={{ background: c }} />
                  ))}
                </div>
              </div>
              {form.role !== "admin" && (
                <div className="col-span-2">
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-2">Page access</label>
                  <div className="grid grid-cols-2 gap-2">
                    {pages.map((p) => (
                      <label key={p.id} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-[var(--border)] cursor-pointer hover:bg-[var(--surface-2)] text-sm">
                        <input type="checkbox" checked={form.pages.includes(p.id)} onChange={() => togglePage(p.id)} className="accent-[var(--brand)]" />
                        {p.label}
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary disabled:opacity-60" onClick={save} disabled={saving} data-testid="ru-save">{saving ? "Saving…" : editing ? "Save" : "Create"}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
function F({ l, v, oc, t = "text", disabled, t2 }) {
  return (
    <div>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <input disabled={disabled} type={t} value={v} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)] disabled:bg-[var(--surface-2)] disabled:text-[var(--ink-3)]" data-testid={t2} />
    </div>
  );
}
