import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import SearchSelect from "@/components/SearchSelect";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { X, Plus, Trash2, FileText } from "lucide-react";
import { toast } from "sonner";

const STATUSES = ["Draft", "Issued", "Received", "Cancelled"];
// Mirrors models.GST_SLABS — quick-select instead of typing a rate, with 0%
// as the default so a rate is never silently pre-applied.
const GST_SLABS = [0, 5, 12, 18, 28];

const emptyLine = () => ({ sku: "", description: "", hsn: "", qty: 1, rate: 0, discount_pct: 0, tax_pct: 0 });

const lineAmount = (l) =>
  +(((+l.qty || 0) * (+l.rate || 0)) * (1 - (+l.discount_pct || 0) / 100)).toFixed(2);
const lineTax = (l) => +((lineAmount(l) * (+l.tax_pct || 0)) / 100).toFixed(2);

// Mirrors lifecycle.po_totals — each line taxed at its own slab, because one
// PO legitimately mixes HSN codes. The server recomputes these on save; this
// is only so the form can show a running total.
const totalsOf = (lines) => {
  const subtotal = +lines.reduce((a, l) => a + lineAmount(l), 0).toFixed(2);
  const tax = +lines.reduce((a, l) => a + lineTax(l), 0).toFixed(2);
  return { subtotal, tax, grand: +(subtotal + tax).toFixed(2) };
};

