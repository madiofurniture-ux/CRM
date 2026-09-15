import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import KpiCard from "@/components/KpiCard";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { ArrowDown, ArrowUp, Wallet, Trash2, X } from "lucide-react";

const CATEGORIES = ["Opening", "Sale", "Refund", "Fuel", "Food", "Transport", "Repair", "Stationery", "Courier", "Utilities", "Misc"];
const MODES = ["Cash", "UPI", "Bank"];

export default function PettyCash() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("All");
  const [show, setShow] = useState(false);
  const [fKind, setFKind] = useState("All");
  const [saving, setSaving] = useState(false);
  const emptyFor = (kind) => ({ date: new Date().toISOString().slice(0, 10), kind, category: "Misc", party: "", description: "", amount: 0, mode: "Cash", by_user: "", ref: "", project_id: projectId !== "All" ? projectId : "" });
  const [form, setForm] = useState(emptyFor("Out"));

  const load = async () => {
    const { data } = await api.get("/petty-cash", { params: projectId !== "All" ? { project_id: projectId } : {} });
    setRows(data);
  };
  useEffect(() => { load(); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { api.get("/projects").then(({ data }) => setProjects(data)).catch(() => setProjects([])); }, []);

  const sorted = useMemo(() => [...rows].sort((a, b) => a.date.localeCompare(b.date) || a.created_at.localeCompare(b.created_at)), [rows]);
  let running = 0;
  const withBalance = sorted.map((r) => {
    running += r.kind === "In" ? r.amount : -r.amount;
    return { ...r, balance: running };
  });
  const view = fKind === "All" ? withBalance.slice().reverse() : withBalance.filter((r) => r.kind === fKind).reverse();

  const totalIn = withBalance.filter((r) => r.kind === "In").reduce((a, b) => a + b.amount, 0);
  const totalOut = withBalance.filter((r) => r.kind === "Out").reduce((a, b) => a + b.amount, 0);
  const closing = totalIn - totalOut;

  const save = async () => {
    if (saving) return;
    setSaving(true);
    try { await api.post("/petty-cash", form); toast.success("Entry added"); setShow(false); setForm(emptyFor("Out")); load(); }
    catch { toast.error("Save failed"); }
    finally { setSaving(false); }
  };
  const remove = async (id) => { if (!window.confirm("Delete entry?")) return; await api.delete(`/petty-cash/${id}`); load(); };
  const openEntry = (kind) => { setForm(emptyFor(kind)); setShow(true); };

  return (
    <>
      <Topbar title="Petty Cash Ledger" subtitle={`Closing: ${inrFull(closing)}`} onAdd={() => openEntry("Out")} addLabel="New Entry" />
      <div className="p-4 md:p-6 space-y-6" data-testid="petty-page">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Project</label>
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className="px-3 py-2 text-sm rounded-xl bg-white border border-[var(--border)] outline-none focus:border-[var(--brand)] min-w-[220px]"
              data-testid="petty-project-filter"
            >
              <option value="All">All Projects</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.customer} · {p.project_no}</option>
              ))}
            </select>
          </div>
          {projectId !== "All" && (
            <div className="flex gap-2">
              <button onClick={() => openEntry("In")} className="btn-primary bg-[var(--moss)] hover:opacity-90 flex items-center gap-1.5" data-testid="petty-cash-in-btn">
                <ArrowDown size={14} /> Cash In
              </button>
              <button onClick={() => openEntry("Out")} className="btn-primary bg-[var(--danger)] hover:opacity-90 flex items-center gap-1.5" data-testid="petty-cash-out-btn">
                <ArrowUp size={14} /> Cash Out
              </button>
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiCard label="Cash In" value={inrFull(totalIn)} accent="moss" icon={ArrowDown} testid="petty-kpi-in" />
          <KpiCard label="Cash Out" value={inrFull(totalOut)} accent="danger" icon={ArrowUp} testid="petty-kpi-out" />
          <KpiCard label={projectId !== "All" ? "Current Balance" : "Closing"} value={inrFull(closing)} accent="brand" icon={Wallet} testid="petty-kpi-balance" />
          <KpiCard label="Entries" value={rows.length} accent="neutral" />
        </div>

        <div className="flex flex-wrap gap-2">
          {["All", "In", "Out"].map((k) => (
            <button key={k} onClick={() => setFKind(k)} className={`px-3 py-1.5 rounded-lg text-sm font-medium ${fKind === k ? "bg-[var(--ink)] text-white" : "bg-[var(--surface)] border border-[var(--border)] text-[var(--ink-2)]"}`} data-testid={`petty-filter-${k}`}>{k}</button>
          ))}
        </div>

        <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Date</th>
                  <th className="text-left font-semibold px-4 py-2.5">Kind</th>
                  <th className="text-left font-semibold px-4 py-2.5">Category</th>
                  <th className="text-left font-semibold px-4 py-2.5">Party</th>
                  <th className="text-left font-semibold px-4 py-2.5">Description</th>
                  <th className="text-left font-semibold px-4 py-2.5 hidden md:table-cell">Mode</th>
                  <th className="text-left font-semibold px-4 py-2.5 hidden lg:table-cell">Logged By</th>
                  <th className="text-right font-semibold px-4 py-2.5">Amount</th>
                  <th className="text-right font-semibold px-4 py-2.5">Balance</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {view.map((r) => (
                  <tr key={r.id} className="border-t border-[var(--border-light)]">
                    <td className="px-4 py-3 text-[var(--ink-2)] whitespace-nowrap">{fmtDate(r.date)}</td>
                    <td className="px-4 py-3">
                      <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${r.kind === "In" ? "bg-[var(--moss-soft)] text-[var(--moss)]" : "bg-[var(--danger-soft)] text-[var(--danger)]"}`}>
                        {r.kind === "In" ? "IN" : "OUT"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{r.category}</td>
                    <td className="px-4 py-3">{r.party || "—"}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)] max-w-[240px] truncate">{r.description}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)] hidden md:table-cell">{r.mode}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)] hidden lg:table-cell">{r.by_user || "—"}</td>
                    <td className={`px-4 py-3 text-right font-mono font-semibold ${r.kind === "In" ? "text-[var(--moss)]" : "text-[var(--danger)]"}`}>{inrFull(r.amount)}</td>
                    <td className="px-4 py-3 text-right font-mono">{inrFull(r.balance)}</td>
                    <td className="px-2 py-3"><button onClick={() => remove(r.id)} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button></td>
                  </tr>
                ))}
                {view.length === 0 && <tr><td colSpan="10" className="text-center py-10 text-[var(--ink-3)]">No entries</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-3" onClick={() => setShow(false)}>
          <div className="bg-white rounded-xl border w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">New Petty Cash Entry</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-4">
              <div className="col-span-2 grid grid-cols-2 gap-2">
                <button onClick={() => setForm({ ...form, kind: "In" })} className={`px-3 py-2 rounded-lg font-semibold text-sm ${form.kind === "In" ? "bg-[var(--moss)] text-white" : "bg-[var(--surface-2)] text-[var(--ink-2)]"}`} data-testid="petty-kind-in">Cash In</button>
                <button onClick={() => setForm({ ...form, kind: "Out" })} className={`px-3 py-2 rounded-lg font-semibold text-sm ${form.kind === "Out" ? "bg-[var(--danger)] text-white" : "bg-[var(--surface-2)] text-[var(--ink-2)]"}`} data-testid="petty-kind-out">Cash Out</button>
              </div>
              <F l="Date" t="date" v={form.date} oc={(v) => setForm({ ...form, date: v })} />
              <F l="Amount" t="number" v={form.amount} oc={(v) => setForm({ ...form, amount: parseFloat(v) || 0 })} t2="petty-amt" />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Category</label>
                <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm" data-testid="petty-category">{(form.project_id ? PROJECT_CATEGORIES : CATEGORIES).map((c) => <option key={c}>{c}</option>)}</select>
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Mode</label>
                <select value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">{MODES.map((m) => <option key={m}>{m}</option>)}</select>
              </div>
              <F l="Party" v={form.party} oc={(v) => setForm({ ...form, party: v })} cls="col-span-2" />
              <F l="Description" v={form.description} oc={(v) => setForm({ ...form, description: v })} cls="col-span-2" t2="petty-desc" />
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary disabled:opacity-60" onClick={save} disabled={saving} data-testid="petty-save">{saving ? "Saving…" : "Save"}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
function F({ l, v, oc, t = "text", cls = "", t2 }) {
  return (
    <div className={cls}>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <input type={t} value={v} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" data-testid={t2} />
    </div>
  );
}
