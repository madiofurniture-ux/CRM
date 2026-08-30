import { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import api from "@/lib/api";
import { Plus, Trash2, X, Wand2 } from "lucide-react";
import { toast } from "sonner";

const emptyItem = { item: "", qty: 1, w: 0, h: 0, rate: 0, notes: "" };
const empty = {
  lead_id: "", customer: "", phone: "", division: "Furniture", title: "",
  budget: 0, priority: "Medium", site_address: "", notes: "", items: [{ ...emptyItem }],
};

export default function Requirements() {
  const nav = useNavigate();
  const [rows, setRows] = useState([]);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [form, setForm] = useState(empty);

  const load = async () => { const { data } = await api.get("/requirements"); setRows(data); };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => rows, [rows]);

  const openNew = () => { setForm(empty); setShow(true); };

  const setItem = (i, changes) => {
    const items = form.items.map((it, idx) => (idx === i ? { ...it, ...changes } : it));
    setForm({ ...form, items });
  };
  const addItem = () => setForm({ ...form, items: [...form.items, { ...emptyItem }] });
  const removeItem = (i) => setForm({ ...form, items: form.items.filter((_, idx) => idx !== i) });

  const save = async () => {
    if (saving) return;
    if (!form.customer.trim()) { toast.error("Customer is required"); return; }
    setSaving(true);
    try {
      await api.post("/requirements", form);
      toast.success("Requirement captured");
      setShow(false);
      load();
    } catch {
      toast.error("Save failed");
    } finally {
      setSaving(false);
    }
  };

  const configure = async (r) => {
    if (busyId) return;
    setBusyId(r.id);
    try {
      const { data } = await api.post(`/requirements/${r.id}/configure`);
      toast.success("Sent to Configurator");
      nav(`/configurator?config=${data.id}`);
    } catch {
      toast.error("Could not open the configurator");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <Topbar title="Requirements" subtitle={`${filtered.length} captured`} onAdd={openNew} addLabel="New Requirement" />
      <div className="p-6" data-testid="requirements-page">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((r) => (
            <div key={r.id} className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5" data-testid={`req-${r.id}`}>
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="font-heading font-semibold text-[var(--ink)]">{r.customer}</div>
                  <div className="text-xs text-[var(--ink-2)]">{r.title || r.division}</div>
                </div>
                <StageBadge stage={r.status} />
              </div>
              <div className="text-xs text-[var(--ink-3)] mb-3">{(r.items || []).length} item(s) · ₹{Number(r.budget || 0).toLocaleString("en-IN")}</div>
              <button
                onClick={() => configure(r)}
                disabled={busyId === r.id || r.status !== "Open"}
                className="btn-primary w-full justify-center disabled:opacity-50"
                data-testid={`req-configure-${r.id}`}
              >
                <Wand2 size={14} /> {r.status === "Open" ? "Send to Configurator" : r.status}
              </button>
            </div>
          ))}
          {filtered.length === 0 && <div className="col-span-full text-center py-12 text-[var(--ink-3)]">No requirements yet</div>}
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div className="bg-white rounded-xl border w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">New Requirement</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-4">
              <F l="Customer" v={form.customer} oc={(v) => setForm({ ...form, customer: v })} />
              <F l="Phone" v={form.phone} oc={(v) => setForm({ ...form, phone: v })} />
              <F l="Title" v={form.title} oc={(v) => setForm({ ...form, title: v })} />
              <F l="Budget" v={form.budget} oc={(v) => setForm({ ...form, budget: Number(v) || 0 })} type="number" />
              <F l="Site address" v={form.site_address} oc={(v) => setForm({ ...form, site_address: v })} cls="col-span-2" />
              <F l="Notes" v={form.notes} oc={(v) => setForm({ ...form, notes: v })} cls="col-span-2" />
            </div>
            <div className="px-5 pb-2">
              <div className="flex items-center justify-between mb-2">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)]">Items</div>
                <button onClick={addItem} className="btn-ghost text-xs"><Plus size={12} /> Add item</button>
              </div>
              <div className="space-y-2">
                {form.items.map((it, i) => (
                  <div key={i} className="grid grid-cols-6 gap-2 items-center">
                    <input placeholder="Item" value={it.item} onChange={(e) => setItem(i, { item: e.target.value })} className="col-span-2 px-2 py-1.5 rounded-lg border border-[var(--border)] text-sm" />
                    <input placeholder="Qty" type="number" value={it.qty} onChange={(e) => setItem(i, { qty: Number(e.target.value) || 0 })} className="px-2 py-1.5 rounded-lg border border-[var(--border)] text-sm" />
                    <input placeholder="W" type="number" value={it.w} onChange={(e) => setItem(i, { w: Number(e.target.value) || 0 })} className="px-2 py-1.5 rounded-lg border border-[var(--border)] text-sm" />
                    <input placeholder="H" type="number" value={it.h} onChange={(e) => setItem(i, { h: Number(e.target.value) || 0 })} className="px-2 py-1.5 rounded-lg border border-[var(--border)] text-sm" />
                    <button onClick={() => removeItem(i)} className="p-1.5 rounded hover:bg-red-50 text-red-600 justify-self-start"><Trash2 size={13} /></button>
                  </div>
                ))}
              </div>
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary disabled:opacity-60" onClick={save} disabled={saving} data-testid="req-save">
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function F({ l, v, oc, cls = "", type = "text" }) {
  return (
    <div className={cls}>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <input type={type} value={v} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" />
    </div>
  );
}