async function openPoPdf(po) {
  try {
    // Bearer-token authed, so it must be fetched as a blob — same pattern as
    // the inventory price tag and the quote PDF.
    const { data } = await api.get(`/purchase-orders/${po.id}/pdf`, { skipCache: true, responseType: "blob" });
    const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
    window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch {
    toast.error("Could not generate the purchase order PDF");
  }
}

export default function PurchaseOrders() {
  const [rows, setRows] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [projects, setProjects] = useState([]);
  const [fStatus, setFStatus] = useState("All");
  const [search, setSearch] = useState("");
  const [show, setShow] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [vendorDraft, setVendorDraft] = useState(null);
  const [savingVendor, setSavingVendor] = useState(false);

  const empty = {
    date: new Date().toISOString().slice(0, 10), vendor_id: "", project_id: "",
    payment_terms: "", delivery_address: "", expected_date: "", status: "Draft",
    remarks: "", line_items: [emptyLine()],
  };
  const [form, setForm] = useState(empty);

  const load = () => api.get("/purchase-orders").then(({ data }) => setRows(data)).catch(() => setRows([]));
  useEffect(() => {
    load();
    api.get("/vendors").then(({ data }) => setVendors(data)).catch(() => setVendors([]));
    api.get("/projects").then(({ data }) => setProjects(data)).catch(() => setProjects([]));
  }, []);

  const vendorOptions = useMemo(() => vendors.map((v) => ({
    id: v.id, label: v.name ? `${v.code} — ${v.name}` : v.code, sub: v.code,
  })), [vendors]);

  const projectOptions = useMemo(() => projects.map((p) => ({
    id: p.id, label: p.project_no, sub: p.customer,
  })), [projects]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return rows.filter((r) =>
      (fStatus === "All" || r.status === fStatus) &&
      (!q || (r.po_no || "").toLowerCase().includes(q) ||
        (r.vendor_name || "").toLowerCase().includes(q) ||
        (r.vendor_code || "").toLowerCase().includes(q))
    );
  }, [rows, fStatus, search]);

  const totals = totalsOf(form.line_items || []);

  const openNew = () => { setForm(empty); setEditingId(null); setShow(true); };
  const openEdit = (po) => {
    setForm({
      date: po.date || "", vendor_id: po.vendor_id || "", project_id: po.project_id || "",
      payment_terms: po.payment_terms || "", delivery_address: po.delivery_address || "",
      expected_date: po.expected_date || "", status: po.status || "Draft",
      remarks: po.remarks || "",
      line_items: (po.line_items || []).length ? po.line_items : [emptyLine()],
    });
    setEditingId(po.id);
    setShow(true);
  };

  const setLine = (i, key, value) => setForm((f) => ({
    ...f, line_items: f.line_items.map((l, idx) => (idx === i ? { ...l, [key]: value } : l)),
  }));
  const addLine = () => setForm((f) => ({ ...f, line_items: [...f.line_items, emptyLine()] }));
  const dropLine = (i) => setForm((f) => ({
    ...f, line_items: f.line_items.filter((_, idx) => idx !== i).length
      ? f.line_items.filter((_, idx) => idx !== i) : [emptyLine()],
  }));

  const saveVendor = async () => {
    const name = (vendorDraft?.name || "").trim();
    if (!name) { toast.error("Vendor name is required"); return; }
    setSavingVendor(true);
    try {
      const { data } = await api.post("/vendors", { name });
      setVendors((v) => [data, ...v]);
      setForm((f) => ({ ...f, vendor_id: data.id }));
      setVendorDraft(null);
      toast.success(`Vendor ${data.code} created`);
    } catch (e) {
      toast.error(e?.response?.data?.detail?.toString?.() || "Could not create vendor");
    } finally { setSavingVendor(false); }
  };

  const save = async () => {
    if (saving) return;
    if (!form.vendor_id) { toast.error("Select a vendor"); return; }
    if (!form.line_items.some((l) => (l.description || l.sku) && +l.qty > 0)) {
      toast.error("Add at least one line item"); return;
    }
    setSaving(true);
    try {
      // po_no, vendor_name/code and every total are assigned server-side —
      // deliberately not sent from here.
      if (editingId) await api.put(`/purchase-orders/${editingId}`, form);
      else await api.post("/purchase-orders", form);
      toast.success(editingId ? "Purchase order updated" : "Purchase order created");
      setShow(false); setEditingId(null); setForm(empty); load();
    } catch (e) {
      toast.error(e?.response?.data?.detail?.toString?.() || "Save failed");
    } finally { setSaving(false); }
  };

  const remove = async () => {
    if (!editingId) return;
    if (!window.confirm("Delete this purchase order? This cannot be undone.")) return;
    try {
      await api.delete(`/purchase-orders/${editingId}`);
      toast.success("Purchase order deleted");
      setShow(false); setEditingId(null); load();
    } catch { toast.error("Delete failed"); }
  };

  const grandTotal = filtered.reduce((a, b) => a + (b.grand_total || 0), 0);

  return (
    <>
      <Topbar
        title="Purchase Orders"
        subtitle={`${filtered.length} orders · ${inrFull(grandTotal)}`}
        onAdd={openNew}
        addLabel="New PO"
      />

      <div className="p-6" data-testid="purchase-orders-page">
        <div className="flex flex-wrap gap-2 mb-4">
          <input
            placeholder="Search PO number or vendor…"
            value={search} onChange={(e) => setSearch(e.target.value)}
            className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] w-72"
            data-testid="po-search"
          />
          <select value={fStatus} onChange={(e) => setFStatus(e.target.value)} aria-label="Filter by status"
            className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
            <option>All</option>
            {STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>

        <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">PO #</th>
                  <th className="text-left font-semibold px-4 py-2.5">Date</th>
                  <th className="text-left font-semibold px-4 py-2.5">Vendor</th>
                  <th className="text-left font-semibold px-4 py-2.5">Project</th>
                  <th className="text-right font-semibold px-4 py-2.5">Subtotal</th>
                  <th className="text-right font-semibold px-4 py-2.5">GST</th>
                  <th className="text-right font-semibold px-4 py-2.5">Total</th>
                  <th className="text-left font-semibold px-4 py-2.5">Status</th>
                  <th className="w-12"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((po) => (
                  <tr key={po.id} onClick={() => openEdit(po)}
                    className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50 cursor-pointer"
                    data-testid={`po-${po.id}`}>
                    <td className="px-4 py-3 font-mono text-xs font-semibold">{po.po_no}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{fmtDate(po.date)}</td>
                    <td className="px-4 py-3">{po.vendor_name || po.vendor_code || "—"}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)] text-xs">
                      {projects.find((p) => p.id === po.project_id)?.project_no || "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-mono">{inrFull(po.subtotal)}</td>
                    <td className="px-4 py-3 text-right font-mono text-[var(--ink-2)]">{inrFull(po.tax_total)}</td>
                    <td className="px-4 py-3 text-right font-mono font-semibold">{inrFull(po.grand_total)}</td>
                    <td className="px-4 py-3"><StageBadge stage={po.status} /></td>
                    <td className="px-2 py-3">
                      <button
                        onClick={(e) => { e.stopPropagation(); openPoPdf(po); }}
                        className="p-1.5 rounded-md hover:bg-[var(--surface-2)] text-[var(--ink-3)] hover:text-[var(--brand)]"
                        title="Open PDF" aria-label={`Open PDF for ${po.po_no}`}
                        data-testid={`po-pdf-${po.id}`}
                      >
                        <FileText size={15} strokeWidth={1.8} />
                      </button>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan={9} className="text-center py-12 text-[var(--ink-3)]">No purchase orders yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div className="bg-white rounded-xl border w-full max-w-4xl max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b sticky top-0 bg-white z-10">
              <h3 className="font-heading font-semibold text-lg">
                {editingId ? "Edit Purchase Order" : "New Purchase Order"}
              </h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>

            <div className="p-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Vendor *</label>
                  <SearchSelect
                    options={vendorOptions}
                    value={form.vendor_id}
                    onChange={(id) => setForm({ ...form, vendor_id: id })}
                    placeholder="Search vendor, name or code…"
                    emptyLabel="No vendors found"
                    testId="po-vendor"
                    createLabel="Vendor"
                    onCreate={(term) => setVendorDraft({ name: term })}
                  />
                  {vendorDraft && (
                    <div className="mt-2 p-3 rounded-lg border border-[var(--brand)] bg-[var(--brand-soft)]/30 flex items-end gap-2">
                      <div className="flex-1">
                        <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">New vendor name</label>
                        <input
                          autoFocus value={vendorDraft.name}
                          onChange={(e) => setVendorDraft({ name: e.target.value })}
                          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); saveVendor(); } }}
                          className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]"
                          data-testid="po-vendor-new-name"
                        />
                      </div>
                      <button type="button" className="btn-primary text-xs shrink-0 disabled:opacity-60"
                        onClick={saveVendor} disabled={savingVendor} data-testid="po-vendor-new-save">
                        {savingVendor ? "Saving…" : "Create"}
                      </button>
                      <button type="button" className="btn-ghost text-xs shrink-0" onClick={() => setVendorDraft(null)}>Cancel</button>
                    </div>
                  )}
                </div>
                <div>
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Against project</label>
                  <SearchSelect
                    options={projectOptions}
                    value={form.project_id}
                    onChange={(id) => setForm({ ...form, project_id: id })}
                    placeholder="Not project-linked"
                    emptyLabel="No projects found"
                    testId="po-project"
                  />
                  <div className="text-[11px] text-[var(--ink-3)] mt-1">
                    Linking feeds this order's cost into the project's P&amp;L once it leaves Draft.
                  </div>
                </div>
                <PF l="Date" t="date" v={form.date} oc={(v) => setForm({ ...form, date: v })} />
                <PF l="Expected delivery" t="date" v={form.expected_date} oc={(v) => setForm({ ...form, expected_date: v })} />
                <PF l="Payment terms" v={form.payment_terms} oc={(v) => setForm({ ...form, payment_terms: v })} placeholder="e.g. 50% advance, balance on delivery" />
                <div>
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Status</label>
                  <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm" data-testid="po-status">
                    {STATUSES.map((s) => <option key={s}>{s}</option>)}
                  </select>
                </div>
                <PF l="Delivery address" v={form.delivery_address} oc={(v) => setForm({ ...form, delivery_address: v })} cls="col-span-2" />
              </div>

              {/* Line items */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)]">Line items</label>
                  <button type="button" onClick={addLine} className="btn-ghost text-xs" data-testid="po-add-line">
                    <Plus size={13} /> Add line
                  </button>
                </div>
                <div className="overflow-x-auto border border-[var(--border-light)] rounded-lg">
                  <table className="w-full text-sm">
                    <thead className="bg-[var(--surface-2)]">
                      <tr className="text-[10px] uppercase tracking-wider text-[var(--ink-3)]">
                        <th className="text-left font-semibold px-2 py-2">Description</th>
                        <th className="text-left font-semibold px-2 py-2 w-24">HSN/SAC</th>
                        <th className="text-right font-semibold px-2 py-2 w-16">Qty</th>
                        <th className="text-right font-semibold px-2 py-2 w-24">Rate</th>
                        <th className="text-right font-semibold px-2 py-2 w-16">Disc%</th>
                        <th className="text-left font-semibold px-2 py-2 w-24">GST</th>
                        <th className="text-right font-semibold px-2 py-2 w-24">Amount</th>
                        <th className="w-8"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {form.line_items.map((l, i) => (
                        <tr key={i} className="border-t border-[var(--border-light)]">
                          <td className="p-1"><LineInput v={l.description} oc={(v) => setLine(i, "description", v)} testId={`po-line-desc-${i}`} /></td>
                          <td className="p-1"><LineInput v={l.hsn} oc={(v) => setLine(i, "hsn", v)} testId={`po-line-hsn-${i}`} /></td>
                          <td className="p-1"><LineInput t="number" right v={l.qty} oc={(v) => setLine(i, "qty", parseFloat(v) || 0)} /></td>
                          <td className="p-1"><LineInput t="number" right v={l.rate} oc={(v) => setLine(i, "rate", parseFloat(v) || 0)} /></td>
                          <td className="p-1"><LineInput t="number" right v={l.discount_pct} oc={(v) => setLine(i, "discount_pct", parseFloat(v) || 0)} /></td>
                          <td className="p-1">
                            {/* Quick-select slabs, defaulting to 0% */}
                            <select value={l.tax_pct} onChange={(e) => setLine(i, "tax_pct", parseFloat(e.target.value))}
                              aria-label={`GST slab for line ${i + 1}`}
                              className="w-full px-2 py-1.5 rounded border border-[var(--border)] text-sm"
                              data-testid={`po-line-gst-${i}`}>
                              {GST_SLABS.map((g) => <option key={g} value={g}>{g}%</option>)}
                            </select>
                          </td>
                          <td className="p-1 text-right font-mono text-xs pr-2">{inrFull(lineAmount(l))}</td>
                          <td className="p-1">
                            <button type="button" onClick={() => dropLine(i)}
                              className="p-1 rounded hover:bg-red-50 text-red-600"
                              aria-label={`Remove line ${i + 1}`}>
                              <Trash2 size={13} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="flex justify-end">
                <div className="w-64 text-sm space-y-1">
                  <Row label="Subtotal" value={totals.subtotal} />
                  <Row label="GST" value={totals.tax} />
                  <div className="flex justify-between font-semibold border-t border-[var(--border)] pt-1">
                    <span>Grand total</span>
                    <span className="font-mono" data-testid="po-grand-total">{inrFull(totals.grand)}</span>
                  </div>
                  <div className="text-[10px] text-[var(--ink-3)] pt-1">Recalculated server-side on save.</div>
                </div>
              </div>

              <PF l="Remarks" v={form.remarks} oc={(v) => setForm({ ...form, remarks: v })} cls="col-span-2" />
            </div>

            <div className="px-5 py-4 border-t flex items-center gap-2 sticky bottom-0 bg-white">
              {editingId && <button className="btn-ghost text-red-600 hover:bg-red-50" onClick={remove} data-testid="po-delete">Delete</button>}
              <div className="flex-1" />
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary disabled:opacity-60" onClick={save} disabled={saving} data-testid="po-save">
                {saving ? "Saving…" : editingId ? "Save Changes" : "Create PO"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between text-[var(--ink-2)]">
      <span>{label}</span><span className="font-mono">{inrFull(value)}</span>
    </div>
  );
}

function PF({ l, v, oc, t = "text", cls = "", placeholder = "" }) {
  return (
    <div className={cls}>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <input type={t} value={v} placeholder={placeholder} onChange={(e) => oc(e.target.value)}
        className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" />
    </div>
  );
}

function LineInput({ v, oc, t = "text", right = false, testId }) {
  return (
    <input type={t} value={v} onChange={(e) => oc(e.target.value)} data-testid={testId}
      className={`w-full px-2 py-1.5 rounded border border-[var(--border)] text-sm ${right ? "text-right font-mono" : ""}`} />
  );
}
