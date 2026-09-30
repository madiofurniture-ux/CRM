import { useEffect, useMemo, useState } from "react";
import Topbar from "@/components/Topbar";
import EmptyState from "@/components/EmptyState";
import StageBadge from "@/components/StageBadge";
import SearchSelect from "@/components/SearchSelect";
import { usePrivacyMode } from "@/context/PrivacyModeContext";
import { useTenantConfig } from "@/context/TenantConfigContext";
import api, { formatApiError } from "@/lib/api";
import { shrinkImage, dataUrlKb } from "@/lib/image";
import { inrFull, fmtDate } from "@/lib/format";
import { GST_SLABS } from "@/lib/constants";
import { X, Factory, ImagePlus, Trash2 } from "lucide-react";
import { toast } from "sonner";

// Mirrors models.MO_STATUSES. "Quoted" is this document's draft state and is
// the one status that does NOT reach project P&L.
const STATUSES = ["Quoted", "Confirmed", "In Production", "Dispatched", "Delivered"];
const MODE_LABEL = { BANK_TRANSFER: "Bank Transfer", OTHER: "Other (Direct)" };

// The server nulls every settlement figure under privacy mode, so a masked
// cell is `null` where a real one is a number — `!= null` distinguishes it
// from a genuine 0. Same placeholder Payments.jsx uses, so the two money
// screens read the same way.
const MASK = "••••••";
const money = (v) => (v == null ? MASK : inrFull(v));

const emptyForm = {
  date: new Date().toISOString().slice(0, 10), vendor_id: "", project_id: "",
  division: "", site_location: "", description: "", quote_no: "", po_id: "",
  image_url: "", notes: "", actual_amount: "", tax_rate: "0",
  bank_due: "", other_due: "", status: "Quoted",
};

