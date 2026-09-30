import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import WhatsAppButton from "@/components/WhatsAppButton";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { useTenantConfig } from "@/context/TenantConfigContext";

export default function Sales() {
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState("");
  const [fDiv, setFDiv] = useState("All");
  const { divisions } = useTenantConfig();

  // A sales order stores no phone of its own; the customer's number lives on
  // the quotation it came from (same lookup the backend uses for the
  // order-confirmed notification). Without quote access the button hides.
  const [phoneByQuote, setPhoneByQuote] = useState({});

  useEffect(() => { api.get("/sales").then((r) => setRows(r.data)); }, []);
  useEffect(() => {
    api.get("/quotes").then(({ data }) => {
      const m = {};
      data.forEach((q) => {
        if (!q.phone) return;
        if (q.id) m[`id:${q.id}`] = q.phone;
        if (q.quote_no) m[`no:${q.quote_no}`] = q.phone;
      });
      setPhoneByQuote(m);
    }).catch(() => setPhoneByQuote({}));
  }, []);
  const phoneOf = (s) => s.phone || phoneByQuote[`id:${s.quote_id}`] || phoneByQuote[`no:${s.quote_ref}`] || "";

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return rows.filter((r) =>
      (fDiv === "All" || r.division === fDiv) &&
      (!q || (r.customer || "").toLowerCase().includes(q) || (r.sale_no || "").toLowerCase().includes(q))
    );
  }, [rows, search, fDiv]);

  const totals = useMemo(() => ({
    value: filtered.reduce((a, b) => a + (b.value || 0), 0),
    paid: filtered.reduce((a, b) => a + (b.paid || 0), 0),
    balance: filtered.reduce((a, b) => a + (b.balance || 0), 0),
  }), [filtered]);

  return (
    <>
      <Topbar title="Sales Register" subtitle={`${filtered.length} sales · ${inrFull(totals.value)} · ₹${totals.balance.toLocaleString("en-IN")} outstanding`} />
      <div className="p-6" data-testid="sales-page">
        <div className="flex flex-wrap gap-2 mb-4">
          <input placeholder="Search…" value={search} onChange={(e) => setSearch(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] w-72" data-testid="sales-search" />
          <select value={fDiv} onChange={(e) => setFDiv(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
            <option>All</option>
            {divisions.map((d) => <option key={d.id} value={d.slug}>{d.slug}</option>)}
          </select>
        </div>
        <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Sale No</th>
                  <th className="text-left font-semibold px-4 py-2.5">Date</th>
                  <th className="text-left font-semibold px-4 py-2.5">Customer</th>
                  <th className="text-left font-semibold px-4 py-2.5">Division</th>
                  <th className="text-left font-semibold px-4 py-2.5">By</th>
                  <th className="text-left font-semibold px-4 py-2.5">Stage</th>
                  <th className="text-right font-semibold px-4 py-2.5">Value</th>
                  <th className="text-right font-semibold px-4 py-2.5">Paid</th>
                  <th className="text-right font-semibold px-4 py-2.5">Balance</th>
                  <th className="px-2 py-2.5"><span className="sr-only">WhatsApp</span></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => (
                  <tr key={s.id} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50">
                    <td className="px-4 py-3 font-mono text-xs">{s.sale_no}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{fmtDate(s.date)}</td>
                    <td className="px-4 py-3 font-medium">{s.customer}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{s.division}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{s.by_user}</td>
                    <td className="px-4 py-3"><StageBadge stage={s.stage} /></td>
                    <td className="px-4 py-3 text-right font-mono font-semibold">{inrFull(s.value)}</td>
                    <td className="px-4 py-3 text-right font-mono text-[var(--moss)]">{inrFull(s.paid)}</td>
                    <td className={`px-4 py-3 text-right font-mono ${s.balance > 0 ? "text-[var(--danger)] font-semibold" : "text-[var(--ink-3)]"}`}>{inrFull(s.balance)}</td>
                    <td className="px-2 py-3">
                      <WhatsAppButton phone={phoneOf(s)} context={s.balance > 0 ? "payment-reminder" : "follow-up"}
                                      customerName={s.customer} ref={s.sale_no} refType="sale" refId={s.id}
                                      testId={`sale-wa-${s.id}`} />
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && <tr><td colSpan="10" className="text-center py-10 text-[var(--ink-3)]">No sales</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
