import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { X, Trash2, ArrowDownCircle, ArrowUpCircle, Repeat, SlidersHorizontal, Plus } from "lucide-react";

const TYPES = ["Receipt", "Issue", "Transfer", "Adjustment", "Return"];
const TYPE_ICON = { Receipt: ArrowDownCircle, Return: ArrowDownCircle, Issue: ArrowUpCircle, Transfer: Repeat, Adjustment: SlidersHorizontal };
const TYPE_COLOR = {
  Receipt: "text-[var(--moss)]", Return: "text-[var(--moss)]",
  Issue: "text-[var(--danger)]", Transfer: "text-[var(--brand)]", Adjustment: "text-[var(--warn)]",
};

// Must match backend server.py's PALETTE_KEYS — the fixed color order both
// "create a new floor" and the seed data cycle through.
const PALETTE_KEYS = ["brand", "blue", "moss", "warn", "danger", "purple", "teal", "pink"];
const FLOOR_STYLES = {
  brand: { bg: "bg-[var(--brand-soft)]", text: "text-[var(--brand)]", dot: "bg-[var(--brand)]", swatch: "bg-[var(--brand)]" },
  blue: { bg: "bg-blue-50", text: "text-blue-700", dot: "bg-blue-500", swatch: "bg-blue-500" },
  moss: { bg: "bg-[var(--moss-soft)]", text: "text-[var(--moss)]", dot: "bg-[var(--moss)]", swatch: "bg-[var(--moss)]" },
  warn: { bg: "bg-[var(--warn-soft)]", text: "text-[var(--warn)]", dot: "bg-[var(--warn)]", swatch: "bg-[var(--warn)]" },
  danger: { bg: "bg-[var(--danger-soft)]", text: "text-[var(--danger)]", dot: "bg-[var(--danger)]", swatch: "bg-[var(--danger)]" },
  purple: { bg: "bg-purple-50", text: "text-purple-700", dot: "bg-purple-500", swatch: "bg-purple-500" },
  teal: { bg: "bg-teal-50", text: "text-teal-700", dot: "bg-teal-500", swatch: "bg-teal-500" },
  pink: { bg: "bg-pink-50", text: "text-pink-700", dot: "bg-pink-500", swatch: "bg-pink-500" },
};
const NEUTRAL_STYLE = { bg: "bg-[var(--surface-2)]", text: "text-[var(--ink-2)]", dot: "bg-[var(--ink-3)]" };

function FloorBadge({ name, floorByName }) {
  if (!name) return null;
  const floor = floorByName[name];
  const c = (floor && FLOOR_STYLES[floor.color]) || NEUTRAL_STYLE;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium ${c.bg} ${c.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {name}
    </span>
  );
}

