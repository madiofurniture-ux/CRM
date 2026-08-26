import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import SearchSelect from "@/components/SearchSelect";
import RemarksEditor, { toRemarksArray } from "@/components/RemarksEditor";
import api, { formatApiError } from "@/lib/api";
import { fmtDate, inrFull } from "@/lib/format";
import { validateIndianPhone } from "@/lib/phone";
import { toast } from "sonner";
import { Phone, Calendar, X, Trash2, Pencil } from "lucide-react";

const STAGES = ["New", "Contacted", "Qualified", "Quoted", "Negotiation", "Won", "Lost"];
const isKnownStage = (s) => STAGES.some((x) => x.toLowerCase() === String(s || "").trim().toLowerCase());

// "Architect Ref"/"WhatsApp"/etc are pre-existing source values seeded/used
// before this became a dropdown — kept as real options rather than dropped,
// same "unrecognized" fallback pattern as STAGES above covers anything else.
const SOURCES = ["Walk-in", "Architect", "Referral", "Website", "Social Media", "WhatsApp", "Instagram", "Site Visit", "Other"];
const isKnownSource = (s) => SOURCES.some((x) => x.toLowerCase() === String(s || "").trim().toLowerCase());

export default function Leads() {
  const [rows, setRows] = useState([]);
  const [architects, setArchitects] = useState([]);
  const [staff, setStaff] = useState([]);
  const [search, setSearch] = useState("");
  const [fStage, setFStage] = useState("All");
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const empty = {
    date: new Date().toISOString().slice(0, 10), name: "", phone: "", source: "Walk-in",
    architect_id: "", architect_name: "",
    stage: "New", follow_up_date: "", remarks: [], assigned_to: "", assigned_to_id: "", value: 0,
  };
  const [form, setForm] = useState(empty);

  const load = async () => { const { data } = await api.get("/leads"); setRows(data); };
  useEffect(() => {
    load();
    api.get("/architects").then(({ data }) => setArchitects(data));
    api.get("/staff").then(({ data }) => setStaff(data));
  }, []);

  const architectOptions = useMemo(() => architects.map((a) => ({
    id: a.id,
    name: a.name,
    label: (a.type === "Architect" ? "Ar. " : "") + a.name,
    sub: [a.phone, a.firm].filter(Boolean).join(" · "),
    assignedTo: a.assigned_to,
  })), [architects]);

  const staffOptions = useMemo(() => staff.map((s) => ({
    id: s.id,
    name: s.name || s.username,
    label: s.name || s.username,
    sub: s.username && s.username !== s.name ? `@${s.username}` : "",
  })), [staff]);

  const phoneCheck = useMemo(() => validateIndianPhone(form.phone), [form.phone]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return rows.filter((r) => {
      const stage = String(r.stage || "New").trim().toLowerCase();
      const remarksText = toRemarksArray(r.remarks).map((x) => x.text).join(" ").toLowerCase();
      return (fStage === "All" || stage === fStage.toLowerCase()) &&
        (!q || (r.name || "").toLowerCase().includes(q) || remarksText.includes(q));
    });
  }, [rows, search, fStage]);

  const today = new Date().toISOString().slice(0, 10);

  const openNew = () => { setEditing(null); setForm(empty); setShow(true); };
  const openEdit = (l) => { setEditing(l); setForm({ ...empty, ...l }); setShow(true); };

  const save = async () => {
    if (saving) return;
    if (!phoneCheck.valid) { toast.error(phoneCheck.message); return; }
    setSaving(true);
    const payload = { ...form, phone: phoneCheck.normalized, remarks: toRemarksArray(form.remarks) };
    try {
      if (editing) {
        await api.put(`/leads/${editing.id}`, payload);
        toast.success("Lead updated");
      } else {
        await api.post("/leads", payload);
        toast.success("Lead added");
      }
      setShow(false); setEditing(null); setForm(empty); load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Save failed");
    } finally {
      setSaving(false);
    }
  };
  const updateStage = async (l, stage) => {
    await api.put(`/leads/${l.id}`, { ...l, stage });
    setRows((p) => p.map((x) => x.id === l.id ? { ...x, stage } : x));
  };
  const remove = async (id) => { if (!window.confirm("Delete?")) return; await api.delete(`/leads/${id}`); load(); };

  return (
    <>
      <Topbar title="Leads" subtitle={`${filtered.length} leads · pipeline ${inrFull(filtered.reduce((a, b) => a + (b.value || 0), 0))}`} onAdd={openNew} addLabel="Add Lead" />
      <div className="p-6" data-testid="leads-page">
        <div className="flex flex-wrap gap-2 mb-4">
          <input placeholder="Search lead, remarks…" value={search} onChange={(e) => setSearch(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] w-72" data-testid="leads-search" />
          <select value={fStage} onChange={(e) => setFStage(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
            <option value="All">All</option>
            {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
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
                        <select value={l.stage || "New"} onChange={(e) => updateStage(l, e.target.value)} className="px-2 py-1 rounded-md border border-[var(--border)] bg-white text-xs" title={!isKnownStage(l.stage) ? "Legacy/imported value — pick a stage to normalize it" : undefined}>
                          {l.stage && !isKnownStage(l.stage) && <option value={l.stage}>{l.stage} (unrecognized)</option>}
                          {STAGES.map((s) => <option key={s}>{s}</option>)}
                        </select>
                      </td>
                      <td className={`px-4 py-3 whitespace-nowrap ${overdue ? "text-[var(--danger)] font-semibold" : "text-[var(--ink-2)]"}`}>
                        <span className="inline-flex items-center gap-1"><Calendar size={11} />{fmtDate(l.follow_up_date)}</span>
                      </td>
                      <td className="px-4 py-3 text-[var(--ink-2)]">{l.assigned_to}</td>
                      <td className="px-4 py-3 text-right font-mono">{inrFull(l.value)}</td>
                      <td className="px-2 py-3">
                        <div className="flex items-center justify-end gap-1">
                          <button onClick={() => openEdit(l)} className="p-1.5 rounded-md hover:bg-[var(--surface-2)] text-[var(--ink-2)]" title="Edit lead" data-testid={`lead-edit-${l.id}`}><Pencil size={13} /></button>
                          <button onClick={() => remove(l.id)} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]" title="Delete lead"><Trash2 size={13} /></button>
                        </div>
                      </td>
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
              <h3 className="font-heading font-semibold text-lg">{editing ? "Edit Lead" : "New Lead"}</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-4">
              <Fld l="Date" t="date" v={form.date} oc={(v) => setForm({ ...form, date: v })} />
              <Fld l="Name" v={form.name} oc={(v) => setForm({ ...form, name: v })} t2="lf-name" />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Phone</label>
                <input
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  placeholder="9876543210 or +919876543210"
                  className={`w-full px-3 py-2 rounded-lg border bg-white text-sm outline-none ${phoneCheck.valid ? "border-[var(--border)] focus:border-[var(--brand)]" : "border-[var(--danger)] focus:border-[var(--danger)]"}`}
                  data-testid="lf-phone"
                />
                {!phoneCheck.valid && <div className="text-[11px] text-[var(--danger)] mt-1" data-testid="lf-phone-error">{phoneCheck.message}</div>}
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Source</label>
                <select
                  value={form.source}
                  onChange={(e) => {
                    const source = e.target.value;
                    setForm((f) => source === "Architect"
                      ? { ...f, source }
                      : { ...f, source, architect_id: "", architect_name: "" });
                  }}
                  className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm"
                  data-testid="lf-source"
                >
                  {form.source && !isKnownSource(form.source) && <option value={form.source}>{form.source} (unrecognized)</option>}
                  {SOURCES.map((s) => <option key={s}>{s}</option>)}
                </select>
              </div>
              {form.source === "Architect" && (
                <div className="col-span-2">
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Architect</label>
                  <SearchSelect
                    options={architectOptions}
                    value={form.architect_id}
                    onChange={(id, opt) => setForm((f) => {
                      if (!opt) return { ...f, architect_id: "", architect_name: "" };
                      // Prepopulate the assigned staff from the architect's own
                      // "assigned to" contact, matched by name — only if the
                      // user hasn't already picked someone, so this never
                      // clobbers a deliberate choice.
                      let staffFill = {};
                      if (!f.assigned_to_id && opt.assignedTo) {
                        const match = staffOptions.find((s) => s.name.toLowerCase() === opt.assignedTo.toLowerCase());
                        if (match) staffFill = { assigned_to_id: match.id, assigned_to: match.name };
                      }
                      return { ...f, architect_id: id, architect_name: opt.name, ...staffFill };
                    })}
                    placeholder="Search architect by name or phone…"
                    emptyLabel="No architects found — add one on the Architects page"
                    testId="lf-architect"
                  />
                </div>
              )}
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Stage</label>
                <select value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
                  {STAGES.map((s) => <option key={s}>{s}</option>)}
                </select>
              </div>
              <Fld l="Follow up" t="date" v={form.follow_up_date} oc={(v) => setForm({ ...form, follow_up_date: v })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Assigned to (Staff)</label>
                <SearchSelect
                  options={staffOptions}
                  value={form.assigned_to_id}
                  onChange={(id, opt) => setForm({ ...form, assigned_to_id: id, assigned_to: opt ? opt.name : "" })}
                  placeholder="Search staff by name…"
                  emptyLabel="No staff found"
                  testId="lf-assigned"
                />
                {!form.assigned_to_id && form.assigned_to && (
                  <div className="text-[11px] text-[var(--ink-3)] mt-1">Currently: {form.assigned_to} (unlinked — pick from the list to link)</div>
                )}
              </div>
              <Fld l="Value" t="number" v={form.value} oc={(v) => setForm({ ...form, value: parseFloat(v) || 0 })} />
              <div className="col-span-2">
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Remarks</label>
                <RemarksEditor remarks={form.remarks} onChange={(remarks) => setForm({ ...form, remarks })} testPrefix="lf-remark" />
              </div>
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary disabled:opacity-60" onClick={save} disabled={saving || !phoneCheck.valid} data-testid="lead-save">
                {saving ? "Saving…" : editing ? "Save Changes" : "Add Lead"}
              </button>
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
