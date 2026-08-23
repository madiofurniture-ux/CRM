import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import api from "@/lib/api";
import { fmtDate, inrFull } from "@/lib/format";
import { toast } from "sonner";
import { Trash2, X, Phone } from "lucide-react";

const STAGES = ["New", "Qualified", "Quoted", "Negotiation", "Won", "Lost", "Delivered"];

export default function Visitors() {
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState("");
  const [fStage, setFStage] = useState("All");
  const [show, setShow] = useState(false);
  const empty = {
    date: new Date().toISOString().slice(0, 10), name: "", location: "", reference: "",
    phone: "", requirement: "", attend_person: "", remarks: "", status: "New", stage: "New", ticket_value: 0,
  };
  const [form, setForm] = useState(empty);

  const load = async () => { const { data } = await api.get("/visitors"); setRows(data); };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return rows.filter((r) => {
      const stage = (r.stage || "New").trim().toLowerCase();
      return (fStage === "All" || stage === fStage.toLowerCase()) &&
        (!q || (r.name || "").toLowerCase().includes(q) || (r.requirement || "").toLowerCase().includes(q) || (r.reference || "").toLowerCase().includes(q));
    });
  }, [rows, search, fStage]);

  const save = async () => {
    try { await api.post("/visitors", form); toast.success("Visitor logged"); setShow(false); setForm(empty); load(); }
    catch { toast.error("Save failed"); }
  };
  const updateStage = async (v, stage) => {
    await api.put(`/visitors/${v.id}`, { ...v, stage });
    setRows((p) => p.map((x) => x.id === v.id ? { ...x, stage } : x));
  };
  const remove = async (id) => { if (!window.confirm("Delete?")) return; await api.delete(`/visitors/${id}`); load(); };

  return (
    <>
      <Topbar title="Visitors" subtitle={`${filtered.length} walk-ins · today's lobby`} onAdd={() => { setForm(empty); setShow(true); }} addLabel="Log Visitor" />
      <div className="p-6" data-testid="visitors-page">
        <div className="flex flex-wrap gap-2 mb-4">
          <input placeholder="Search name, requirement, reference…" value={search} onChange={(e) => setSearch(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] w-80" data-testid="visitors-search" />
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
                  <th className="text-left font-semibold px-4 py-2.5">Reference</th>
                  <th className="text-left font-semibold px-4 py-2.5">Requirement</th>
                  <th className="text-left font-semibold px-4 py-2.5">Attended by</th>
                  <th className="text-left font-semibold px-4 py-2.5">Stage</th>
                  <th className="text-right font-semibold px-4 py-2.5">Ticket</th>
                  <th className="w-12"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((v) => (
                  <tr key={v.id} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50">
                    <td className="px-4 py-3 text-[var(--ink-2)] whitespace-nowrap">{fmtDate(v.date)}</td>
                    <td className="px-4 py-3 font-medium">{v.name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-[var(--ink-2)]">
                      {v.phone && (
                        <span className="inline-flex items-center gap-1">
                          <Phone size={11} className="text-[var(--ink-3)]" /> {v.phone}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{v.reference}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)] max-w-[200px] truncate">{v.requirement}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{v.attend_person}</td>
                    <td className="px-4 py-3">
                      <select value={v.stage || "New"} onChange={(e) => updateStage(v, e.target.value)} className="px-2 py-1 rounded-md border border-[var(--border)] bg-white text-xs">
                        {STAGES.map((s) => <option key={s}>{s}</option>)}
                      </select>
                    </td>
                    <td className="px-4 py-3 text-right font-mono">{inrFull(v.ticket_value)}</td>
                    <td className="px-2 py-3">
                      <button onClick={() => remove(v.id)} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && <tr><td colSpan="9" className="text-center py-10 text-[var(--ink-3)]">No visitors</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div className="bg-white rounded-xl border border-[var(--border)] w-full max-w-xl shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">Log Visitor</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-4">
              <Fld l="Date" t="date" v={form.date} oc={(v) => setForm({ ...form, date: v })} t2="vf-date" />
              <Fld l="Name" v={form.name} oc={(v) => setForm({ ...form, name: v })} t2="vf-name" />
              <Fld l="Phone" v={form.phone} oc={(v) => setForm({ ...form, phone: v })} t2="vf-phone" />
              <Fld l="Reference" v={form.reference} oc={(v) => setForm({ ...form, reference: v })} t2="vf-ref" />
              <Fld l="Requirement" v={form.requirement} oc={(v) => setForm({ ...form, requirement: v })} cls="col-span-2" t2="vf-req" />
              <Fld l="Attended by" v={form.attend_person} oc={(v) => setForm({ ...form, attend_person: v })} t2="vf-by" />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Stage</label>
                <select value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value, status: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm" data-testid="vf-stage">
                  {STAGES.map((s) => <option key={s}>{s}</option>)}
                </select>
              </div>
              <Fld l="Remarks" v={form.remarks} oc={(v) => setForm({ ...form, remarks: v })} cls="col-span-2" t2="vf-remarks" />
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary" onClick={save} data-testid="visitor-save">Log Visitor</button>
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
