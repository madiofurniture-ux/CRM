import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import api from "@/lib/api";
import { inrFull } from "@/lib/format";
import { Package, Grid3x3, List, X } from "lucide-react";
import { toast } from "sonner";

const STATUSES = ["In Stock", "Display", "Sold", "Missing", "Reserved"];

export default function Inventory() {
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState("");
  const [fStatus, setFStatus] = useState("All");
  const [fCat, setFCat] = useState("All");
  const [view, setView] = useState("grid");
  const [show, setShow] = useState(false);
  const [editingId, setEditingId] = useState(null); // null = creating, else the item id being edited
  const empty = { sku: "", name: "", category: "", vendor: "", model_no: "", qty: 1, cost: 0, mrp: 0, margin: 0, status: "In Stock", location: "Warehouse A", image_url: "" };
  const [form, setForm] = useState(empty);

  const openEdit = (item) => {
    // copy only the editable fields so stray keys (id/created_at) never round-trip into the form
    setForm({
      sku: item.sku || "", name: item.name || "", category: item.category || "",
      vendor: item.vendor || "", model_no: item.model_no || "", qty: item.qty ?? 1,
      cost: item.cost ?? 0, mrp: item.mrp ?? 0, margin: item.margin ?? 0,
      status: item.status || "In Stock", location: item.location || "", image_url: item.image_url || "",
    });
    setEditingId(item.id);
    setShow(true);
  };

  const load = async () => { const { data } = await api.get("/inventory"); setRows(data); };
  useEffect(() => { load(); }, []);

  const categories = useMemo(() => Array.from(new Set(rows.map((r) => r.category).filter(Boolean))).sort(), [rows]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return rows.filter((r) =>
      (fStatus === "All" || r.status === fStatus) &&
      (fCat === "All" || r.category === fCat) &&
      (!q || r.name.toLowerCase().includes(q) || r.sku.toLowerCase().includes(q) || (r.vendor || "").toLowerCase().includes(q))
    );
  }, [rows, search, fStatus, fCat]);

  const totalMrp = filtered.reduce((a, b) => a + (b.mrp || 0) * (b.qty || 0), 0);
  const totalCost = filtered.reduce((a, b) => a + (b.cost || 0) * (b.qty || 0), 0);

  const save = async () => {
    if (!form.sku.trim() || !form.name.trim()) { toast.error("SKU and Name are required"); return; }
    const margin = form.cost > 0 ? +(((form.mrp - form.cost) / form.cost) * 100).toFixed(2) : 0;
    try {
      if (editingId) {
        await api.put(`/inventory/${editingId}`, { ...form, margin });
        toast.success("Item updated");
      } else {
        await api.post("/inventory", { ...form, margin });
        toast.success("Item added");
      }
      setShow(false); setForm(empty); setEditingId(null); load();
    } catch { toast.error("Save failed"); }
  };

  const remove = async () => {
    if (!editingId) return;
    if (!window.confirm(`Delete ${form.sku} — ${form.name}? This cannot be undone.`)) return;
    try {
      await api.delete(`/inventory/${editingId}`);
      toast.success("Item deleted");
      setShow(false); setForm(empty); setEditingId(null); load();
    } catch { toast.error("Delete failed"); }
  };

  return (
    <>
      <Topbar
        title="Inventory"
        subtitle={`${filtered.length} items · MRP ${inrFull(totalMrp)} · Cost ${inrFull(totalCost)}`}
        onAdd={() => { setForm(empty); setEditingId(null); setShow(true); }}
        addLabel="Add Item"
        actions={
          <div className="hidden md:flex items-center bg-[var(--surface-2)] border border-[var(--border)] rounded-lg p-0.5">
            <button onClick={() => setView("grid")} className={`p-1.5 rounded ${view === "grid" ? "bg-white shadow-sm" : ""}`} title="Grid"><Grid3x3 size={15} /></button>
            <button onClick={() => setView("list")} className={`p-1.5 rounded ${view === "list" ? "bg-white shadow-sm" : ""}`} title="List"><List size={15} /></button>
          </div>
        }
      />
      <div className="p-6" data-testid="inventory-page">
        <div className="flex flex-wrap gap-2 mb-4">
          <input placeholder="Search SKU, name, vendor…" value={search} onChange={(e) => setSearch(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] w-72" data-testid="inv-search" />
          <select value={fStatus} onChange={(e) => setFStatus(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
            <option>All</option>
            {STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <select value={fCat} onChange={(e) => setFCat(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
            <option>All</option>
            {categories.map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>

        {view === "grid" ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filtered.map((i) => (
              <div key={i.id} onClick={() => openEdit(i)} role="button" tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openEdit(i); } }}
                className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden hover:shadow-md hover:border-[var(--brand)] transition cursor-pointer" data-testid={`item-${i.id}`}>
                <div className="aspect-[4/3] bg-[var(--surface-2)] flex items-center justify-center relative">
                  {i.image_url ? (
                    <img src={i.image_url} alt="" className="w-full h-full object-cover" />
                  ) : (
                    <Package size={40} className="text-[var(--ink-3)]" strokeWidth={1.2} />
                  )}
                  <span className="absolute top-2 right-2"><StageBadge stage={i.status} /></span>
                </div>
                <div className="p-4">
                  <div className="font-mono text-[10px] text-[var(--ink-3)] mb-1">{i.sku}</div>
                  <div className="font-semibold text-[var(--ink)] text-sm leading-tight mb-2 line-clamp-2">{i.name}</div>
                  <div className="flex items-center justify-between text-xs">
                    <div>
                      <div className="text-[10px] uppercase tracking-wider text-[var(--ink-3)]">MRP</div>
                      <div className="font-mono font-semibold">{inrFull(i.mrp)}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] uppercase tracking-wider text-[var(--ink-3)]">Qty</div>
                      <div className="font-mono font-semibold">{i.qty}</div>
                    </div>
                  </div>
                  <div className="mt-2 pt-2 border-t border-[var(--border-light)] flex items-center justify-between text-[11px] text-[var(--ink-3)]">
                    <span className="truncate">{i.vendor}</span>
                    <span>{i.location}</span>
                  </div>
                </div>
              </div>
            ))}
            {filtered.length === 0 && <div className="col-span-full text-center py-12 text-[var(--ink-3)]">No inventory items</div>}
          </div>
        ) : (
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[var(--surface-2)]">
                  <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                    <th className="text-left font-semibold px-4 py-2.5">SKU</th>
                    <th className="text-left font-semibold px-4 py-2.5">Name</th>
                    <th className="text-left font-semibold px-4 py-2.5">Category</th>
                    <th className="text-left font-semibold px-4 py-2.5">Vendor</th>
                    <th className="text-right font-semibold px-4 py-2.5">Qty</th>
                    <th className="text-right font-semibold px-4 py-2.5">Cost</th>
                    <th className="text-right font-semibold px-4 py-2.5">MRP</th>
                    <th className="text-right font-semibold px-4 py-2.5">Margin</th>
                    <th className="text-left font-semibold px-4 py-2.5">Status</th>
                    <th className="text-left font-semibold px-4 py-2.5">Location</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((i) => (
                    <tr key={i.id} onClick={() => openEdit(i)} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50 cursor-pointer">
                      <td className="px-4 py-3 font-mono text-xs">{i.sku}</td>
                      <td className="px-4 py-3 font-medium">{i.name}</td>
                      <td className="px-4 py-3 text-[var(--ink-2)]">{i.category}</td>
                      <td className="px-4 py-3 text-[var(--ink-2)]">{i.vendor}</td>
                      <td className="px-4 py-3 text-right font-mono">{i.qty}</td>
                      <td className="px-4 py-3 text-right font-mono text-[var(--ink-2)]">{inrFull(i.cost)}</td>
                      <td className="px-4 py-3 text-right font-mono font-semibold">{inrFull(i.mrp)}</td>
                      <td className="px-4 py-3 text-right font-mono text-[var(--moss)]">{i.margin?.toFixed(0)}%</td>
                      <td className="px-4 py-3"><StageBadge stage={i.status} /></td>
                      <td className="px-4 py-3 text-[var(--ink-2)] text-xs">{i.location}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => { setShow(false); setEditingId(null); }}>
          <div className="bg-white rounded-xl border w-full max-w-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">{editingId ? `Edit Item — ${form.sku}` : "Add Item"}</h3>
              <button onClick={() => { setShow(false); setEditingId(null); }} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-4">
              <F l="SKU" v={form.sku} oc={(v) => setForm({ ...form, sku: v })} t2="if-sku" />
              <F l="Name" v={form.name} oc={(v) => setForm({ ...form, name: v })} t2="if-name" />
              <F l="Category" v={form.category} oc={(v) => setForm({ ...form, category: v })} />
              <F l="Vendor" v={form.vendor} oc={(v) => setForm({ ...form, vendor: v })} />
              <F l="Model No" v={form.model_no} oc={(v) => setForm({ ...form, model_no: v })} />
              <F l="Qty" t="number" v={form.qty} oc={(v) => setForm({ ...form, qty: parseInt(v) || 0 })} />
              <F l="Cost" t="number" v={form.cost} oc={(v) => setForm({ ...form, cost: parseFloat(v) || 0 })} />
              <F l="MRP" t="number" v={form.mrp} oc={(v) => setForm({ ...form, mrp: parseFloat(v) || 0 })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Status</label>
                <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">{STATUSES.map((s) => <option key={s}>{s}</option>)}</select>
              </div>
              <F l="Location" v={form.location} oc={(v) => setForm({ ...form, location: v })} />
              <F l="Image URL (Product Picture)" v={form.image_url} oc={(v) => setForm({ ...form, image_url: v })} cls="col-span-2" placeholder="https://images.unsplash.com/..." />
            </div>
            <div className="px-5 py-4 border-t flex items-center gap-2">
              {editingId && (
                <button className="btn-ghost text-red-600 hover:bg-red-50" onClick={remove} data-testid="item-delete">Delete</button>
              )}
              <div className="flex-1" />
              <button className="btn-ghost" onClick={() => { setShow(false); setEditingId(null); }}>Cancel</button>
              <button className="btn-primary" onClick={save} data-testid="item-save">{editingId ? "Save Changes" : "Save"}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
function F({ l, v, oc, t = "text", cls = "", t2, placeholder = "" }) {
  return (
    <div className={cls}>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <input type={t} value={v} placeholder={placeholder} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" data-testid={t2} />
    </div>
  );
}