export default function StockLedger() {
  const [moves, setMoves] = useState([]);
  const [summary, setSummary] = useState(null);
  const [inventory, setInventory] = useState([]);
  const [floors, setFloors] = useState([]);
  const [show, setShow] = useState(false);
  const [showFloorModal, setShowFloorModal] = useState(false);
  const [tab, setTab] = useState("onhand");
  const [selectedFloor, setSelectedFloor] = useState("");
  const [saving, setSaving] = useState(false);
  const [savingFloor, setSavingFloor] = useState(false);

  const empty = {
    date: new Date().toISOString().slice(0, 10), type: "Receipt", product_id: "",
    qty: 1, unit: "pc", warehouse: "", to_warehouse: "", source_doc: "", reason: "",
  };
  const [form, setForm] = useState(empty);
  const floorEmpty = { name: "", color: "" };
  const [floorForm, setFloorForm] = useState(floorEmpty);

  const load = async () => {
    const [m, s, inv, fl] = await Promise.all([
      api.get("/stock-movements"),
      api.get("/stock-movements/summary"),
      api.get("/inventory"),
      api.get("/floors"),
    ]);
    setMoves(m.data); setSummary(s.data); setInventory(inv.data); setFloors(fl.data);
  };
  useEffect(() => { load(); }, []);

  const invBySku = useMemo(() => Object.fromEntries(inventory.map((i) => [i.sku, i.name])), [inventory]);
  const visibleMoves = useMemo(() => {
    if (!selectedFloor) return moves;
    return moves.filter((m) => m.warehouse === selectedFloor || m.to_warehouse === selectedFloor);
  }, [moves, selectedFloor]);
  const floorByName = useMemo(() => Object.fromEntries(floors.map((f) => [f.name, f])), [floors]);

  const save = async () => {
    if (saving) return;
    if (!form.product_id) { toast.error("Pick a product"); return; }
    setSaving(true);
    try { await api.post("/stock-movements", form); toast.success("Movement recorded"); setShow(false); setForm(empty); load(); }
    catch { toast.error("Save failed"); }
    finally { setSaving(false); }
  };
  const remove = async (id) => { if (!window.confirm("Delete this movement?")) return; await api.delete(`/stock-movements/${id}`); load(); };
  const removeFloor = async (f) => {
    if (!window.confirm(`Delete floor "${f.name}"? Existing movements keep the plain text, just without a color.`)) return;
    await api.delete(`/floors/${f.id}`);
    load();
  };

  const saveFloor = async () => {
    if (savingFloor) return;
    if (!floorForm.name.trim()) { toast.error("Name is required"); return; }
    setSavingFloor(true);
    try {
      const { data } = await api.post("/floors", floorForm);
      toast.success("Floor created");
      setShowFloorModal(false); setFloorForm(floorEmpty);
      await load();
      setForm((f) => ({ ...f, warehouse: data.name }));
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Save failed");
    } finally {
      setSavingFloor(false);
    }
  };

  return (
    <>
      <Topbar title="Stock Ledger" subtitle={`${summary?.total_movements || 0} movements · ${summary?.products?.length || 0} products tracked`} onAdd={() => { setForm(empty); setShow(true); }} addLabel="New Movement" />
      <div className="p-6" data-testid="stock-ledger-page">
        <div className="flex items-center justify-between border-b border-[var(--border)] mb-4">
          <div className="flex gap-1">
            {[["onhand", "On Hand"], ["ledger", "Movement Log"]].map(([k, lbl]) => (
              <button key={k} onClick={() => setTab(k)} className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${tab === k ? "border-[var(--brand)] text-[var(--brand)]" : "border-transparent text-[var(--ink-3)]"}`}>{lbl}</button>
            ))}
          </div>
          <button onClick={() => { setFloorForm(floorEmpty); setShowFloorModal(true); }} className="btn-ghost text-xs mb-2" data-testid="floor-add-btn">
            <Plus size={13} /> New Floor
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2 mb-4" data-testid="floor-legend">
          <span className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">Floors</span>
          {floors.length === 0 && <span className="text-xs text-[var(--ink-3)]">None yet — create one above.</span>}
          {floors.map((f) => (
            <span key={f.id} className="group inline-flex items-center">
              <button
                type="button"
                onClick={() => { setSelectedFloor((cur) => (cur === f.name ? "" : f.name)); setTab("ledger"); }}
                className={`rounded-full transition ${selectedFloor === f.name ? "ring-2 ring-offset-1 ring-[var(--ink)]" : "hover:opacity-80"}`}
                title={`Filter Movement Log by "${f.name}"`}
                data-testid={`floor-filter-${f.id}`}
              >
                <FloorBadge name={f.name} floorByName={floorByName} />
              </button>
              <button
                onClick={() => removeFloor(f)}
                className="opacity-0 group-hover:opacity-100 -ml-1.5 p-0.5 rounded-full hover:bg-[var(--danger-soft)] text-[var(--danger)] transition"
                title={`Delete "${f.name}"`}
                data-testid={`floor-delete-${f.id}`}
              >
                <X size={11} />
              </button>
            </span>
          ))}
          {selectedFloor && (
            <button onClick={() => setSelectedFloor("")} className="text-[11px] text-[var(--ink-3)] hover:text-[var(--ink)] underline ml-1" data-testid="floor-filter-clear">
              Clear filter
            </button>
          )}
        </div>

        {tab === "onhand" && (
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">SKU</th>
                  <th className="text-left font-semibold px-4 py-2.5">Product</th>
                  <th className="text-right font-semibold px-4 py-2.5">On Hand</th>
                </tr>
              </thead>
              <tbody>
                {(summary?.products || []).map((p) => (
                  <tr key={p.product_id} className="border-t border-[var(--border-light)]">
                    <td className="px-4 py-2.5 font-mono text-xs">{p.product_id}</td>
                    <td className="px-4 py-2.5">{p.name}</td>
                    <td className={`px-4 py-2.5 text-right font-mono font-semibold ${p.on_hand < 0 ? "text-[var(--danger)]" : "text-[var(--ink)]"}`}>{p.on_hand}</td>
                  </tr>
                ))}
                {(summary?.products || []).length === 0 && <tr><td colSpan="3" className="text-center py-10 text-[var(--ink-3)]">No movements yet — record the first receipt.</td></tr>}
              </tbody>
            </table>
          </div>
        )}

        {tab === "ledger" && (
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[var(--surface-2)]">
                  <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                    <th className="text-left font-semibold px-4 py-2.5">Ref</th>
                    <th className="text-left font-semibold px-4 py-2.5">Date</th>
                    <th className="text-left font-semibold px-4 py-2.5">Type</th>
                    <th className="text-left font-semibold px-4 py-2.5">Product</th>
                    <th className="text-right font-semibold px-4 py-2.5">Qty</th>
                    <th className="text-left font-semibold px-4 py-2.5">Warehouse</th>
                    <th className="text-left font-semibold px-4 py-2.5">Reason</th>
                    <th className="w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  {visibleMoves.map((m) => {
                    const Icon = TYPE_ICON[m.type] || SlidersHorizontal;
                    return (
                      <tr key={m.id} className="border-t border-[var(--border-light)]">
                        <td className="px-4 py-2.5 font-mono text-xs">{m.movement_no}</td>
                        <td className="px-4 py-2.5 text-[var(--ink-2)]">{fmtDate(m.date)}</td>
                        <td className="px-4 py-2.5"><span className={`inline-flex items-center gap-1 ${TYPE_COLOR[m.type]}`}><Icon size={13} />{m.type}</span></td>
                        <td className="px-4 py-2.5">{invBySku[m.product_id] || m.product_id}</td>
                        <td className="px-4 py-2.5 text-right font-mono">{m.qty} {m.unit}</td>
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-1.5">
                            <FloorBadge name={m.warehouse} floorByName={floorByName} />
                            {m.to_warehouse && <>
                              <span className="text-[var(--ink-3)]">→</span>
                              <FloorBadge name={m.to_warehouse} floorByName={floorByName} />
                            </>}
                          </div>
                        </td>
                        <td className="px-4 py-2.5 text-[var(--ink-3)] text-xs">{m.reason}</td>
                        <td className="px-2 py-2.5"><button onClick={() => remove(m.id)} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button></td>
                      </tr>
                    );
                  })}
                  {visibleMoves.length === 0 && (
                    <tr><td colSpan="8" className="text-center py-10 text-[var(--ink-3)]">
                      {selectedFloor ? `No movements on "${selectedFloor}"` : "No movements"}
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div className="bg-white rounded-xl border border-[var(--border)] w-full max-w-lg shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">New Stock Movement</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-4">
              <Sel l="Type" v={form.type} opts={TYPES} oc={(v) => setForm({ ...form, type: v })} />
              <F l="Date" t="date" v={form.date} oc={(v) => setForm({ ...form, date: v })} />
              <div className="col-span-2">
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Product</label>
                <select value={form.product_id} onChange={(e) => setForm({ ...form, product_id: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
                  <option value="">Select a SKU…</option>
                  {inventory.map((i) => <option key={i.sku} value={i.sku}>{i.sku} — {i.name}</option>)}
                </select>
              </div>
              <F l="Qty" t="number" v={form.qty} oc={(v) => setForm({ ...form, qty: parseFloat(v) || 0 })} />
              <F l="Unit" v={form.unit} oc={(v) => setForm({ ...form, unit: v })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Warehouse / Floor</label>
                <select value={form.warehouse} onChange={(e) => setForm({ ...form, warehouse: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
                  <option value="">Select a floor…</option>
                  {floors.map((f) => <option key={f.id} value={f.name}>{f.name}</option>)}
                </select>
              </div>
              {form.type === "Transfer" && (
                <div>
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">To Warehouse / Floor</label>
                  <select value={form.to_warehouse} onChange={(e) => setForm({ ...form, to_warehouse: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
                    <option value="">Select a floor…</option>
                    {floors.map((f) => <option key={f.id} value={f.name}>{f.name}</option>)}
                  </select>
                </div>
              )}
              <F l="Source doc" v={form.source_doc} oc={(v) => setForm({ ...form, source_doc: v })} />
              <F l="Reason" v={form.reason} oc={(v) => setForm({ ...form, reason: v })} cls="col-span-2" />
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary disabled:opacity-60" onClick={save} disabled={saving}>{saving ? "Saving…" : "Record"}</button>
            </div>
          </div>
        </div>
      )}

      {showFloorModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowFloorModal(false)}>
          <div className="bg-white rounded-xl border border-[var(--border)] w-full max-w-sm shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">New Floor</h3>
              <button onClick={() => setShowFloorModal(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-4">
              <F l="Floor / Warehouse name" v={floorForm.name} oc={(v) => setFloorForm({ ...floorForm, name: v })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-2">Colour</label>
                <div className="flex flex-wrap gap-2">
                  {PALETTE_KEYS.map((k) => (
                    <button
                      key={k}
                      type="button"
                      onClick={() => setFloorForm({ ...floorForm, color: k })}
                      title={k}
                      className={`w-8 h-8 rounded-full ${FLOOR_STYLES[k].swatch} ${floorForm.color === k ? "ring-2 ring-offset-2 ring-[var(--ink)]" : ""}`}
                      data-testid={`floor-color-${k}`}
                    />
                  ))}
                </div>
                {!floorForm.color && <div className="text-[11px] text-[var(--ink-3)] mt-2">No colour picked — one will be assigned automatically.</div>}
              </div>
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShowFloorModal(false)}>Cancel</button>
              <button className="btn-primary disabled:opacity-60" onClick={saveFloor} disabled={savingFloor} data-testid="floor-save">
                {savingFloor ? "Saving…" : "Create Floor"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function F({ l, v, oc, t = "text", cls = "" }) {
  return (
    <div className={cls}>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <input type={t} value={v ?? ""} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" />
    </div>
  );
}
function Sel({ l, v, opts, oc }) {
  return (
    <div>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <select value={v} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
        {opts.map((o) => <option key={o}>{o}</option>)}
      </select>
    </div>
  );
}
