import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Save, Plus, Trash2 } from "lucide-react";

// The only modules the backend actually enforces this matrix against today
// (server.py's make_crud module= calls) — matches AuthContext's GATED_MODULES.
const MODULES = [
  "leads", "customers", "quotes", "sales", "inventory",
  "visitors", "architects", "tasks", "invoice-gen", "meetplan", "petty", "requirements",
  "commissions",
];
const ACTIONS = ["view", "create", "edit", "delete", "approve", "export"];
const SCOPES = ["own", "team", "all"];

function emptyPerm(module) {
  return { module, view: false, create: false, edit: false, delete: false, approve: false, export: false, scope: "own" };
}

export default function RolesPermissions() {
  const [roles, setRoles] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [perms, setPerms] = useState([]);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const load = async () => {
    const { data } = await api.get("/roles");
    setRoles(data);
    if (!selectedId && data.length) select(data[0]);
  };
  useEffect(() => { load(); }, []); // eslint-disable-line

  const select = (role) => {
    setSelectedId(role.id);
    setName(role.name);
    setPerms(MODULES.map((m) => role.permissions.find((p) => p.module === m) || emptyPerm(m)));
  };

  const toggle = (module, field) => setPerms((p) => p.map((row) =>
    row.module === module ? { ...row, [field]: field === "scope" ? row.scope : !row[field] } : row));
  const setScope = (module, scope) => setPerms((p) => p.map((row) => row.module === module ? { ...row, scope } : row));

  const save = async () => {
    if (!selectedId || saving) return;
    setSaving(true);
    try {
      await api.put(`/roles/${selectedId}`, { name, permissions: perms.filter((p) => ACTIONS.some((a) => p[a])) });
      toast.success("Role saved");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const createRole = async () => {
    if (!newName.trim() || creating) return;
    setCreating(true);
    try {
      const { data } = await api.post("/roles", { name: newName.trim(), permissions: [] });
      toast.success("Role created");
      setNewName("");
      await load();
      select(data);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setCreating(false); }
  };

  const removeRole = async (role) => {
    if (!window.confirm(`Delete role "${role.name}"? Users with this role keep it assigned but it will grant nothing.`)) return;
    try {
      await api.delete(`/roles/${role.id}`);
      toast.success("Role deleted");
      setSelectedId(null);
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <>
      <Topbar title="Roles & Permissions" subtitle="Module access, per role" />
      <div className="p-6 grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-6" data-testid="roles-permissions-page">
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-3 space-y-1 h-fit">
          {roles.map((r) => (
            <button key={r.id} onClick={() => select(r)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center justify-between group ${selectedId === r.id ? "bg-[var(--brand-soft)] text-[var(--brand)] font-semibold" : "hover:bg-[var(--surface-hover)]"}`}
              data-testid={`role-${r.id}`}>
              {r.name}
              <Trash2 size={12} className="opacity-0 group-hover:opacity-60 hover:!opacity-100" onClick={(e) => { e.stopPropagation(); removeRole(r); }} />
            </button>
          ))}
          <div className="flex gap-1 pt-2 border-t border-[var(--border-light)] mt-2">
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="New role…" className="flex-1 min-w-0 px-2 py-1.5 rounded-md border border-[var(--border)] text-xs" />
            <button onClick={createRole} disabled={creating} className="p-1.5 rounded-md bg-[var(--brand)] text-white disabled:opacity-50"><Plus size={13} /></button>
          </div>
        </div>

        {selectedId && (
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
            <div className="mb-4">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Role Name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} className="px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)] w-64" />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                    <th className="py-2 pr-3">Module</th>
                    {ACTIONS.map((a) => <th key={a} className="py-2 px-2 text-center capitalize">{a}</th>)}
                    <th className="py-2 pl-3">Scope</th>
                  </tr>
                </thead>
                <tbody>
                  {perms.map((row) => (
                    <tr key={row.module} className="border-t border-[var(--border-light)]">
                      <td className="py-2 pr-3 font-medium capitalize">{row.module}</td>
                      {ACTIONS.map((a) => (
                        <td key={a} className="py-2 px-2 text-center">
                          <input type="checkbox" checked={row[a]} onChange={() => toggle(row.module, a)} className="accent-[var(--brand)]" data-testid={`perm-${row.module}-${a}`} />
                        </td>
                      ))}
                      <td className="py-2 pl-3">
                        <select value={row.scope} onChange={(e) => setScope(row.module, e.target.value)} className="px-2 py-1 rounded-md border border-[var(--border)] bg-white text-xs">
                          {SCOPES.map((s) => <option key={s} value={s}>{s}</option>)}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button onClick={save} disabled={saving} className="btn-primary mt-4 disabled:opacity-60" data-testid="roles-save">
              <Save size={14} /> {saving ? "Saving…" : "Save"}
            </button>
          </div>
        )}
      </div>
    </>
  );
}