export default function ManufacturerOrders() {
  const { isOtherHidden, requestUnlock } = usePrivacyMode();
  const { divisions } = useTenantConfig();

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [vendors, setVendors] = useState([]);
  const [projects, setProjects] = useState([]);
  const [pos, setPos] = useState([]);

  const [fStatus, setFStatus] = useState("All");
  const [fDivision, setFDivision] = useState("All");

  const [show, setShow] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [vendorDraft, setVendorDraft] = useState(null);
  const [savingVendor, setSavingVendor] = useState(false);

  const [preview, setPreview] = useState("");
  const [settling, setSettling] = useState(null);

  const load = () => {
    setLoading(true);
    // Division/status filtering is done server-side (the list route
    // allow-lists these params) so a long order book is never shipped whole
    // just to be thrown away in the browser.
    const params = { mask_other: isOtherHidden };
    if (fStatus !== "All") params.status = fStatus;
    if (fDivision !== "All") params.division = fDivision;
    api.get("/manufacturer-orders", { params })
      .then(({ data }) => setRows(data))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  };
  useEffect(load, [isOtherHidden, fStatus, fDivision]); // eslint-disable-line

  useEffect(() => {
    api.get("/vendors").then(({ data }) => setVendors(data)).catch(() => setVendors([]));
    api.get("/projects").then(({ data }) => setProjects(data)).catch(() => setProjects([]));
    api.get("/purchase-orders").then(({ data }) => setPos(data)).catch(() => setPos([]));
  }, []);

  const vendorOptions = useMemo(() => vendors.map((v) => ({
    id: v.id, label: v.name ? `${v.code} — ${v.name}` : v.code, sub: v.code,
  })), [vendors]);
  const projectOptions = useMemo(() => projects.map((p) => ({
    id: p.id, label: p.project_no, sub: p.customer,
  })), [projects]);
  const poOptions = useMemo(() => pos.map((p) => ({
    id: p.id, label: p.po_no, sub: p.vendor_code,
  })), [pos]);

  // Mirrors models.manufacturer_order_totals — the server recomputes these on
  // save; this is only so the form can show a running total.
  const actual = parseFloat(form.actual_amount) || 0;
  const rate = parseFloat(form.tax_rate) || 0;
  const taxAmount = Math.round(actual * rate) / 100;
  const finalTotal = actual + taxAmount;
  const splitTotal = (parseFloat(form.bank_due) || 0) + (parseFloat(form.other_due) || 0);

  const openNew = () => { setForm(emptyForm); setEditingId(null); setShow(true); };
  const openEdit = (o) => {
    setForm({
      date: o.date || "", vendor_id: o.vendor_id || "", project_id: o.project_id || "",
      division: o.division || "", site_location: o.site_location || "",
      description: o.description || "", quote_no: o.quote_no || "", po_id: o.po_id || "",
      image_url: o.image_url || "", notes: o.notes || "",
      actual_amount: o.actual_amount ?? "", tax_rate: o.tax_rate ?? "0",
      // Masked out for this viewer — left blank rather than pre-filled with a
      // placeholder that would be saved back as a real number.
      bank_due: o.bank_due ?? "", other_due: o.other_due ?? "",
      status: o.status || "Quoted",
    });
    setEditingId(o.id);
    setShow(true);
  };

  const pickImage = async (file) => {
    if (!file) return;
    try {
      const dataUrl = await shrinkImage(file);
      setForm((f) => ({ ...f, image_url: dataUrl }));
    } catch (e) {
      toast.error(e.message || "Could not read that image");
    }
  };

  const saveVendor = async () => {
    const name = (vendorDraft?.name || "").trim();
    if (!name) { toast.error("Manufacturer name is required"); return; }
    setSavingVendor(true);
    try {
      const { data } = await api.post("/vendors", { name });
      setVendors((v) => [data, ...v]);
      setForm((f) => ({ ...f, vendor_id: data.id }));
      setVendorDraft(null);
      toast.success(`Manufacturer ${data.code} created`);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Could not create manufacturer");
    } finally { setSavingVendor(false); }
  };

  const save = async () => {
    if (saving) return;
    if (!form.vendor_id) { toast.error("Select a manufacturer"); return; }
    if (actual <= 0) { toast.error("Enter the agreed amount"); return; }
    setSaving(true);
    try {
      // order_code, vendor name/code and every total are assigned
      // server-side — deliberately not sent from here.
      const payload = {
        ...form,
        actual_amount: actual, tax_rate: rate,
        bank_due: parseFloat(form.bank_due) || 0,
        other_due: parseFloat(form.other_due) || 0,
      };
      if (editingId) await api.put(`/manufacturer-orders/${editingId}`, payload);
      else await api.post("/manufacturer-orders", payload);
      toast.success(editingId ? "Order updated" : "Order created");
      setShow(false); setEditingId(null); setForm(emptyForm); load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Save failed");
    } finally { setSaving(false); }
  };

  const remove = async () => {
    if (!editingId) return;
    if (!window.confirm("Delete this manufacturer order? This cannot be undone.")) return;
    try {
      await api.delete(`/manufacturer-orders/${editingId}`);
      toast.success("Order deleted");
      setShow(false); setEditingId(null); load();
    } catch { toast.error("Delete failed"); }
  };

  const saveNotes = async (order, notes) => {
    if ((order.notes || "") === notes) return;
    try {
      await api.put(`/manufacturer-orders/${order.id}`, { notes });
      setRows((rs) => rs.map((r) => (r.id === order.id ? { ...r, notes } : r)));
    } catch {
      toast.error("Could not save the note");
      load();
    }
  };

  const totals = rows.reduce((a, r) => ({
    final: a.final + (r.final_total || 0),
    // A masked row contributes nothing to a running total, so the footer is
    // shown as unavailable rather than as a smaller, wrong-looking number.
    masked: a.masked || r.total_balance_due == null,
    due: a.due + (r.total_balance_due || 0),
  }), { final: 0, masked: false, due: 0 });

  return (
    <>
      <Topbar
        title="Manufacturer Orders"
        subtitle={`${rows.length} orders · ${inrFull(totals.final)} ordered`}
        onAdd={openNew}
        addLabel="New Order"
      />

      <div className="p-6 space-y-4" data-testid="manufacturer-orders-page">
        <div className="flex flex-wrap gap-2">
          <select value={fStatus} onChange={(e) => setFStatus(e.target.value)}
            aria-label="Filter by status" data-testid="mo-filter-status"
            className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
            <option>All</option>
            {STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <select value={fDivision} onChange={(e) => setFDivision(e.target.value)}
            aria-label="Filter by division" data-testid="mo-filter-division"
            className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
            <option>All</option>
            {divisions.map((d) => <option key={d.id} value={d.slug}>{d.name}</option>)}
          </select>
          <div className="flex-1" />
          <div className="text-sm text-[var(--ink-3)] self-center">
            Outstanding:{" "}
            <span className="font-mono font-semibold text-[var(--ink)]">
              {totals.masked ? MASK : inrFull(totals.due)}
            </span>
            {totals.masked && (
              <button onClick={requestUnlock} className="ml-2 text-blue-600 underline text-xs">
                unlock
              </button>
            )}
          </div>
        </div>

        <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5 w-16">Image</th>
                  <th className="text-left font-semibold px-4 py-2.5">Order #</th>
                  <th className="text-left font-semibold px-4 py-2.5">Site</th>
                  <th className="text-left font-semibold px-4 py-2.5">Project / Description</th>
                  <th className="text-right font-semibold px-4 py-2.5">Actual</th>
                  <th className="text-right font-semibold px-4 py-2.5">Tax</th>
                  <th className="text-right font-semibold px-4 py-2.5">Final Total</th>
                  <th className="text-right font-semibold px-4 py-2.5">Bank Due</th>
                  <th className="text-right font-semibold px-4 py-2.5">Other Due</th>
                  <th className="text-left font-semibold px-4 py-2.5">Status</th>
                  <th className="text-left font-semibold px-4 py-2.5">Quote #</th>
                  <th className="text-left font-semibold px-4 py-2.5">Notes</th>
                  <th className="w-24" />
                </tr>
              </thead>
              <tbody>
                {!loading && rows.map((o) => (
                  <tr key={o.id} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50"
                    data-testid={`mo-${o.id}`}>
                    <td className="px-4 py-2">
                      {o.image_url ? (
                        <button onClick={() => setPreview(o.image_url)}
                          aria-label={`Preview image for ${o.order_code}`}>
                          <img src={o.image_url} alt="" loading="lazy"
                            className="w-10 h-10 rounded-lg object-cover border border-[var(--border-light)]" />
                        </button>
                      ) : (
                        <div className="w-10 h-10 rounded-lg bg-[var(--surface-2)] flex items-center justify-center text-[var(--ink-3)]">
                          <Factory size={14} />
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      <button onClick={() => openEdit(o)} className="font-mono text-xs font-semibold hover:text-[var(--brand)]">
                        {o.order_code}
                      </button>
                      <div className="text-[10px] text-[var(--ink-3)]">{fmtDate(o.date)}</div>
                    </td>
                    <td className="px-4 py-2 text-[var(--ink-2)]">{o.site_location || "—"}</td>
                    <td className="px-4 py-2">
                      <div className="text-[var(--ink)]">
                        {projects.find((p) => p.id === o.project_id)?.project_no || "—"}
                      </div>
                      <div className="text-[11px] text-[var(--ink-3)] truncate max-w-[14rem]">{o.description}</div>
                    </td>
                    <td className="px-4 py-2 text-right font-mono">{inrFull(o.actual_amount)}</td>
                    <td className="px-4 py-2 text-right font-mono text-[var(--ink-2)]">{inrFull(o.tax_amount)}</td>
                    <td className="px-4 py-2 text-right font-mono font-semibold">{inrFull(o.final_total)}</td>
                    <td className="px-4 py-2 text-right font-mono">{money(o.bank_due)}</td>
                    <td className="px-4 py-2 text-right font-mono" data-testid={`mo-other-due-${o.id}`}>
                      {o.other_due == null ? (
                        <button onClick={requestUnlock} className="text-[var(--ink-3)] hover:text-blue-600"
                          title="Hidden by privacy mode — click to unlock">{MASK}</button>
                      ) : inrFull(o.other_due)}
                    </td>
                    <td className="px-4 py-2"><StageBadge stage={o.status} /></td>
                    <td className="px-4 py-2 text-[var(--ink-2)] text-xs">{o.quote_no || "—"}</td>
                    <td className="px-4 py-2">
                      <input
                        defaultValue={o.notes || ""}
                        onBlur={(e) => saveNotes(o, e.target.value)}
                        placeholder="Add a note…"
                        aria-label={`Notes for ${o.order_code}`}
                        data-testid={`mo-notes-${o.id}`}
                        className="w-40 px-2 py-1 rounded border border-transparent hover:border-[var(--border)] focus:border-[var(--brand)] bg-transparent text-xs outline-none"
                      />
                    </td>
                    <td className="px-2 py-2 text-right">
                      <button onClick={() => setSettling(o)} className="btn-ghost text-xs"
                        data-testid={`mo-settle-${o.id}`}>Settle</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && rows.length === 0 && (
              <EmptyState icon={Factory} title="No manufacturer orders"
                hint="Raise an order to track production and settlement against a manufacturer." />
            )}
          </div>
        </div>
      </div>

      {preview && (
        <div className="fixed inset-0 bg-black/70 z-[60] flex items-center justify-center p-6"
          onClick={() => setPreview("")} role="dialog" aria-modal="true" aria-label="Order image">
          <img src={preview} alt="Manufacturer order reference" className="max-h-[90vh] max-w-full rounded-xl" />
        </div>
      )}

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div role="dialog" aria-modal="true" aria-labelledby="mo-modal-title"
            className="bg-white rounded-xl border w-full max-w-3xl max-h-[92vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b sticky top-0 bg-white z-10">
              <h3 id="mo-modal-title" className="font-heading font-semibold text-lg">
                {editingId ? "Edit Manufacturer Order" : "New Manufacturer Order"}
              </h3>
              <button onClick={() => setShow(false)} aria-label="Close"
                className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>

            <div className="p-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Manufacturer *</label>
                  <SearchSelect
                    options={vendorOptions} value={form.vendor_id}
                    onChange={(id) => setForm({ ...form, vendor_id: id })}
                    placeholder="Search manufacturer, name or code…"
                    emptyLabel="No manufacturers found" testId="mo-vendor"
                    createLabel="Manufacturer"
                    onCreate={(term) => setVendorDraft({ name: term })}
                  />
                  {vendorDraft && (
                    <div className="mt-2 p-3 rounded-lg border border-[var(--brand)] bg-[var(--brand-soft)]/30 flex items-end gap-2">
                      <div className="flex-1">
                        <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">New manufacturer name</label>
                        <input autoFocus value={vendorDraft.name}
                          onChange={(e) => setVendorDraft({ name: e.target.value })}
                          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); saveVendor(); } }}
                          className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]"
                          data-testid="mo-vendor-new-name" />
                      </div>
                      <button type="button" className="btn-primary text-xs shrink-0 disabled:opacity-60"
                        onClick={saveVendor} disabled={savingVendor} data-testid="mo-vendor-new-save">
                        {savingVendor ? "Saving…" : "Create"}
                      </button>
                      <button type="button" className="btn-ghost text-xs shrink-0" onClick={() => setVendorDraft(null)}>Cancel</button>
                    </div>
                  )}
                </div>

                <div>
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Against project</label>
                  <SearchSelect
                    options={projectOptions} value={form.project_id}
                    onChange={(id) => setForm({ ...form, project_id: id })}
                    placeholder="Not project-linked" emptyLabel="No projects found" testId="mo-project"
                  />
                  <div className="text-[11px] text-[var(--ink-3)] mt-1">
                    Linking feeds this order's cost into the project's P&amp;L once it leaves Quoted.
                  </div>
                </div>

                <F l="Date" t="date" v={form.date} oc={(v) => setForm({ ...form, date: v })} />
                <div>
                  <label htmlFor="mo-division" className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Division</label>
                  <select id="mo-division" value={form.division} onChange={(e) => setForm({ ...form, division: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm" data-testid="mo-division">
                    <option value="">—</option>
                    {divisions.map((d) => <option key={d.id} value={d.slug}>{d.name}</option>)}
                  </select>
                </div>

                <F l="Site location" v={form.site_location} oc={(v) => setForm({ ...form, site_location: v })} />
                <F l="Manufacturer quote #" v={form.quote_no} oc={(v) => setForm({ ...form, quote_no: v })} />
                <F l="Description" v={form.description} oc={(v) => setForm({ ...form, description: v })} cls="col-span-2" />

                <div>
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Internal PO (optional)</label>
                  <SearchSelect
                    options={poOptions} value={form.po_id}
                    onChange={(id) => setForm({ ...form, po_id: id })}
                    placeholder="No linked PO" emptyLabel="No purchase orders found" testId="mo-po"
                  />
                </div>
                <div>
                  <label htmlFor="mo-status" className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Production status</label>
                  <select id="mo-status" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm" data-testid="mo-status">
                    {STATUSES.map((s) => <option key={s}>{s}</option>)}
                  </select>
                </div>
              </div>

              {/* Reference photo — shrunk to a data URL on-device, same as D&W
                  survey photos and inventory product images. No blob store. */}
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Reference photo</label>
                <div className="flex items-center gap-3">
                  {form.image_url ? (
                    <>
                      <img src={form.image_url} alt="Selected reference" className="w-16 h-16 rounded-lg object-cover border border-[var(--border-light)]" />
                      <span className="text-[11px] text-[var(--ink-3)]">{dataUrlKb(form.image_url)} KB</span>
                      <button type="button" onClick={() => setForm({ ...form, image_url: "" })}
                        className="btn-ghost text-xs text-red-600"><Trash2 size={13} /> Remove</button>
                    </>
                  ) : (
                    <label className="btn-ghost text-xs cursor-pointer">
                      <ImagePlus size={13} /> Add photo
                      <input type="file" accept="image/*" className="sr-only"
                        data-testid="mo-image" onChange={(e) => pickImage(e.target.files?.[0])} />
                    </label>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <F l="Agreed amount (pre-tax)" t="number" v={form.actual_amount}
                  oc={(v) => setForm({ ...form, actual_amount: v })} testId="mo-actual" />
                <div>
                  <label htmlFor="mo-tax" className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">GST rate</label>
                  <select id="mo-tax" value={form.tax_rate} onChange={(e) => setForm({ ...form, tax_rate: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm" data-testid="mo-tax">
                    {GST_SLABS.map((g) => <option key={g} value={g}>{g}%</option>)}
                  </select>
                </div>
              </div>

              <div className="bg-[var(--surface-2)] rounded-xl p-3 text-sm space-y-1" data-testid="mo-breakdown">
                <div className="flex justify-between"><span className="text-[var(--ink-3)]">Actual</span><span className="font-mono">{inrFull(actual)}</span></div>
                <div className="flex justify-between"><span className="text-[var(--ink-3)]">Tax ({rate}%)</span><span className="font-mono">{inrFull(taxAmount)}</span></div>
                <div className="flex justify-between font-semibold pt-1 border-t border-[var(--border-light)]">
                  <span>Final total</span><span className="font-mono" data-testid="mo-final-total">{inrFull(finalTotal)}</span>
                </div>
                <div className="text-[10px] text-[var(--ink-3)] pt-1">Recalculated server-side on save.</div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <F l="Bank transfer due" t="number" v={form.bank_due}
                  oc={(v) => setForm({ ...form, bank_due: v })} testId="mo-bank-due" />
                <F l="Other / direct settlement due" t="number" v={form.other_due}
                  oc={(v) => setForm({ ...form, other_due: v })} testId="mo-other-due" />
              </div>
              <div className="text-[11px] text-[var(--ink-3)] -mt-2">
                {splitTotal === 0
                  ? "Leave both blank to treat the whole order as bank-settled."
                  : Math.abs(splitTotal - finalTotal) > 0.5
                    ? `Split totals ${inrFull(splitTotal)} against a final total of ${inrFull(finalTotal)}.`
                    : "Split matches the final total."}
              </div>

              <F l="Notes" v={form.notes} oc={(v) => setForm({ ...form, notes: v })} />
            </div>

            <div className="px-5 py-4 border-t flex items-center gap-2 sticky bottom-0 bg-white">
              {editingId && <button className="btn-ghost text-red-600 hover:bg-red-50" onClick={remove} data-testid="mo-delete">Delete</button>}
              <div className="flex-1" />
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary disabled:opacity-60" onClick={save} disabled={saving} data-testid="mo-save">
                {saving ? "Saving…" : editingId ? "Save Changes" : "Create Order"}
              </button>
            </div>
          </div>
        </div>
      )}

      {settling && (
        <SettleModal
          order={settling}
          onClose={() => setSettling(null)}
          onDone={() => { setSettling(null); load(); }}
          masked={isOtherHidden}
          onUnlock={requestUnlock}
        />
      )}
    </>
  );
}

function SettleModal({ order, onClose, onDone, masked, onUnlock }) {
  const [mode, setMode] = useState("BANK_TRANSFER");
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [walletId, setWalletId] = useState("");
  const [wallets, setWallets] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/cashbooks").then(({ data }) => setWallets(data)).catch(() => setWallets([]));
  }, []);

  const due = mode === "BANK_TRANSFER" ? order.bank_due : order.other_due;

  const submit = async () => {
    if (saving) return;
    const value = parseFloat(amount) || 0;
    if (value <= 0) { toast.error("Enter an amount"); return; }
    setSaving(true);
    try {
      // Only what this screen knows first-hand is sent. The resulting
      // balances are recomputed server-side — never posted from here.
      await api.post(`/manufacturer-orders/${order.id}/payments`, {
        mode, amount: value, reference_no: reference, wallet_id: walletId,
      });
      toast.success("Settlement recorded");
      onDone();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Could not record the settlement");
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="mo-settle-title"
        className="bg-white rounded-2xl border border-[var(--border)] w-full max-w-md"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h3 id="mo-settle-title" className="font-heading font-semibold text-lg">Record Settlement</h3>
          <button onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        <div className="p-5 space-y-4">
          <div className="text-sm text-[var(--ink-2)]">
            <span className="font-mono font-semibold">{order.order_code}</span>
            {" · "}Final total <span className="font-mono">{inrFull(order.final_total)}</span>
          </div>

          <div>
            <label htmlFor="mo-settle-mode" className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Settlement leg</label>
            <select id="mo-settle-mode" value={mode} onChange={(e) => setMode(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-[var(--border)] text-sm" data-testid="mo-settle-mode">
              {Object.entries(MODE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <div className="text-[11px] text-[var(--ink-3)] mt-1">
              Outstanding on this leg:{" "}
              {due == null ? (
                <>
                  {MASK}{" "}
                  <button onClick={onUnlock} className="text-blue-600 underline">unlock</button>
                </>
              ) : inrFull(due)}
            </div>
          </div>

          <div>
            <label htmlFor="mo-settle-amount" className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Amount</label>
            <input id="mo-settle-amount" type="number" min="0" value={amount}
              onChange={(e) => setAmount(e.target.value)} data-testid="mo-settle-amount"
              className="w-full px-3 py-2 rounded-lg border border-[var(--border)] text-sm" />
            {masked && (
              <div className="text-[11px] text-[var(--ink-3)] mt-1">
                A payment larger than what is outstanding on this leg is refused.
              </div>
            )}
          </div>

          <div>
            <label htmlFor="mo-settle-ref" className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">
              {mode === "BANK_TRANSFER" ? "UTR reference" : "Voucher reference"}
            </label>
            <input id="mo-settle-ref" value={reference} onChange={(e) => setReference(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-[var(--border)] text-sm" data-testid="mo-settle-ref" />
          </div>

          <div>
            <label htmlFor="mo-settle-wallet" className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Paid from wallet (optional)</label>
            <select id="mo-settle-wallet" value={walletId} onChange={(e) => setWalletId(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-[var(--border)] text-sm" data-testid="mo-settle-wallet">
              <option value="">Not from a wallet</option>
              {wallets.map((w) => <option key={w.id} value={w.id}>{w.book_name}</option>)}
            </select>
            <div className="text-[11px] text-[var(--ink-3)] mt-1">
              Debits that wallet's ledger. It is not charged to the project twice — the order already carries the cost.
            </div>
          </div>
        </div>
        <div className="px-5 py-4 border-t flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary disabled:opacity-60" onClick={submit} disabled={saving} data-testid="mo-settle-save">
            {saving ? "Saving…" : "Record"}
          </button>
        </div>
      </div>
    </div>
  );
}

function F({ l, v, oc, t = "text", cls = "", testId }) {
  const id = `mo-f-${l.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <div className={cls}>
      <label htmlFor={id} className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <input id={id} type={t} value={v} onChange={(e) => oc(e.target.value)} data-testid={testId}
        className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" />
    </div>
  );
}
