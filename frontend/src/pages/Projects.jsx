import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { X, Trash2 } from "lucide-react";

// The 8-stage MAP applicator workflow from the live app.
const STAGES = ["Customer Enquiry", "Site Measurement", "Quotation", "Material Allocation",
  "Applicator Assignment", "Site Readiness", "Project Execution", "Payment & Review"];
const DIVISIONS = ["MAP", "D&W", "Furniture"];

export default function Projects() {
  const [rows, setRows] = useState([]);
  const [fStage, setFStage] = useState("All");
  const [show, setShow] = useState(false);
  const empty = {
    division: "MAP", project_type: "", name: "", customer_name: "", phone: "",
    site_address: "", stage: "Customer Enquiry", status: "Active", priority: "Normal",
    value: 0, paid: 0, applicator: "", pm: "", start_date: new Date().toISOString().slice(0, 10),
    target_date: "", notes: "",
  };
  const [form, setForm] = useState(empty);

  const load = async () => { const { data } = await api.get("/projects"); setRows(data); };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() =>
    rows.filter((r) => fStage === "All" || r.stage === fStage), [rows, fStage]);

  const totals = useMemo(() => ({
    value: filtered.reduce((a, b) => a + (b.value || 0), 0),
    balance: filtered.reduce((a, b) => a + (b.balance || 0), 0),
  }), [filtered]);

  const save = async () => {
    try { await api.post("/projects", form); toast.success("Project created"); setShow(false); setForm(empty); load(); }
    catch { toast.error("Save failed"); }
  };
  const patch = async (p, changes) => {
    setRows((prev) => prev.map((x) => x.id === p.id ? { ...x, ...changes } : x));
    try { await api.put(`/projects/${p.id}`, { ...p, ...changes }); }
    catch { toast.error("Update failed"); load(); }
  };
  const remove = async (id) => { if (!window.confirm("Delete this project?")) return; await api.delete(`/projects/${id}`); load(); };

  return (
    <>
      <Topbar title="MAP Projects" subtitle={`${filtered.length} projects · ${inrFull(totals.value)} · ${inrFull(totals.balance)} balance`} onAdd={() => { setForm(empty); setShow(true); }} addLabel="New Project" />
      <div className="p-6" data-testid="projects-page">
        <div className="flex flex-wrap gap-2 mb-4">
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
                  <th className="text-left font-semibold px-4 py-2.5">Project</th>
                  <th className="text-left font-semibold px-4 py-2.5">Customer</th>
                  <th className="text-left font-semibold px-4 py-2.5">Stage</th>
                  <th className="text-left font-semibold px-4 py-2.5">Applicator</th>
                  <th className="text-right font-semibold px-4 py-2.5">Value</th>
                  <th className="text-right font-semibold px-4 py-2.5">Paid</th>
                  <th className="text-right font-semibold px-4 py-2.5">Balance</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((p) => (
                  <tr key={p.id} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50">
                    <td className="px-4 py-3">
                      <div className="font-medium text-[var(--ink)]">{p.name}</div>
                      <div className="text-xs text-[var(--ink-3)]">{p.division}{p.project_type ? ` · ${p.project_type}` : ""}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-[var(--ink)]">{p.customer_name}</div>
                      {p.site_address && <div className="text-xs text-[var(--ink-3)]">{p.site_address}</div>}
                    </td>
                    <td className="px-4 py-3">
                      <select value={p.stage} onChange={(e) => patch(p, { stage: e.target.value })} className="px-2 py-1 rounded-md border border-[var(--border)] bg-white text-xs">
                        {STAGES.map((s) => <option key={s}>{s}</option>)}
                      </select>
                    </td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{p.applicator || "—"}</td>
                    <td className="px-4 py-3 text-right font-mono">{inrFull(p.value)}</td>
                    <td className="px-4 py-3 text-right font-mono text-[var(--moss)]">{inrFull(p.paid)}</td>
                    <td className={`px-4 py-3 text-right font-mono ${p.balance > 0 ? "text-[var(--danger)] font-semibold" : "text-[var(--ink-3)]"}`}>{inrFull(p.balance)}</td>
                    <td className="px-2 py-3"><button onClick={() => remove(p.id)} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button></td>
                  </tr>
                ))}
                {filtered.length === 0 && <tr><td colSpan="8" className="text-center py-10 text-[var(--ink-3)]">No projects</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div className="bg-white rounded-xl border border-[var(--border)] w-full max-w-xl shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">New Project</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-4 max-h-[60vh] overflow-y-auto">
              <Sel l="Division" v={form.division} opts={DIVISIONS} oc={(v) => setForm({ ...form, division: v })} />
              <Fld l="Project type" v={form.project_type} oc={(v) => setForm({ ...form, project_type: v })} />
              <Fld l="Project name" v={form.name} oc={(v) => setForm({ ...form, name: v })} cls="col-span-2" />
              <Fld l="Customer" v={form.customer_name} oc={(v) => setForm({ ...form, customer_name: v })} />
              <Fld l="Phone" v={form.phone} oc={(v) => setForm({ ...form, phone: v })} />
              <Fld l="Site address" v={form.site_address} oc={(v) => setForm({ ...form, site_address: v })} cls="col-span-2" />
              <Sel l="Stage" v={form.stage} opts={STAGES} oc={(v) => setForm({ ...form, stage: v })} />
              <Fld l="Applicator" v={form.applicator} oc={(v) => setForm({ ...form, applicator: v })} />
              <Fld l="Value" t="number" v={form.value} oc={(v) => setForm({ ...form, value: parseFloat(v) || 0 })} />
              <Fld l="Paid" t="number" v={form.paid} oc={(v) => setForm({ ...form, paid: parseFloat(v) || 0 })} />
              <Fld l="PM" v={form.pm} oc={(v) => setForm({ ...form, pm: v })} />
              <Fld l="Target date" t="date" v={form.target_date} oc={(v) => setForm({ ...form, target_date: v })} />
              <Fld l="Notes" v={form.notes} oc={(v) => setForm({ ...form, notes: v })} cls="col-span-2" />
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary" onClick={save}>Create</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function Fld({ l, v, oc, t = "text", cls = "" }) {
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
