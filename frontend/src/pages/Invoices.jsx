import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import api from "@/lib/api";
import { GST_DEFAULT, GST_SLABS } from "@/lib/constants";
import { inrFull, fmtDate, amountInWords, todayIST } from "@/lib/format";
import { toast } from "sonner";
import CustomerProjectPicker from "@/components/CustomerProjectPicker";
import ColumnFilters from "@/components/ColumnFilters";
import useColumnFilters from "@/hooks/useColumnFilters";

const COLUMNS = [
  { key: "invoice_no", label: "Invoice no", type: "text" },
  { key: "customer", label: "Customer", type: "text" },
  { key: "date", label: "Date", type: "date" },
  { key: "due_date", label: "Due", type: "date" },
  { key: "status", label: "Status", type: "select" },
  { key: "division", label: "Division", type: "select" },
  { key: "source", label: "Source", type: "select" },
  { key: "total", label: "Total", type: "number" },
  { key: "balance", label: "Balance", type: "number" },
];
import { Trash2, Edit2, Printer, X, Plus, IndianRupee } from "lucide-react";
import ProductPicker, { StockBadge, rateFromMrp } from "@/components/ProductPicker";

const HSN_OPTIONS = ["9403", "3208", "4418", "9401", "6304", "9405"];
// Furniture/interiors line items are priced per piece, per square foot
// (laminate, glazing, false ceiling) or per running foot (beading,
// edge-banding, skirting) — qty*rate math doesn't care which, this is
// purely so the printed invoice line reads "20 sqft" instead of just "20".
const UNIT_OPTIONS = ["pcs", "sqft", "rft"];

const emptyItem = () => ({ sku: "", description: "", hsn: "9403", qty: 1, rate: 0, unit: "pcs", discount_pct: 0, tax_pct: GST_DEFAULT });

