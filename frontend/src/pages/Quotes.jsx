import { useEffect, useMemo, useState } from "react";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { Trash2, Edit2, X, Plus, Package, FileCheck, Layers } from "lucide-react";

const DIVISIONS = ["Furniture", "MAP", "D&W"];
const STAGES = ["New", "Qualified", "Quoted", "Negotiation", "Won", "Lost"];

export default function Quotes() {
  const [rows, setRows] = useState([]);
  const [inventory, setInventory] = useState([]);
  const [search, setSearch] = useState("");
  const [fDiv, setFDiv] = useState("All");
  const [fStage, setFStage] = useState("All");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);

  const emptyItem = { sku: "", name: "", division: "Furniture", qty: 1, unit_price: 0, discount_pct: 0, gst_pct: 18, total_amount: 0 };

  const empty = {
    quote_no: "",
    date: new Date().toISOString().slice(0, 10),
    customer: "",
    reference: "",
    phone: "",
    division: "Furniture",
    by_user: "",
    stage: "Quoted",
    value: 0,
    cash: 0,
    bank: 0,
    mode: "Walk-in",
    remarks: "",
    line_items: [],
  };

  const [form, setForm] = useState(empty);

  const loadData = async () => {
    try {
      const [qRes, iRes] = await Promise.all([api.get("/quotes"), api.get("/inventory")]);
      setRows(qRes.data);
      setInventory(iRes.data);
    } catch {
      toast.error("Failed to load quotations");
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filteredInventory = useMemo(() => {
    if (!form.division) return inventory;
    return inventory.filter(
      (item) => item.category?.toLowerCase().includes(form.division.toLowerCase()) || form.division === "Furniture" || !item.category
    );
  }, [inventory, form.division]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return rows.filter(
      (r) =>
        (fDiv === "All" || r.division === fDiv) &&
        (fStage === "All" || r.stage === fStage) &&
        (!q || r.customer.toLowerCase().includes(q) || r.quote_no.toLowerCase().includes(q) || (r.reference || "").toLowerCase().includes(q))
    );
  }, [rows, search, fDiv, fStage]);

  const openNew = () => {
    setEditing(null);
    setForm({
      ...empty,
      quote_no: `AF-${String(rows.length + 1).padStart(4, "0")}`,
      line_items: [],
    });
    setShowForm(true);
  };

  const openEdit = (r) => {
    setEditing(r);
    setForm({ ...r, line_items: r.line_items || [] });
    setShowForm(true);
  };

  const addLineItem = () => {
    setForm((prev) => ({
      ...prev,
      line_items: [...prev.line_items, { ...emptyItem, division: prev.division }],
    }));
  };

  const updateLineItem = (index, field, val) => {
    setForm((prev) => {
      const updated = [...prev.line_items];
      const item = { ...updated[index], [field]: val };

      if (field === "sku") {
        const invMatch = inventory.find((i) => i.sku === val);
        if (invMatch) {
          item.name = invMatch.name;
          item.unit_price = invMatch.mrp || invMatch.cost || 0;
        }
      }

      const base = (item.unit_price || 0) * (item.qty || 1);
      const afterDisc = base * (1 - (item.discount_pct || 0) / 100);
      item.total_amount = afterDisc * (1 + (item.gst_pct || 18) / 100);

      updated[index] = item;

      const grandTotal = updated.reduce((a, b) => a + (b.total_amount || 0), 0);
      return { ...prev, line_items: updated, value: grandTotal };
    });
  };

  const removeLineItem = (index) => {
    setForm((prev) => {
      const updated = prev.line_items.filter((_, i) => i !== index);
      const grandTotal = updated.reduce((a, b) => a + (b.total_amount || 0), 0);
      return { ...prev, line_items: updated, value: grandTotal };
    });
  };

  const save = async () => {
    if (!form.customer || !form.quote_no) {
      toast.error("Customer name and Quote # are required");
      return;
    }
    try {
      if (editing) {
        await api.put(`/quotes/${editing.id}`, form);
        toast.success("Quotation updated");
      } else {
        await api.post("/quotes", form);
        toast.success("Quotation created");
      }
      setShowForm(false);
      loadData();
    } catch {
      toast.error("Save failed");
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this quotation?")) return;
    await api.delete(`/quotes/${id}`);
    toast.success("Deleted");
    loadData();
  };

  const total = filtered.reduce((a, b) => a + (b.value || 0), 0);

  return (
    <>
      <Topbar title="Quotations Engine" subtitle={`${filtered.length} quotes · Total Value ${inrFull(total)}`} onAdd={openNew} addLabel="New Quotation" />

      <div className="p-6" data-testid="quotes-page">
        {/* Filters */}
        <div className="flex flex-wrap gap-2 mb-4">
          <input
            placeholder="Search customer, quote no, reference…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="px-3.5 py-2 rounded-xl bg-white border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] w-72"
            data-testid="quotes-search"
          />
          <select value={fDiv} onChange={(e) => setFDiv(e.target.value)} className="px-3.5 py-2 rounded-xl bg-white border border-[var(--border)] text-sm outline-none">
            <option value="All">All Divisions</option>
            {DIVISIONS.map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
          <select value={fStage} onChange={(e) => setFStage(e.target.value)} className="px-3.5 py-2 rounded-xl bg-white border border-[var(--border)] text-sm outline-none">
            <option value="All">All Stages</option>
            {STAGES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </div>

        {/* Quotes Table */}
        <div className="bg-white border border-[var(--border)] rounded-2xl overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] text-[11px] uppercase tracking-wider text-[var(--ink-3)] border-b border-[var(--border)]">
                <tr>
                  <th className="text-left font-semibold px-4 py-3">Quote #</th>
                  <th className="text-left font-semibold px-4 py-3">Date</th>
                  <th className="text-left font-semibold px-4 py-3">Customer</th>
                  <th className="text-left font-semibold px-4 py-3">Division</th>
                  <th className="text-left font-semibold px-4 py-3">Stage</th>
                  <th className="text-right font-semibold px-4 py-3">Quote Value</th>
                  <th className="text-right font-semibold px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-light)]">
                {filtered.map((r) => (
                  <tr key={r.id} className="hover:bg-[var(--surface-2)]/50 transition">
                    <td className="px-4 py-3 font-mono text-xs font-semibold text-[var(--ink)]">{r.quote_no}</td>
                    <td className="px-4 py-3 font-mono text-xs text-[var(--ink-2)]">{r.date}</td>
                    <td className="px-4 py-3">
                      <div className="font-semibold text-[var(--ink)]">{r.customer}</div>
                      <div className="text-xs text-[var(--ink-3)]">{r.phone || r.reference}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-[var(--brand-light)] text-[var(--brand)]">
                        {r.division}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <StageBadge stage={r.stage} />
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-bold text-[var(--ink)]">{inrFull(r.value)}</td>
                    <td className="px-4 py-3 text-right space-x-1">
                      <button onClick={() => openEdit(r)} className="p-1.5 rounded-lg hover:bg-[var(--surface-2)] text-[var(--ink-2)]" title="Edit">
                        <Edit2 size={15} />
                      </button>
                      <button onClick={() => remove(r.id)} className="p-1.5 rounded-lg hover:bg-red-50 text-red-600" title="Delete">
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={7} className="text-center py-10 text-[var(--ink-3)] text-xs">
                      No quotations found. Click "New Quotation" to build one.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Interactive Quotation Builder Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[var(--border)] w-full max-w-3xl shadow-xl overflow-hidden animate-in fade-in zoom-in duration-150 max-h-[90vh] flex flex-col">
            <div className="px-6 py-4 border-b border-[var(--border)] flex items-center justify-between bg-[var(--surface-2)] shrink-0">
              <div>
                <h3 className="font-heading font-bold text-base text-[var(--ink)]">
                  {editing ? "Edit Quotation" : "Multi-Division Quotation Builder"}
                </h3>
                <p className="text-xs text-[var(--ink-3)]">Linked directly to live stock & pricing catalogue</p>
              </div>
              <button onClick={() => setShowForm(false)} className="p-1 rounded-lg text-[var(--ink-3)] hover:bg-white">
                <X size={18} />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-4">
              {/* Basic Quote Header Information */}
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Quote #</label>
                  <input
                    type="text"
                    required
                    value={form.quote_no}
                    onChange={(e) => setForm({ ...form, quote_no: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] font-mono outline-none focus:border-[var(--brand)]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Customer Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Krishna Reddy"
                    value={form.customer}
                    onChange={(e) => setForm({ ...form, customer: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Division</label>
                  <select
                    value={form.division}
                    onChange={(e) => setForm({ ...form, division: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)] bg-white font-semibold text-[var(--brand)]"
                  >
                    <option value="Furniture">Furniture</option>
                    <option value="MAP">MAP - Premium Architectural Plaster</option>
                    <option value="D&W">Doors & Windows (D&W)</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Phone Number</label>
                  <input
                    type="text"
                    placeholder="9876543210"
                    value={form.phone}
                    onChange={(e) => setForm({ ...form, phone: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Architect / Reference</label>
                  <input
                    type="text"
                    placeholder="Ar Ravindra / Walk-in"
                    value={form.reference}
                    onChange={(e) => setForm({ ...form, reference: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Quote Stage</label>
                  <select
                    value={form.stage}
                    onChange={(e) => setForm({ ...form, stage: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)] bg-white"
                  >
                    {STAGES.map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Line Items Section */}
              <div className="pt-2">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Package size={16} className="text-[var(--brand)]" />
                    <h4 className="font-bold text-sm text-[var(--ink)]">Inventory Line Items</h4>
                  </div>
                  <button
                    type="button"
                    onClick={addLineItem}
                    className="flex items-center gap-1 text-xs font-semibold text-[var(--brand)] bg-[var(--brand-light)] px-3 py-1.5 rounded-lg hover:opacity-90 transition"
                  >
                    <Plus size={14} />
                    Add Product / Stock Item
                  </button>
                </div>

                <div className="space-y-2 border border-[var(--border)] rounded-xl p-3 bg-[var(--surface-2)]">
                  {form.line_items.map((item, idx) => (
                    <div key={idx} className="bg-white p-3 rounded-lg border border-[var(--border-light)] grid grid-cols-12 gap-2 items-center text-xs">
                      {/* SKU / Stock Picker */}
                      <div className="col-span-4">
                        <label className="text-[10px] text-[var(--ink-3)] font-mono uppercase block mb-0.5">Stock Item / SKU</label>
                        <select
                          value={item.sku}
                          onChange={(e) => updateLineItem(idx, "sku", e.target.value)}
                          className="w-full px-2 py-1.5 rounded-md border border-[var(--border)] outline-none text-xs bg-white"
                        >
                          <option value="">Custom Item / Select Stock...</option>
                          {inventory.map((inv) => (
                            <option key={inv.id} value={inv.sku}>
                              {inv.sku} - {inv.name} (MRP ₹{inv.mrp})
                            </option>
                          ))}
                        </select>
                        <input
                          type="text"
                          placeholder="Item description"
                          value={item.name}
                          onChange={(e) => updateLineItem(idx, "name", e.target.value)}
                          className="w-full px-2 py-1 rounded border border-[var(--border-light)] mt-1 text-[11px]"
                        />
                      </div>

                      {/* Unit Price */}
                      <div className="col-span-2">
                        <label className="text-[10px] text-[var(--ink-3)] font-mono uppercase block mb-0.5">Rate (₹)</label>
                        <input
                          type="number"
                          value={item.unit_price}
                          onChange={(e) => updateLineItem(idx, "unit_price", +e.target.value)}
                          className="w-full px-2 py-1.5 rounded-md border border-[var(--border)] font-mono text-xs"
                        />
                      </div>

                      {/* Quantity */}
                      <div className="col-span-2">
                        <label className="text-[10px] text-[var(--ink-3)] font-mono uppercase block mb-0.5">Qty</label>
                        <input
                          type="number"
                          value={item.qty}
                          onChange={(e) => updateLineItem(idx, "qty", +e.target.value)}
                          className="w-full px-2 py-1.5 rounded-md border border-[var(--border)] font-mono text-xs"
                        />
                      </div>

                      {/* Discount % */}
                      <div className="col-span-1">
                        <label className="text-[10px] text-[var(--ink-3)] font-mono uppercase block mb-0.5">Disc %</label>
                        <input
                          type="number"
                          value={item.discount_pct}
                          onChange={(e) => updateLineItem(idx, "discount_pct", +e.target.value)}
                          className="w-full px-2 py-1.5 rounded-md border border-[var(--border)] font-mono text-xs"
                        />
                      </div>

                      {/* Line Amount */}
                      <div className="col-span-2 text-right">
                        <label className="text-[10px] text-[var(--ink-3)] font-mono uppercase block mb-0.5">Incl GST 18%</label>
                        <div className="font-mono font-bold text-[var(--ink)] py-1.5">{inrFull(item.total_amount || 0)}</div>
                      </div>

                      {/* Remove button */}
                      <div className="col-span-1 text-center">
                        <button type="button" onClick={() => removeLineItem(idx)} className="p-1 text-red-500 hover:bg-red-50 rounded">
                          <X size={15} />
                        </button>
                      </div>
                    </div>
                  ))}

                  {form.line_items.length === 0 && (
                    <div className="text-center py-6 text-[var(--ink-3)] text-xs">No items added yet. Click "Add Product" to populate quotation line items.</div>
                  )}
                </div>
              </div>

              {/* Remarks */}
              <div>
                <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Remarks & Terms</label>
                <textarea
                  rows={2}
                  placeholder="e.g. Standard 1 year warranty included. 50% advance."
                  value={form.remarks}
                  onChange={(e) => setForm({ ...form, remarks: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                />
              </div>
            </div>

            {/* Modal Footer with Grand Total */}
            <div className="px-6 py-4 border-t border-[var(--border)] flex items-center justify-between bg-[var(--surface-2)] shrink-0">
              <div>
                <span className="text-[10px] uppercase font-mono tracking-wider text-[var(--ink-3)] block">Calculated Grand Total</span>
                <span className="font-mono text-xl font-bold text-[var(--brand)]">{inrFull(form.value)}</span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="px-4 py-2 text-xs font-semibold rounded-xl border border-[var(--border)] bg-white hover:bg-[var(--surface-2)] transition"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={save}
                  className="px-5 py-2 text-xs font-semibold rounded-xl bg-[var(--brand)] text-white hover:opacity-90 transition shadow-sm"
                >
                  Save Quotation
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
