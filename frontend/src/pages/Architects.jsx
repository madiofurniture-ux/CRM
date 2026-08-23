import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { Phone, MapPin, Building, X, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";

const TYPES = ["Architect", "Designer", "Builder", "Vendor"];

export default function Architects() {
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState("");
  const [fType, setFType] = useState("All");
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const empty = { name: "", firm: "", type: "Architect", location: "", phone: "", last_contact: new Date().toISOString().slice(0, 10), visited: false, assigned_to: "", remarks: "" };
  const [form, setForm] = useState(empty);

  const load = async () => { const { data } = await api.get("/architects"); setRows(data); };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return rows.filter((r) =>
      (fType === "All" || r.type === fType) &&
      (!q || (r.name || "").toLowerCase().includes(q) || (r.firm || "").toLowerCase().includes(q) || (r.location || "").toLowerCase().includes(q))
    );
  }, [rows, search, fType]);

  const openNew = () => { setEditing(null); setForm(empty); setShow(true); };
  const openEdit = (a) => { setEditing(a); setForm({ ...empty, ...a }); setShow(true); };

  const save = async () => {
    if (saving) return;
    if (!form.name.trim()) { toast.error("Name is required"); return; }
    setSaving(true);
    try {
      if (editing) {
        await api.put(`/architects/${editing.id}`, form);
        toast.success("Contact updated");
      } else {
        await api.post("/architects", form);
        toast.success("Contact added");
      }
      setShow(false);
      load();
    } catch {
      toast.error("Save failed");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (a) => {
    if (!window.confirm(`Delete contact "${a.name}"?`)) return;
    try {
      await api.delete(`/architects/${a.id}`);
      toast.success("Contact deleted");
      load();
    } catch {
      toast.error("Delete failed");
    }
  };

  return (
    <>
      <Topbar title="Architects & Designers" subtitle={`${filtered.length} contacts`} onAdd={openNew} addLabel="Add Contact" />
      <div className="p-6" data-testid="architects-page">
        <div className="flex flex-wrap gap-2 mb-4">
          <input placeholder="Search name, firm, location…" value={search} onChange={(e) => setSearch(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] w-72" />
          <select value={fType} onChange={(e) => setFType(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
            <option>All</option>
            {TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((a) => (
            <div key={a.id} className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 hover:shadow-md transition" data-testid={`arch-${a.id}`}>
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="font-heading font-semibold text-[var(--ink)]">{a.name}</div>
                  {a.firm && <div className="text-xs text-[var(--ink-2)] flex items-center gap-1 mt-0.5"><Building size={11} />{a.firm}</div>}
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--brand-soft)] text-[var(--brand)] font-semibold uppercase tracking-wider">{a.type}</span>
                  <button
                    onClick={() => openEdit(a)}
                    className="p-1 rounded hover:bg-[var(--surface-2)] text-[var(--ink-2)]"
                    title="Edit contact"
                    data-testid={`arch-edit-${a.id}`}
                  >
                    <Pencil size={13} />
                  </button>
                  <button
                    onClick={() => remove(a)}
                    className="p-1 rounded hover:bg-red-50 text-red-600"
                    title="Delete contact"
                    data-testid={`arch-delete-${a.id}`}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
              <div className="space-y-1.5 text-xs text-[var(--ink-2)]">
                {a.location && <div className="flex items-center gap-1.5"><MapPin size={12} className="text-[var(--ink-3)]" />{a.location}</div>}
                {a.phone && <div className="flex items-center gap-1.5 font-mono"><Phone size={12} className="text-[var(--ink-3)]" />{a.phone}</div>}
              </div>
              <div className="mt-3 pt-3 border-t border-[var(--border-light)] flex items-center justify-between text-[11px] text-[var(--ink-3)]">
                <span>Last: {fmtDate(a.last_contact)}</span>
                <span>{a.assigned_to}</span>
              </div>
            </div>
          ))}
          {filtered.length === 0 && <div className="col-span-full text-center py-12 text-[var(--ink-3)]">No contacts</div>}
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div className="bg-white rounded-xl border w-full max-w-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">{editing ? "Edit Contact" : "Add Contact"}</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-4">
              <F l="Name" v={form.name} oc={(v) => setForm({ ...form, name: v })} t2="af-name" />
              <F l="Firm" v={form.firm} oc={(v) => setForm({ ...form, firm: v })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Type</label>
                <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">{TYPES.map((t) => <option key={t}>{t}</option>)}</select>
              </div>
              <F l="Location" v={form.location} oc={(v) => setForm({ ...form, location: v })} />
              <F l="Phone" v={form.phone} oc={(v) => setForm({ ...form, phone: v })} />
              <F l="Assigned to" v={form.assigned_to} oc={(v) => setForm({ ...form, assigned_to: v })} />
              <F l="Remarks" v={form.remarks} oc={(v) => setForm({ ...form, remarks: v })} cls="col-span-2" />
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary disabled:opacity-60" onClick={save} disabled={saving} data-testid="arch-save">
                {saving ? "Saving…" : editing ? "Save Changes" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
function F({ l, v, oc, cls = "", t2 }) {
  return (
    <div className={cls}>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <input value={v} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" data-testid={t2} />
    </div>
  );
}