export default function Invoices() {
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState("");
  const [fStatus, setFStatus] = useState("All");
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(null);
  const [printRow, setPrintRow] = useState(null);
  const [saving, setSaving] = useState(false);
  const [office, setOffice] = useState({ name: "", address: "", gstin: "", invoice_prefix: "INV", home_state: "Telangana" });
  const [payFor, setPayFor] = useState(null);
  const [stock, setStock] = useState({});   // sku -> live stock for the lines in the open form

  const empty = {
    invoice_no: "", date: todayIST(), due_date: "",
    customer: "", billing_address: "", phone: "", gstin: "",
    place_of_supply: "Telangana", is_igst: false,
    line_items: [emptyItem()],
    subtotal: 0, discount_total: 0, cgst: 0, sgst: 0, igst: 0, total: 0,
    paid: 0, balance: 0, by_user: "", status: "Draft", notes: "Thank you for your business."
  };
  const [form, setForm] = useState(empty);

  const load = async () => {
    const [r, s] = await Promise.all([api.get("/invoices"), api.get("/settings/office")]);
    setRows(r.data);
    setOffice(s.data);
  };
  useEffect(() => { load(); }, []);

  // Interstate when the place of supply is outside the office's GST state;
  // the server makes the same call on save.
  const homeState = office.home_state || "Telangana";
  const isIgst = !!form.place_of_supply && form.place_of_supply.trim().toLowerCase() !== homeState.trim().toLowerCase();

  const computed = useMemo(() => {
    let subtotal = 0, tax = 0, cgst = 0, sgst = 0, igst = 0, disc = 0;
    for (const it of form.line_items || []) {
      const base = (it.qty || 0) * (it.rate || 0);
      const d = base * ((it.discount_pct || 0) / 100);
      const net = base - d;
      const t = net * ((it.tax_pct || 0) / 100);
      subtotal += net;
      disc += d;
      tax += t;
    }
    if (isIgst) igst = tax;
    else { cgst = tax / 2; sgst = tax / 2; }
    // Rounded to the rupee like the server's invoice_totals.
    const exact = Math.round((subtotal + tax) * 100) / 100;
    const total = Math.round(exact);
    const round_off = Math.round((total - exact) * 100) / 100;
    const balance = Math.max(0, total - (form.paid || 0));
    return { subtotal, discount_total: disc, cgst, sgst, igst, round_off, total, balance };
  }, [form.line_items, isIgst, form.paid]);

  const cf = useColumnFilters("invoices", COLUMNS);
  const applyColumns = cf.apply;
  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return applyColumns(rows.filter((r) =>
      (fStatus === "All" || r.status === fStatus) &&
      (!q || [r.customer, r.invoice_no, r.phone, r.gstin].some((v) => String(v || "").toLowerCase().includes(q)))
    ));
  }, [rows, search, fStatus, applyColumns]);

  const totals = useMemo(() => ({
    total: filtered.reduce((a, b) => a + (b.total || 0), 0),
    balance: filtered.reduce((a, b) => a + (b.balance || 0), 0),
  }), [filtered]);

  const openNew = () => {
    setEditing(null);
    setForm({ ...empty, invoice_no: "" });  // numbered by the server on save
    setShow(true);
  };
  const openEdit = (r) => { setEditing(r); setForm({ ...r, line_items: r.line_items?.length ? r.line_items : [emptyItem()] }); setShow(true); };

  const lineSkus = show ? (form.line_items || []).map((it) => it.sku).filter(Boolean).sort().join(",") : "";
  useEffect(() => {
    if (!lineSkus) { setStock({}); return; }
    api.get(`/inventory/lookup?skus=${encodeURIComponent(lineSkus)}`, { skipCache: true })
      .then(({ data }) => setStock(Object.fromEntries((data || []).map((r) => [r.sku, r]))))
      .catch(() => setStock({}));
  }, [lineSkus]);

  // MRP includes GST; the invoice adds GST per line, so use the pre-GST rate.
  const addProduct = (item) => setForm((f) => {
    const gst = item.gst_pct ?? GST_DEFAULT;
    const line = { ...emptyItem(), sku: item.sku, hsn: item.hsn || emptyItem().hsn, unit: item.unit || "pcs",
      description: [item.name, item.model_no].filter(Boolean).join(" · "), qty: 1,
      rate: rateFromMrp(item.mrp, gst), tax_pct: gst };
    const blankOnly = f.line_items.length === 1 && !f.line_items[0].description && !f.line_items[0].rate;
    return { ...f, line_items: blankOnly ? [line] : [...f.line_items, line] };
  });

  const save = async () => {
    if (saving) return;
    setSaving(true);
    // Money received comes from payments, never from this form.
    const payload = { ...form, is_igst: isIgst };
    delete payload.paid;
    delete payload.balance;
    try {
      const { data } = editing ? await api.put(`/invoices/${editing.id}`, payload) : await api.post("/invoices", payload);
      toast.success(editing ? "Invoice updated" : "Invoice created");
      if (data?.stock_warnings?.length) toast.warning(`Stock: ${data.stock_warnings.join("; ")}`, { duration: 8000 });
      setShow(false); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };
  const remove = async (id) => {
    if (!window.confirm("Delete invoice?")) return;
    await api.delete(`/invoices/${id}`); toast.success("Deleted"); load();
  };
  const setItem = (idx, k, v) => setForm((f) => ({ ...f, line_items: f.line_items.map((it, i) => i === idx ? { ...it, [k]: v } : it) }));
  const addItem = () => setForm((f) => ({ ...f, line_items: [...f.line_items, emptyItem()] }));
  const delItem = (idx) => setForm((f) => ({ ...f, line_items: f.line_items.filter((_, i) => i !== idx) }));

  return (
    <>
      <Topbar
        title="Tax Invoices"
        subtitle={`${filtered.length} invoices · ${inrFull(totals.total)} total · ${inrFull(totals.balance)} due`}
        onAdd={openNew}
        addLabel="New Invoice"
      />
      <div className="p-4 md:p-6" data-testid="invoices-page">
        <div className="flex flex-wrap gap-2 mb-4">
          <input placeholder="Search customer or invoice no…" value={search} onChange={(e) => setSearch(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] flex-1 min-w-[220px] max-w-md" data-testid="inv-search" />
          <select value={fStatus} onChange={(e) => setFStatus(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
            <option>All</option><option>Draft</option><option>Sent</option><option>Paid</option><option>Cancelled</option>
          </select>
          <ColumnFilters filters={cf} rows={rows} shown={filtered.length} testid="invoices-filters" />
        </div>

        <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Invoice No</th>
                  <th className="text-left font-semibold px-4 py-2.5">Date</th>
                  <th className="text-left font-semibold px-4 py-2.5">Customer</th>
                  <th className="text-left font-semibold px-4 py-2.5 hidden md:table-cell">GSTIN</th>
                  <th className="text-right font-semibold px-4 py-2.5">Subtotal</th>
                  <th className="text-right font-semibold px-4 py-2.5 hidden lg:table-cell">Tax</th>
                  <th className="text-right font-semibold px-4 py-2.5">Total</th>
                  <th className="text-right font-semibold px-4 py-2.5">Balance</th>
                  <th className="text-left font-semibold px-4 py-2.5">Status</th>
                  <th className="w-24"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.id} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50" data-testid={`inv-${r.id}`}>
                    <td className="px-4 py-3 font-mono text-xs">{r.invoice_no}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{fmtDate(r.date)}</td>
                    <td className="px-4 py-3 font-medium">{r.customer}</td>
                    <td className="px-4 py-3 font-mono text-xs text-[var(--ink-2)] hidden md:table-cell">{r.gstin || "—"}</td>
                    <td className="px-4 py-3 text-right font-mono">{inrFull(r.subtotal)}</td>
                    <td className="px-4 py-3 text-right font-mono text-[var(--ink-2)] hidden lg:table-cell">{inrFull((r.cgst || 0) + (r.sgst || 0) + (r.igst || 0))}</td>
                    <td className="px-4 py-3 text-right font-mono font-semibold">{inrFull(r.total)}</td>
                    <td className={`px-4 py-3 text-right font-mono ${r.balance > 0 ? "text-[var(--danger)] font-semibold" : "text-[var(--ink-3)]"}`}>{inrFull(r.balance)}</td>
                    <td className="px-4 py-3"><StageBadge stage={r.status === "Paid" ? "Delivered" : r.status === "Sent" ? "Quoted" : r.status === "Cancelled" ? "Lost" : "New"} />
                      {r.source === "tally" ? <div className="text-[10px] text-[var(--ink-3)] mt-0.5" title="Raised in Tally; refreshed by the Tally connector">from Tally</div>
                        : r.sale_id && <div className="text-[10px] text-[var(--ink-3)] mt-0.5">from sale</div>}</td>
                    <td className="px-2 py-3">
                      <div className="flex items-center gap-1">
                        {r.balance > 0 && r.status !== "Cancelled" && r.source !== "tally" && (
                          <button onClick={() => setPayFor(r)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]" title="Record payment" data-testid={`inv-pay-${r.id}`}><IndianRupee size={13} /></button>
                        )}
                        <button onClick={() => setPrintRow(r)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]" title="Print" data-testid={`inv-print-${r.id}`}><Printer size={13} /></button>
                        {r.source !== "tally" && (
                          <>
                            <button onClick={() => openEdit(r)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]"><Edit2 size={13} /></button>
                            <button onClick={() => remove(r.id)} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && <tr><td colSpan="10" className="text-center py-10 text-[var(--ink-3)]">No invoices</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-2 md:p-4" onClick={() => setShow(false)}>
          <div className="bg-white rounded-xl border w-full max-w-4xl max-h-[95vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">{editing ? "Edit Invoice" : "New Tax Invoice"}</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 overflow-y-auto">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
                <Fld l="Invoice No" v={form.invoice_no} oc={(v) => setForm({ ...form, invoice_no: v })} t2="inv-no" ph="Assigned on save" />
                <Fld l="Date" t="date" v={form.date} oc={(v) => setForm({ ...form, date: v })} />
                <Fld l="Due date" t="date" v={form.due_date} oc={(v) => setForm({ ...form, due_date: v })} />
                <Fld l="By" v={form.by_user} oc={(v) => setForm({ ...form, by_user: v })} />
                <div className="col-span-2 md:col-span-3">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] mb-1">Customer &amp; project</div>
                  <CustomerProjectPicker customerId={form.customer_id || ""} projectId={form.project_id || ""} allowNewProject={false}
                    onChange={({ customer, project }) => setForm((f) => ({
                      ...f, customer_id: customer?.id || "", project_id: project?.id || "",
                      ...(customer ? { customer: customer.company || customer.name, phone: customer.phone || f.phone,
                                       billing_address: f.billing_address || customer.address || "", gstin: f.gstin || customer.gstin || "" } : {}),
                    }))}
                    testid="inv-cpp" />
                </div>
                <Fld l="Bill to (as printed)" v={form.customer} oc={(v) => setForm({ ...form, customer: v })} cls="col-span-2 md:col-span-3" t2="inv-cust" />
                <Fld l="Billing Address" v={form.billing_address} oc={(v) => setForm({ ...form, billing_address: v })} cls="col-span-2 md:col-span-3" />
                <Fld l="Phone" v={form.phone} oc={(v) => setForm({ ...form, phone: v })} />
                <Fld l="GSTIN" v={form.gstin} oc={(v) => setForm({ ...form, gstin: v })} />
                <Fld l="Place of Supply" v={form.place_of_supply} oc={(v) => setForm({ ...form, place_of_supply: v })} />
                <div className="col-span-2 md:col-span-3 text-sm text-[var(--ink-2)] mt-1" data-testid="inv-igst">
                  {isIgst ? `Interstate supply (outside ${homeState}): IGST applies.` : `Within ${homeState}: CGST + SGST apply.`}
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)]">Line items</div>
                <ProductPicker onPick={addProduct} className="w-64" testId="invoice-product-picker" />
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-[var(--surface-2)]">
                    <tr className="text-[10px] uppercase tracking-wider text-[var(--ink-3)]">
                      <th className="text-left px-2 py-2">Description</th>
                      <th className="text-left px-2 py-2 w-20">HSN</th>
                      <th className="text-right px-2 py-2 w-16">Qty</th>
                      <th className="text-left px-2 py-2 w-16">Unit</th>
                      <th className="text-right px-2 py-2 w-24">Rate</th>
                      <th className="text-right px-2 py-2 w-16">Disc%</th>
                      <th className="text-right px-2 py-2 w-16">Tax%</th>
                      <th className="text-right px-2 py-2 w-24">Amount</th>
                      <th className="w-8"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {form.line_items.map((it, i) => {
                      const amt = (it.qty || 0) * (it.rate || 0) * (1 - (it.discount_pct || 0) / 100);
                      return (
                        <tr key={it.id || `${it.description}-${i}`} className="border-t border-[var(--border-light)]">

                          <td className="p-1"><input value={it.description} onChange={(e) => setItem(i, "description", e.target.value)} placeholder="Item description" className="w-full px-2 py-1.5 rounded border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)]" data-testid={`inv-item-desc-${i}`} />
                            {it.sku && (
                              <div className="mt-1 flex items-center gap-1.5 text-[10px] text-[var(--ink-3)]">
                                <span className="font-mono">{it.sku}</span><StockBadge item={stock[it.sku]} qty={it.qty} />
                              </div>
                            )}
                          </td>
                          <td className="p-1">
                            <select value={it.hsn} onChange={(e) => setItem(i, "hsn", e.target.value)} className="w-full px-1 py-1.5 rounded border border-[var(--border)] text-xs">
                              {HSN_OPTIONS.map((h) => <option key={h}>{h}</option>)}
                            </select>
                          </td>
                          <td className="p-1"><input type="number" value={it.qty} onChange={(e) => setItem(i, "qty", parseFloat(e.target.value) || 0)} className="w-full px-2 py-1.5 rounded border border-[var(--border)] text-sm text-right font-mono" data-testid={`inv-item-qty-${i}`} /></td>
                          <td className="p-1">
                            <select value={it.unit || "pcs"} onChange={(e) => setItem(i, "unit", e.target.value)}
                              aria-label={`Unit for line ${i + 1}`}
                              className="w-full px-1 py-1.5 rounded border border-[var(--border)] text-xs" data-testid={`inv-item-unit-${i}`}>
                              {UNIT_OPTIONS.map((u) => <option key={u} value={u}>{u}</option>)}
                            </select>
                          </td>
                          <td className="p-1"><input type="number" value={it.rate} onChange={(e) => setItem(i, "rate", parseFloat(e.target.value) || 0)} className="w-full px-2 py-1.5 rounded border border-[var(--border)] text-sm text-right font-mono" data-testid={`inv-item-rate-${i}`} /></td>
                          <td className="p-1"><input type="number" value={it.discount_pct} onChange={(e) => setItem(i, "discount_pct", parseFloat(e.target.value) || 0)} className="w-full px-2 py-1.5 rounded border border-[var(--border)] text-sm text-right font-mono" /></td>
                          <td className="p-1">
                            {/* Quick-select slabs rather than a free number box */}
                            <select value={it.tax_pct} onChange={(e) => setItem(i, "tax_pct", parseFloat(e.target.value))}
                              aria-label={`GST slab for line ${i + 1}`}
                              className="w-full px-2 py-1.5 rounded border border-[var(--border)] text-sm text-right font-mono">
                              {GST_SLABS.map((g) => <option key={g} value={g}>{g}%</option>)}
                              {!GST_SLABS.includes(it.tax_pct) && <option value={it.tax_pct}>{it.tax_pct}%</option>}
                            </select>
                          </td>
                          <td className="p-1 text-right font-mono text-sm font-semibold">{inrFull(amt)}</td>
                          <td className="p-1"><button onClick={() => delItem(i)} className="p-1 rounded hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={12} /></button></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <button onClick={addItem} className="mt-2 btn-ghost text-xs" data-testid="inv-add-item"><Plus size={13} />Add line</button>

              <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Notes</label>
                  <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} rows="3" className="w-full px-3 py-2 rounded-lg border border-[var(--border)] text-sm resize-none focus:border-[var(--brand)] outline-none" />
                  <p className="text-xs text-[var(--ink-3)] mt-2">Payments are recorded with the ₹ button on the invoice list{form.sale_id ? " (they go against the sale this invoice was raised from)" : ""}.</p>
                </div>
                <div className="bg-[var(--surface-2)] rounded-lg p-4 text-sm space-y-1.5 font-mono">
                  <Row label="Subtotal" val={computed.subtotal} />
                  <Row label="Discount" val={-computed.discount_total} muted />
                  {isIgst ? (
                    <Row label="IGST" val={computed.igst} />
                  ) : (
                    <>
                      <Row label="CGST" val={computed.cgst} />
                      <Row label="SGST" val={computed.sgst} />
                    </>
                  )}
                  {computed.round_off ? <div className="flex justify-between text-[var(--ink-3)]"><span>Round off</span><span>{paise(computed.round_off)}</span></div> : null}
                  <div className="border-t border-[var(--border)] pt-2 mt-2">
                    <Row label="TOTAL" val={computed.total} bold />
                    <Row label="Paid" val={form.paid} muted />
                    <Row label="Balance" val={computed.balance} bold danger={computed.balance > 0} />
                  </div>
                </div>
              </div>
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary disabled:opacity-60" onClick={save} disabled={saving} data-testid="inv-save">{saving ? "Saving…" : editing ? "Save" : "Create Invoice"}</button>
            </div>
          </div>
        </div>
      )}

      {printRow && <InvoicePrint invoice={printRow} office={office} onClose={() => setPrintRow(null)} />}
      {payFor && <RecordPayment invoice={payFor} onClose={() => setPayFor(null)} onSaved={() => { setPayFor(null); load(); }} />}
    </>
  );
}

const paise = (n) => `${n < 0 ? "−" : "+"}₹${Math.abs(Number(n) || 0).toFixed(2)}`;

function Row({ label, val, bold, muted, danger }) {
  return (
    <div className="flex justify-between">
      <span className={`${bold ? "font-bold text-[var(--ink)]" : "text-[var(--ink-2)]"} ${muted ? "text-[var(--ink-3)]" : ""}`}>{label}</span>
      <span className={`${bold ? "font-bold text-[var(--ink)]" : ""} ${danger ? "text-[var(--danger)]" : ""} ${muted ? "text-[var(--ink-3)]" : ""}`}>{inrFull(val)}</span>
    </div>
  );
}

function RecordPayment({ invoice, onClose, onSaved }) {
  const [amount, setAmount] = useState(invoice.balance || 0);
  const [date, setDate] = useState(todayIST());
  const [mode, setMode] = useState("Bank");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (busy || !(amount > 0)) return;
    setBusy(true);
    try {
      await api.post("/payments", {
        date, amount, mode, direction: "In", kind: amount >= invoice.balance ? "Final" : "Part",
        phone: invoice.phone || "", remarks: `Invoice ${invoice.invoice_no}`,
        // A sale-linked invoice's money is tracked on the sale.
        ...(invoice.sale_id ? { against_sale_id: invoice.sale_id } : { against_invoice_id: invoice.id }),
      });
      toast.success("Payment recorded");
      onSaved();
    } catch (e) { toast.error(e?.response?.data?.detail || "Couldn't record the payment"); }
    finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl border w-full max-w-sm" onClick={(e) => e.stopPropagation()} data-testid="inv-pay-modal">
        <div className="px-5 py-4 border-b font-heading font-semibold">Record payment · {invoice.invoice_no}</div>
        <div className="p-5 space-y-3">
          <div className="text-sm text-[var(--ink-2)]">Balance due {inrFull(invoice.balance)}</div>
          <Fld l="Amount" t="number" v={amount} oc={(v) => setAmount(parseFloat(v) || 0)} t2="inv-pay-amount" />
          <Fld l="Date" t="date" v={date} oc={setDate} />
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Mode</label>
            <select value={mode} onChange={(e) => setMode(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
              {["Bank", "UPI", "Cheque", "Other"].map((m) => <option key={m}>{m}</option>)}
            </select>
          </div>
        </div>
        <div className="px-5 py-4 border-t flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary disabled:opacity-60" disabled={busy || !(amount > 0)} onClick={save} data-testid="inv-pay-save">{busy ? "Saving…" : "Record"}</button>
        </div>
      </div>
    </div>
  );
}

function Fld({ l, v, oc, t = "text", cls = "", t2, ph }) {
  return (
    <div className={cls}>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <input type={t} value={v ?? ""} placeholder={ph} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" data-testid={t2} />
    </div>
  );
}

function InvoicePrint({ invoice, office, onClose }) {
  useEffect(() => {
    document.body.classList.add("printing");
    return () => document.body.classList.remove("printing");
  }, []);
  const tax = (invoice.cgst || 0) + (invoice.sgst || 0) + (invoice.igst || 0);
  return (
    <div className="fixed inset-0 bg-white z-[60] overflow-auto print-view">
      <div className="max-w-4xl mx-auto p-8 print:p-0" id="print-area">
        <div className="flex justify-between items-start mb-8 print:mb-6">
          <div>
            <div className="w-16 h-16 rounded-xl bg-[var(--brand)] flex items-center justify-center text-white font-heading font-bold text-2xl mb-3">M</div>
            <div className="font-heading font-bold text-2xl text-[var(--ink)]">{office.name}</div>
            <div className="text-sm text-[var(--ink-2)]">{office.address}</div>
            {office.gstin && <div className="text-xs font-mono text-[var(--ink-3)] mt-1">GSTIN: {office.gstin}</div>}
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-widest text-[var(--ink-3)] font-semibold">Tax Invoice</div>
            <div className="font-heading font-bold text-lg mt-1">{invoice.invoice_no}</div>
            <div className="text-sm text-[var(--ink-2)] mt-1">{fmtDate(invoice.date)}</div>
            {invoice.due_date && <div className="text-xs text-[var(--ink-3)] mt-0.5">Due {fmtDate(invoice.due_date)}</div>}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-8 mb-8">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-[var(--ink-3)] font-semibold mb-1">Bill to</div>
            <div className="font-semibold text-[var(--ink)]">{invoice.customer}</div>
            <div className="text-sm text-[var(--ink-2)]">{invoice.billing_address}</div>
            {invoice.phone && <div className="text-sm text-[var(--ink-2)] font-mono">📞 {invoice.phone}</div>}
            {invoice.gstin && <div className="text-xs font-mono text-[var(--ink-2)] mt-1">GSTIN: {invoice.gstin}</div>}
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-widest text-[var(--ink-3)] font-semibold mb-1">Place of supply</div>
            <div className="font-medium">{invoice.place_of_supply}</div>
            <div className="text-xs text-[var(--ink-3)] mt-1">{invoice.is_igst ? "Interstate (IGST)" : "Intrastate (CGST + SGST)"}</div>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm mb-6 border-t border-b border-[var(--ink)]">
            <thead>
              <tr className="border-b border-[var(--border)]">
                <th className="text-left py-2 text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">#</th>
                <th className="text-left py-2 text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">Description</th>
                <th className="text-left py-2 text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">HSN</th>
                <th className="text-right py-2 text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">Qty</th>
                <th className="text-right py-2 text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">Rate</th>
                <th className="text-right py-2 text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">Tax%</th>
                <th className="text-right py-2 text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">Amount</th>
              </tr>
            </thead>
            <tbody>
              {(invoice.line_items || []).map((it, i) => {
                const amt = (it.qty || 0) * (it.rate || 0) * (1 - (it.discount_pct || 0) / 100);
                return (
                  <tr key={it.id || `${it.description}-${i}`} className="border-b border-[var(--border-light)]">

                    <td className="py-3">{i + 1}</td>
                    <td className="py-3">{it.description}</td>
                    <td className="py-3 font-mono">{it.hsn}</td>
                    <td className="py-3 text-right font-mono">{it.qty}{it.unit && it.unit !== "pcs" ? ` ${it.unit}` : ""}</td>
                    <td className="py-3 text-right font-mono">{inrFull(it.rate)}</td>
                    <td className="py-3 text-right font-mono">{it.tax_pct}%</td>
                    <td className="py-3 text-right font-mono font-semibold">{inrFull(amt)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="flex justify-end mb-8">
          <div className="w-72 space-y-1 text-sm font-mono">
            <div className="flex justify-between"><span className="text-[var(--ink-2)]">Subtotal</span><span>{inrFull(invoice.subtotal)}</span></div>
            {invoice.is_igst ? (
              <div className="flex justify-between"><span className="text-[var(--ink-2)]">IGST</span><span>{inrFull(invoice.igst)}</span></div>
            ) : (
              <>
                <div className="flex justify-between"><span className="text-[var(--ink-2)]">CGST</span><span>{inrFull(invoice.cgst)}</span></div>
                <div className="flex justify-between"><span className="text-[var(--ink-2)]">SGST</span><span>{inrFull(invoice.sgst)}</span></div>
              </>
            )}
            {invoice.round_off ? <div className="flex justify-between"><span className="text-[var(--ink-2)]">Round off</span><span>{paise(invoice.round_off)}</span></div> : null}
            <div className="flex justify-between border-t border-[var(--ink)] pt-2 mt-2 font-bold text-base"><span>TOTAL</span><span>{inrFull(invoice.total)}</span></div>
            <div className="flex justify-between text-[var(--ink-3)]"><span>Paid</span><span>{inrFull(invoice.paid)}</span></div>
            <div className={`flex justify-between font-bold ${invoice.balance > 0 ? "text-[var(--danger)]" : ""}`}><span>Balance</span><span>{inrFull(invoice.balance)}</span></div>
          </div>
        </div>

        <div className="text-sm text-[var(--ink)] mb-4" data-testid="inv-words"><span className="text-[var(--ink-3)]">Amount in words: </span>{amountInWords(invoice.total)}</div>
        <div className="text-xs text-[var(--ink-3)] italic border-t border-[var(--border)] pt-4">
          {invoice.notes}
        </div>
        <div className="text-[10px] text-[var(--ink-3)] mt-8">This is a computer-generated invoice.</div>
      </div>
      <div className="no-print fixed bottom-6 right-6 flex gap-2 z-10">
        <button onClick={onClose} className="btn-ghost">Close</button>
        <button onClick={() => window.print()} className="btn-primary" data-testid="print-btn"><Printer size={14} />Print / Save PDF</button>
      </div>
    </div>
  );
}
