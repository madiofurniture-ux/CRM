import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import FilterChips from "@/components/FilterChips";
import JourneyDrawer from "@/components/JourneyDrawer";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { Phone, Calendar, X, Trash2, Compass, FileText } from "lucide-react";

// Unified intake schema — walk-ins + Navaki enquiries land in one queue.
const STAGES = ["New", "Contacted", "Follow-Up", "Qualified", "Dormant", "Lost", "Converted"];
const SOURCES = ["Walk-in", "Navaki", "Architect", "Referral", "Online"];
const DIVISIONS = ["Furniture", "MAP", "D&W"];
const CLOSED = ["Lost", "Converted"];

const daysUntil = (d) => {
  if (!d) return null;
  const t = new Date(d); t.setHours(0, 0, 0, 0);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return Math.round((t - today) / 86400000);
};

export default function Leads() {
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState("");
  const [view, setView] = useState("all");
  const [show, setShow] = useState(false);
  const [jny, setJny] = useState(null);

  const empty = {
    source: "Walk-in", intake_date: new Date().toISOString().slice(0, 10),
    name: "", phone: "", referrer: "", requirement: "", division: "Furniture",
    owner: "", stage: "New", next_action_date: "", remarks: "",
  };
  const [form, setForm] = useState(empty);

  const load = async () => { const { data } = await api.get("/leads"); setRows(data); };
  useEffect(() => { load(); }, []);

  // Saved-view predicates, mirroring the web app's chip row.
  const pred = (v) => (l) => {
    if (v === "all") return true;
    if (SOURCES.includes(v)) return l.source === v;
    if (STAGES.includes(v)) return l.stage === v;
    const du = daysUntil(l.next_action_date);
    if (v === "due") return du === 0 && !CLOSED.includes(l.stage);
    if (v === "overdue") return du != null && du < 0 && !CLOSED.includes(l.stage);
    if (v === "fresh") { const a = daysUntil(l.intake_date); return a != null && a >= -3; }
    if (v === "untouched") return !l.next_action_date && !CLOSED.includes(l.stage);
    return true;
  };

  const views = useMemo(() => [
    { key: "all", label: "All", count: rows.length },
    { key: "New", label: "🆕 New", count: rows.filter(pred("New")).length },
    { key: "Follow-Up", label: "📞 Follow-Up", count: rows.filter(pred("Follow-Up")).length },
    { key: "Qualified", label: "⭐ Qualified", count: rows.filter(pred("Qualified")).length },
    { key: "due", label: "🔔 Due today", count: rows.filter(pred("due")).length },
    { key: "overdue", label: "⚠ Overdue", count: rows.filter(pred("overdue")).length },
    { key: "untouched", label: "🕸 Untouched", count: rows.filter(pred("untouched")).length },
    { key: "Converted", label: "✅ Converted", count: rows.filter(pred("Converted")).length },
  ], [rows]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return rows.filter(pred(view)).filter((r) =>
      !q || (r.name || "").toLowerCase().includes(q)
      || (r.phone || "").toString().includes(q)
      || (r.requirement || "").toLowerCase().includes(q)
      || (r.lead_id || "").toLowerCase().includes(q)
    );
  }, [rows, search, view]);

  const save = async () => {
    try {
      const { data } = await api.post("/leads", form);
      if (data._duplicate_of) toast.warning(`Possible duplicate of ${data._duplicate_of} — check the journey 🧭`);
      else toast.success("Lead added");
      setShow(false); setForm(empty); load();
    } catch { toast.error("Save failed"); }
  };
  const patch = async (l, changes) => {
    setRows((p) => p.map((x) => x.id === l.id ? { ...x, ...changes } : x));
    try { await api.put(`/leads/${l.id}`, { ...l, ...changes }); }
    catch { toast.error("Update failed"); load(); }
  };
  const convert = async (l) => {
    try { const { data } = await api.post(`/convert/lead-to-quote/${l.id}`); toast.success(`Quote ${data.quote_no} created`); load(); }
    catch { toast.error("Convert failed"); }
  };
  const remove = async (id) => { if (!window.confirm("Delete this lead?")) return; await api.delete(`/leads/${id}`); load(); };

  return (
    <>
      <Topbar title="Leads (All Intake)" subtitle={`${filtered.length} of ${rows.length} leads`} onAdd={() => { setForm(empty); setShow(true); }} addLabel="Add Lead" />
      <div className="p-6" data-testid="leads-page">
        <div className="flex flex-col gap-3 mb-4">
          <FilterChips views={views} active={view} onChange={setView} />
          <input placeholder="Search name, phone, requirement, LD-id…" value={search} onChange={(e) => setSearch(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] w-full max-w-md" data-testid="leads-search" />
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Lead</th>
                  <th className="text-left font-semibold px-4 py-2.5">Name</th>
                  <th className="text-left font-semibold px-4 py-2.5">Source</th>
                  <th className="text-left font-semibold px-4 py-2.5">Division</th>
                  <th className="text-left font-semibold px-4 py-2.5">Stage</th>
                  <th className="text-left font-semibold px-4 py-2.5">Next action</th>
                  <th className="text-left font-semibold px-4 py-2.5">Owner</th>
                  <th className="w-28"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((l) => {
                  const du = daysUntil(l.next_action_date);
                  const overdue = du != null && du < 0 && !CLOSED.includes(l.stage);
                  return (
                    <tr key={l.id} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50">
                      <td className="px-4 py-3">
                        <div className="font-mono text-[11px] text-[var(--ink-2)]">{l.lead_id}</div>
                        {l.phone && <span className="inline-flex items-center gap-1 font-mono text-[11px] text-[var(--ink-3)]"><Phone size={10} />{l.phone}</span>}
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium text-[var(--ink)]">{l.name}</div>
                        {l.requirement && <div className="text-xs text-[var(--ink-3)]">{l.requirement}</div>}
                      </td>
                      <td className="px-4 py-3 text-[var(--ink-2)]">{l.source}</td>
                      <td className="px-4 py-3 text-[var(--ink-2)]">{l.division}</td>
                      <td className="px-4 py-3">
                        <select value={l.stage} onChange={(e) => patch(l, { stage: e.target.value })} className="px-2 py-1 rounded-md border border-[var(--border)] bg-white text-xs">
                          {STAGES.map((s) => <option key={s}>{s}</option>)}
                        </select>
                      </td>
                      <td className={`px-4 py-3 whitespace-nowrap ${overdue ? "text-[var(--danger)] font-semibold" : "text-[var(--ink-2)]"}`}>
                        <input type="date" value={l.next_action_date || ""} onChange={(e) => patch(l, { next_action_date: e.target.value })} className="bg-transparent text-xs outline-none" />
                        {overdue && <span className="ml-1 text-[10px]">⚠ {Math.abs(du)}d</span>}
                      </td>
                      <td className="px-4 py-3 text-[var(--ink-2)]">{l.owner}</td>
                      <td className="px-2 py-3">
                        <div className="flex items-center gap-1">
                          {l.phone && <button onClick={() => setJny({ phone: l.phone, name: l.name })} title="Journey" className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]"><Compass size={13} /></button>}
                          {!CLOSED.includes(l.stage) && <button onClick={() => convert(l)} title="Convert to quote" className="p-1.5 rounded-md hover:bg-[var(--brand-soft)] text-[var(--brand)]"><FileText size={13} /></button>}
                          <button onClick={() => remove(l.id)} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {filtered.length === 0 && <tr><td colSpan="8" className="text-center py-10 text-[var(--ink-3)]">No leads match this view</td></tr>}
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
              <Sel l="Source" v={form.source} opts={SOURCES} oc={(v) => setForm({ ...form, source: v })} />
              <Fld l="Intake date" t="date" v={form.intake_date} oc={(v) => setForm({ ...form, intake_date: v })} />
              <Fld l="Name" v={form.name} oc={(v) => setForm({ ...form, name: v })} t2="lf-name" />
              <Fld l="Phone" v={form.phone} oc={(v) => setForm({ ...form, phone: v })} />
              <Sel l="Division" v={form.division} opts={DIVISIONS} oc={(v) => setForm({ ...form, division: v })} />
              <Sel l="Stage" v={form.stage} opts={STAGES} oc={(v) => setForm({ ...form, stage: v })} />
              <Fld l="Requirement" v={form.requirement} oc={(v) => setForm({ ...form, requirement: v })} />
              <Fld l="Referrer" v={form.referrer} oc={(v) => setForm({ ...form, referrer: v })} />
              <Fld l="Owner" v={form.owner} oc={(v) => setForm({ ...form, owner: v })} />
              <Fld l="Next action" t="date" v={form.next_action_date} oc={(v) => setForm({ ...form, next_action_date: v })} />
              <Fld l="Remarks" v={form.remarks} oc={(v) => setForm({ ...form, remarks: v })} cls="col-span-2" />
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary" onClick={save} data-testid="lead-save">Add Lead</button>
            </div>
          </div>
        </div>
      )}

      <JourneyDrawer phone={jny?.phone} name={jny?.name} onClose={() => setJny(null)} />
    </>
  );
}

function Fld({ l, v, oc, t = "text", cls = "", t2 }) {
  return (
    <div className={cls}>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <input type={t} value={v ?? ""} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" data-testid={t2} />
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
