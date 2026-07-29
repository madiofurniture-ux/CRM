import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import api from "@/lib/api";
import { fmtDate, inrFull } from "@/lib/format";
import { toast } from "sonner";
import { Phone, Calendar, X, Trash2 } from "lucide-react";

const STAGES = ["New", "Contacted", "Qualified", "Quoted", "Negotiation", "Won", "Lost"];

export default function Leads() {
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState("");
  const [fStage, setFStage] = useState("All");
  const [show, setShow] = useState(false);
  const empty = {
    date: new Date().toISOString().slice(0, 10), name: "", phone: "", source: "Walk-in",
    stage: "New", follow_up_date: "", remarks: "", assigned_to: "", value: 0,
  };
  const [form, setForm] = useState(empty);

  const load = async () => { const { data } = await api.get("/leads"); setRows(data); };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return rows.filter((r) =>
      (fStage === "All" || r.stage === fStage) &&
      (!q || r.name.toLowerCase().includes(q) || (r.remarks || "").toLowerCase().includes(q))
    );
  }, [rows, search, fStage]);

  const today = new Date().toISOString().slice(0, 10);

  const save = async () => {
    try { await api.post("/leads", form); toast.success("Lead added"); setShow(false); setForm(empty); load(); }
    catch { toast.error("Save failed"); }
  };
  const updateStage = async (l, stage) => {
    await api.put(`/leads/${l.id}`, { ...l, stage });
    setRows((p) => p.map((x) => x.id === l.id ? { ...x, stage } : x));
  };
  const remove = async (id) => { if (!window.confirm("Delete?")) return; await api.delete(`/leads/${id}`); load(); };

  return (
    <>
      <Topbar title="Leads" subtitle={`${filtered.length} leads · pipeline ${inrFull(filtered.reduce((a, b) => a + (b.value || 0), 0))}`} onAdd={() => { setForm(empty); setShow(true); }} addLabel="Add Lead" />
      <div className="p-6" data-testid="leads-page">
        <div className="flex flex-wrap gap-2 mb-4">
          <input placeholder="Search lead, remarks…" value={search} onChange={(e) => setSearch(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] w-72" data-testid="leads-search" />
          <select value={fStage} onChange={(e) => setFStage(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
            <option>All</option>
            {STAGES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Date</th>
                  <th className="text-left font-semibold px-4 py-2.5">Name</th>
                  <th className="text-left font-semibold px-4 py-2.5">Phone</th>
                  <th className="text-left font-semibold px-4 py-2.5">Source</th>
                  <th className="text-left font-semibold px-4 py-2.5">Stage</th>
                  <th className="text-left font-semibold px-4 py-2.5">Follow up</th>
                  <th className="text-left font-semibold px-4 py-2.5">Assigned</th>
                  <th className="text-right font-semibold px-4 py-2.5">Value</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((l) => {
                  const overdue = l.follow_up_date && l.follow_up_date < today && !["Won", "Lost"].includes(l.stage);
                  return (
                    <tr key={l.id} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50">
                      <td className="px-4 py-3 text-[var(--ink-2)] whitespace-nowrap">{fmtDate(l.date)}</td>
                      <td className="px-4 py-3 font-medium">{l.name}</td>
                      <td className="px-4 py-3 font-mono text-xs text-[var(--ink-2)]">
                        {l.phone && <span className="inline-flex items-center gap-1"><Phone size={11} className="text-[var(--ink-3)]" />{l.phone}</span>}
                      </td>
                      <td className="px-4 py-3 text-[var(--ink-2)]">{l.source}</td>
                      <td className="px-4 py-3">
                        <select value={l.stage} onChange={(e) => updateStage(l, e.target.value)} className="px-2 py-1 rounded-md border border-[var(--border)] bg-white text-xs">
                          {STAGES.map((s) => <option key={s}>{s}</option>)}
                        </select>
                      </td>
                      <td className={`px-4 py-3 whitespace-nowrap ${overdue ? "text-[var(--danger)] font-semibold" : "text-[var(--ink-2)]"}`}>
                        <span className="inline-flex items-center gap-1"><Calendar size={11} />{fmtDate(l.follow_up_date)}</span>
                      </td>
                      <td className="px-4 py-3 text-[var(--ink-2)]">{l.assigned_to}</td>
                      <td className="px-4 py-3 text-right font-mono">{inrFull(l.value)}</td>
                      <td className="px-2 py-3"><button onClick={() => remove(l.id)} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button></td>
                    </tr>
                  );
                })}
                {filtered.length === 0 && <tr><td colSpan="9" className="text-center py-10 text-[var(--ink-3)]">No leads</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div className="bg-white rounded-xl border border-[var(--border)] w-full max-w-xl shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">New Lead</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-4">
              <Fld l="Date" t="date" v={form.date} oc={(v) => setForm({ ...form, date: v })} />
              <Fld l="Name" v={form.name} oc={(v) => setForm({ ...form, name: v })} t2="lf-name" />
              <Fld l="Phone" v={form.phone} oc={(v) => setForm({ ...form, phone: v })} />
              <Fld l="Source" v={form.source} oc={(v) => setForm({ ...form, source: v })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Stage</label>
                <select value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
                  {STAGES.map((s) => <option key={s}>{s}</option>)}
                </select>
              </div>
              <Fld l="Follow up" t="date" v={form.follow_up_date} oc={(v) => setForm({ ...form, follow_up_date: v })} />
              <Fld l="Assigned to" v={form.assigned_to} oc={(v) => setForm({ ...form, assigned_to: v })} />
              <Fld l="Value" t="number" v={form.value} oc={(v) => setForm({ ...form, value: parseFloat(v) || 0 })} />
              <Fld l="Remarks" v={form.remarks} oc={(v) => setForm({ ...form, remarks: v })} cls="col-span-2" />
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary" onClick={save} data-testid="lead-save">Add Lead</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function Fld({ l, v, oc, t = "text", cls = "", t2 }) {
  return (
    <div className={cls}>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <input type={t} value={v} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" data-testid={t2} />
    </div>
  );
}
