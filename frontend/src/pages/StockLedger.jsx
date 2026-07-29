import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { X, Trash2, ArrowDownCircle, ArrowUpCircle, Repeat, SlidersHorizontal } from "lucide-react";

const TYPES = ["Receipt", "Issue", "Transfer", "Adjustment", "Return"];
const TYPE_ICON = { Receipt: ArrowDownCircle, Return: ArrowDownCircle, Issue: ArrowUpCircle, Transfer: Repeat, Adjustment: SlidersHorizontal };
const TYPE_COLOR = {
  Receipt: "text-[var(--moss)]", Return: "text-[var(--moss)]",
  Issue: "text-[var(--danger)]", Transfer: "text-[var(--brand)]", Adjustment: "text-[var(--warn)]",
};

export default function StockLedger() {
  const [moves, setMoves] = useState([]);
  const [summary, setSummary] = useState(null);
  const [inventory, setInventory] = useState([]);
  const [show, setShow] = useState(false);
  const [tab, setTab] = useState("onhand");

  const empty = {
    date: new Date().toISOString().slice(0, 10), type: "Receipt", product_id: "",
    qty: 1, unit: "pc", warehouse: "Main", to_warehouse: "", source_doc: "", reason: "",
  };
  const [form, setForm] = useState(empty);

  const load = async () => {
    const [m, s, inv] = await Promise.all([
      api.get("/stock-movements"),
      api.get("/stock-movements/summary"),
      api.get("/inventory"),
    ]);
    setMoves(m.data); setSummary(s.data); setInventory(inv.data);
  };
  useEffect(() => { load(); }, []);

  const invBySku = useMemo(() => Object.fromEntries(inventory.map((i) => [i.sku, i.name])), [inventory]);

  const save = async () => {
    if (!form.product_id) { toast.error("Pick a product"); return; }
    try { await api.post("/stock-movements", form); toast.success("Movement recorded"); setShow(false); setForm(empty); load(); }
    catch { toast.error("Save failed"); }
  };
  const remove = async (id) => { if (!window.confirm("Delete this movement?")) return; await api.delete(`/stock-movements/${id}`); load(); };

  return (
    <>
      <Topbar title="Stock Ledger" subtitle={`${summary?.total_movements || 0} movements · ${summary?.products?.length || 0} products tracked`} onAdd={() => { setForm(empty); setShow(true); }} addLabel="New Movement" />
      <div className="p-6" data-testid="stock-ledger-page">
        <div className="flex gap-1 border-b border-[var(--border)] mb-4">
          {[["onhand", "On Hand"], ["ledger", "Movement Log"]].map(([k, lbl]) => (
            <button key={k} onClick={() => setTab(k)} className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${tab === k ? "border-[var(--brand)] text-[var(--brand)]" : "border-transparent text-[var(--ink-3)]"}`}>{lbl}</button>
          ))}
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
                  {moves.map((m) => {
                    const Icon = TYPE_ICON[m.type] || SlidersHorizontal;
                    return (
                      <tr key={m.id} className="border-t border-[var(--border-light)]">
                        <td className="px-4 py-2.5 font-mono text-xs">{m.movement_no}</td>
                        <td className="px-4 py-2.5 text-[var(--ink-2)]">{fmtDate(m.date)}</td>
                        <td className="px-4 py-2.5"><span className={`inline-flex items-center gap-1 ${TYPE_COLOR[m.type]}`}><Icon size={13} />{m.type}</span></td>
                        <td className="px-4 py-2.5">{invBySku[m.product_id] || m.product_id}</td>
                        <td className="px-4 py-2.5 text-right font-mono">{m.qty} {m.unit}</td>
                        <td className="px-4 py-2.5 text-[var(--ink-2)]">{m.warehouse}{m.to_warehouse ? ` → ${m.to_warehouse}` : ""}</td>
                        <td className="px-4 py-2.5 text-[var(--ink-3)] text-xs">{m.reason}</td>
                        <td className="px-2 py-2.5"><button onClick={() => remove(m.id)} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button></td>
                      </tr>
                    );
                  })}
                  {moves.length === 0 && <tr><td colSpan="8" className="text-center py-10 text-[var(--ink-3)]">No movements</td></tr>}
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
              <F l="Warehouse" v={form.warehouse} oc={(v) => setForm({ ...form, warehouse: v })} />
              {form.type === "Transfer" && <F l="To warehouse" v={form.to_warehouse} oc={(v) => setForm({ ...form, to_warehouse: v })} />}
              <F l="Source doc" v={form.source_doc} oc={(v) => setForm({ ...form, source_doc: v })} />
              <F l="Reason" v={form.reason} oc={(v) => setForm({ ...form, reason: v })} cls="col-span-2" />
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary" onClick={save}>Record</button>
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
