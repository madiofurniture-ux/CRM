import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import FilterChips from "@/components/FilterChips";
import JourneyDrawer from "@/components/JourneyDrawer";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { X, IndianRupee, Compass, MessageCircle } from "lucide-react";

export default function Sales() {
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState("");
  const [fDiv, setFDiv] = useState("All");
  const [view, setView] = useState("all");
  const [jny, setJny] = useState(null);
  const [pay, setPay] = useState(null); // sale being paid

  const me = JSON.parse(localStorage.getItem("madio_user") || "{}")?.name || "";

  const load = () => api.get("/sales").then((r) => setRows(r.data));
  useEffect(() => { load(); }, []);

  const pred = (v) => (s) => {
    if (v === "all") return true;
    if (v === "unpaid") return (s.balance || 0) > 0;
    if (v === "mine") return s.by_user === me;
    if (v === "delivered") return s.stage === "Delivered";
    return true;
  };
  const views = useMemo(() => [
    { key: "all", label: "All", count: rows.length },
    { key: "unpaid", label: "💳 Unpaid", count: rows.filter(pred("unpaid")).length },
    { key: "delivered", label: "✅ Delivered", count: rows.filter(pred("delivered")).length },
    { key: "mine", label: "👤 My Sales", count: rows.filter(pred("mine")).length },
  ], [rows, me]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    let list = rows.filter(pred(view)).filter((r) =>
      (fDiv === "All" || r.division === fDiv) &&
      (!q || (r.customer || "").toLowerCase().includes(q) || (r.sale_no || "").toLowerCase().includes(q))
    );
    if (view === "unpaid") list = [...list].sort((a, b) => (b.balance || 0) - (a.balance || 0));
    return list;
  }, [rows, search, fDiv, view]);

  const totals = useMemo(() => ({
    value: filtered.reduce((a, b) => a + (b.value || 0), 0),
    balance: filtered.reduce((a, b) => a + (b.balance || 0), 0),
  }), [filtered]);

  const remind = (s) => {
    const ph = String(s.phone || "").replace(/\D/g, "").slice(-10);
    if (!ph) { toast.error("No phone on this sale (or its linked quote)"); return; }
    const first = String(s.customer || "").split(" ")[0];
    const msg = `Hi ${first}, a friendly reminder about the pending balance of ${inrFull(s.balance)} for your order ${s.sale_no}. Please let us know a convenient time for payment.`;
    window.open(`https://wa.me/91${ph}?text=${encodeURIComponent(msg)}`, "_blank");
  };

  return (
    <>
      <Topbar title="Sales Register" subtitle={`${filtered.length} sales · ${inrFull(totals.value)} · ${inrFull(totals.balance)} outstanding`} />
      <div className="p-6" data-testid="sales-page">
        <div className="flex flex-col gap-3 mb-4">
          <FilterChips views={views} active={view} onChange={setView} />
          <div className="flex flex-wrap gap-2">
            <input placeholder="Search customer, sale no…" value={search} onChange={(e) => setSearch(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] w-72" data-testid="sales-search" />
            <select value={fDiv} onChange={(e) => setFDiv(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
              <option>All</option><option>Furniture</option><option>MAP</option><option>D&W</option>
            </select>
          </div>
        </div>
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Sale No</th>
                  <th className="text-left font-semibold px-4 py-2.5">Date</th>
                  <th className="text-left font-semibold px-4 py-2.5">Customer</th>
                  <th className="text-left font-semibold px-4 py-2.5">Division</th>
                  <th className="text-left font-semibold px-4 py-2.5">Stage</th>
                  <th className="text-right font-semibold px-4 py-2.5">Value</th>
                  <th className="text-right font-semibold px-4 py-2.5">Paid</th>
                  <th className="text-right font-semibold px-4 py-2.5">Balance</th>
                  <th className="w-28"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => (
                  <tr key={s.id} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50">
                    <td className="px-4 py-3 font-mono text-xs">{s.sale_no}{s.quote_ref && <div className="text-[10px] text-[var(--ink-3)]">← {s.quote_ref}</div>}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{fmtDate(s.date)}</td>
                    <td className="px-4 py-3 font-medium">{s.customer}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{s.division}</td>
                    <td className="px-4 py-3"><StageBadge stage={s.stage} /></td>
                    <td className="px-4 py-3 text-right font-mono font-semibold">{inrFull(s.value)}</td>
                    <td className="px-4 py-3 text-right font-mono text-[var(--moss)]">{inrFull(s.paid)}</td>
                    <td className={`px-4 py-3 text-right font-mono ${s.balance > 0 ? "text-[var(--danger)] font-semibold" : "text-[var(--ink-3)]"}`}>{inrFull(s.balance)}</td>
                    <td className="px-2 py-3">
                      <div className="flex items-center gap-1">
                        {s.phone && <button onClick={() => setJny({ phone: s.phone, name: s.customer })} title="Journey" className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]"><Compass size={13} /></button>}
                        {s.balance > 0 && <button onClick={() => setPay(s)} title="Record payment" className="p-1.5 rounded-md hover:bg-[var(--moss-soft)] text-[var(--moss)]"><IndianRupee size={13} /></button>}
                        {s.balance > 0 && <button onClick={() => remind(s)} title="Payment reminder" className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]"><MessageCircle size={13} /></button>}
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && <tr><td colSpan="9" className="text-center py-10 text-[var(--ink-3)]">No sales</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {pay && <PaymentDialog sale={pay} onClose={() => setPay(null)} onDone={() => { setPay(null); load(); }} />}
      <JourneyDrawer phone={jny?.phone} name={jny?.name} onClose={() => setJny(null)} />
    </>
  );
}

function PaymentDialog({ sale, onClose, onDone }) {
  const [form, setForm] = useState({
    amount: sale.balance || 0, date: new Date().toISOString().slice(0, 10),
    mode: "Cash", kind: "Part", received_by: "",
  });
  const save = async () => {
    try {
      await api.post("/payments", {
        ...form, division: sale.division, direction: "In",
        against_sale_id: sale.id, against_quote_no: sale.quote_ref || "", phone: sale.phone || "",
      });
      toast.success("Payment recorded");
      onDone();
    } catch { toast.error("Save failed"); }
  };
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl border border-[var(--border)] w-full max-w-md shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <div>
            <h3 className="font-heading font-semibold text-lg">Record Payment</h3>
            <div className="text-xs text-[var(--ink-3)]">{sale.sale_no} · {sale.customer} · balance {inrFull(sale.balance)}</div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
        </div>
        <div className="p-5 grid grid-cols-2 gap-4">
          <F l="Amount" t="number" v={form.amount} oc={(v) => setForm({ ...form, amount: parseFloat(v) || 0 })} />
          <F l="Date" t="date" v={form.date} oc={(v) => setForm({ ...form, date: v })} />
          <S l="Mode" v={form.mode} opts={["Cash", "Bank", "UPI", "Cheque"]} oc={(v) => setForm({ ...form, mode: v })} />
          <S l="Kind" v={form.kind} opts={["Advance", "Part", "Final"]} oc={(v) => setForm({ ...form, kind: v })} />
          <F l="Received by" v={form.received_by} oc={(v) => setForm({ ...form, received_by: v })} cls="col-span-2" />
        </div>
        <div className="px-5 py-4 border-t flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={save}>Save Payment</button>
        </div>
      </div>
    </div>
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
function S({ l, v, opts, oc }) {
  return (
    <div>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <select value={v} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
        {opts.map((o) => <option key={o}>{o}</option>)}
      </select>
    </div>
  );
}
