import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import SearchSelect from "@/components/SearchSelect";
import LogTimeline from "@/components/LogTimeline";
import CustomerResolver from "@/components/CustomerResolver";
import SavedViewsBar from "@/components/SavedViewsBar";
import CustomFieldInput from "@/components/CustomFieldInput";
import CsvImportModal from "@/components/CsvImportModal";
import EmptyState from "@/components/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import useCustomFields from "@/hooks/useCustomFields";
import api, { formatApiError } from "@/lib/api";
import { fmtDate, inrFull } from "@/lib/format";
import { validateIndianPhone } from "@/lib/phone";
import { toast } from "sonner";
import { Phone, Calendar, X, Trash2, Pencil, MessageSquare, MessageCircle, Sparkles, Download, Upload } from "lucide-react";

const waLink = (phone, text = "") => {
  const ph = String(phone || "").replace(/\D/g, "").slice(-10);
  return ph ? `https://wa.me/91${ph}?text=${encodeURIComponent(text)}` : null;
};

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
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [fStage, setFStage] = useState("All");
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [users, setUsers] = useState([]);
  const [teams, setTeams] = useState([]);
  const [logLead, setLogLead] = useState(null);
  const { defs: customFieldDefs } = useCustomFields("lead");
  const [customFilters, setCustomFilters] = useState({});
  const [showImport, setShowImport] = useState(false);
  const empty = {
    date: new Date().toISOString().slice(0, 10), name: "", phone: "", source: "Walk-in",
    architect_id: "", architect_name: "",
    reference: "", attended_by: "", confidence_level: "", team_id: "",
    stage: "New", follow_up_date: "", remarks: "", assigned_to: "", assigned_to_id: "", value: 0,
    custom_fields: {},
  };
  const [form, setForm] = useState(empty);

  const load = async () => {
    setLoading(true);
    try { const { data } = await api.get("/leads"); setRows(data); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    load();
    api.get("/architects").then(({ data }) => setArchitects(data));
    api.get("/staff").then(({ data }) => setStaff(data));
    api.get("/users/directory").then(({ data }) => setUsers(data)).catch(() => setUsers([]));
    api.get("/teams").then(({ data }) => setTeams(data)).catch(() => setTeams([]));
  }, []);
  const userName = (id) => users.find((u) => u.id === id)?.name || "";

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
      if (fStage !== "All" && stage !== fStage.toLowerCase()) return false;
      if (q && !(r.name || "").toLowerCase().includes(q) && !(r.remarks || "").toLowerCase().includes(q)) return false;
      for (const [key, val] of Object.entries(customFilters)) {
        if (!val) continue;
        if (String((r.custom_fields || {})[key] ?? "") !== String(val)) return false;
      }
      return true;
    });
  }, [rows, search, fStage, customFilters]);

  const today = new Date().toISOString().slice(0, 10);

  const openNew = () => { setEditing(null); setForm(empty); setShow(true); };
  const openEdit = (l) => { setEditing(l); setForm({ ...empty, ...l, custom_fields: l.custom_fields || {} }); setShow(true); };

  const save = async () => {
    if (saving) return;
    if (!phoneCheck.valid) { toast.error(phoneCheck.message); return; }
    if (!form.source.trim()) return toast.error("Source is required");
    if (!editing && !form.reference.trim()) return toast.error("Reference is required");
    setSaving(true);
    const payload = { ...form, phone: phoneCheck.normalized };
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

  const exportCsv = async () => {
    const { data } = await api.get("/leads/export.csv", { skipCache: true, responseType: "blob" });
    const blob = new Blob([data], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `leads_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <>
      <Topbar
        title="Leads"
        subtitle={`${filtered.length} leads · pipeline ${inrFull(filtered.reduce((a, b) => a + (b.value || 0), 0))}`}
        onAdd={openNew}
        addLabel="Add Lead"
        actions={
          <>
            <button onClick={exportCsv} title="Export CSV" className="p-2 rounded-lg hover:bg-[var(--surface-2)] text-[var(--ink-2)]" data-testid="leads-export"><Download size={16} /></button>
            <button onClick={() => setShowImport(true)} title="Import CSV" className="p-2 rounded-lg hover:bg-[var(--surface-2)] text-[var(--ink-2)]" data-testid="leads-import-open"><Upload size={16} /></button>
          </>
        }
      />
      <div className="p-6" data-testid="leads-page">
        <div className="flex flex-wrap gap-2 mb-3">
          <input placeholder="Search lead, remarks…" value={search} onChange={(e) => setSearch(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] w-72" data-testid="leads-search" />
          <select value={fStage} onChange={(e) => setFStage(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
            <option value="All">All</option>
            {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          {customFieldDefs.filter((d) => d.show_filter).map((d) => (
            <select key={d.key} value={customFilters[d.key] || ""} title={d.label}
                    onChange={(e) => setCustomFilters((p) => ({ ...p, [d.key]: e.target.value }))}
                    className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
              <option value="">{d.label}: All</option>
              {d.type === "select"
                ? (d.options || []).map((o) => <option key={o} value={o}>{o}</option>)
                : d.type === "boolean"
                  ? ["true", "false"].map((o) => <option key={o} value={o}>{o}</option>)
                  : null}
            </select>
          ))}
        </div>
        <div className="mb-4">
          <SavedViewsBar
            entity="leads"
            filters={{ search, fStage, customFilters }}
            onApply={(f) => { setSearch(f.search || ""); setFStage(f.fStage || "All"); setCustomFilters(f.customFilters || {}); }}
          />
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="hidden lg:table-cell text-left font-semibold px-4 py-2.5">Date</th>
                  <th className="text-left font-semibold px-4 py-2.5">Name</th>
                  <th className="hidden md:table-cell text-left font-semibold px-4 py-2.5">Phone</th>
                  <th className="hidden lg:table-cell text-left font-semibold px-4 py-2.5">Source</th>
                  <th className="hidden lg:table-cell text-left font-semibold px-4 py-2.5">Reference</th>
                  <th className="text-left font-semibold px-4 py-2.5">Stage</th>
                  <th className="hidden md:table-cell text-left font-semibold px-4 py-2.5">Follow up</th>
                  <th className="hidden lg:table-cell text-left font-semibold px-4 py-2.5">Attended by</th>
                  <th className="text-right font-semibold px-4 py-2.5">Value</th>
                  {customFieldDefs.filter((d) => d.show_table).map((d) => (
                    <th key={d.key} className="hidden lg:table-cell text-left font-semibold px-4 py-2.5">{d.label}</th>
                  ))}
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {loading && Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i} className="border-t border-[var(--border-light)]">
                    <td className="hidden lg:table-cell px-4 py-3"><Skeleton className="h-4 w-16" /></td>
                    <td className="px-4 py-3"><Skeleton className="h-4 w-28" /></td>
                    <td className="hidden md:table-cell px-4 py-3"><Skeleton className="h-4 w-24" /></td>
                    <td className="hidden lg:table-cell px-4 py-3"><Skeleton className="h-4 w-20" /></td>
                    <td className="hidden lg:table-cell px-4 py-3"><Skeleton className="h-4 w-20" /></td>
                    <td className="px-4 py-3"><Skeleton className="h-6 w-20" /></td>
                    <td className="hidden md:table-cell px-4 py-3"><Skeleton className="h-4 w-20" /></td>
                    <td className="hidden lg:table-cell px-4 py-3"><Skeleton className="h-4 w-20" /></td>
                    <td className="px-4 py-3"><Skeleton className="h-4 w-16 ml-auto" /></td>
                    {customFieldDefs.filter((d) => d.show_table).map((d) => (
                      <td key={d.key} className="hidden lg:table-cell px-4 py-3"><Skeleton className="h-4 w-16" /></td>
                    ))}
                    <td className="px-2 py-3"><Skeleton className="h-6 w-14" /></td>
                  </tr>
                ))}
                {!loading && filtered.map((l) => {
                  const overdue = l.follow_up_date && l.follow_up_date < today && !["Won", "Lost"].includes(l.stage);
                  return (
                    <tr key={l.id} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50">
                      <td className="hidden lg:table-cell px-4 py-3 text-[var(--ink-2)] whitespace-nowrap">{fmtDate(l.date)}</td>
                      <td className="px-4 py-3 font-medium">{l.name}</td>
                      <td className="hidden md:table-cell px-4 py-3 font-mono text-xs text-[var(--ink-2)]">
                        {l.phone && <span className="inline-flex items-center gap-1"><Phone size={11} className="text-[var(--ink-3)]" />{l.phone}</span>}
                      </td>
                      <td className="hidden lg:table-cell px-4 py-3 text-[var(--ink-2)]">{l.source}</td>
                      <td className="hidden lg:table-cell px-4 py-3 text-[var(--ink-2)]">{l.reference}</td>
                      <td className="px-4 py-3">
                        <select value={l.stage || "New"} onChange={(e) => updateStage(l, e.target.value)} className="px-2 py-1 rounded-md border border-[var(--border)] bg-white text-xs" title={!isKnownStage(l.stage) ? "Legacy/imported value — pick a stage to normalize it" : undefined}>
                          {l.stage && !isKnownStage(l.stage) && <option value={l.stage}>{l.stage} (unrecognized)</option>}
                          {STAGES.map((s) => <option key={s}>{s}</option>)}
                        </select>
                      </td>
                      <td className={`hidden md:table-cell px-4 py-3 whitespace-nowrap ${overdue ? "text-[var(--danger)] font-semibold" : "text-[var(--ink-2)]"}`}>
                        <span className="inline-flex items-center gap-1"><Calendar size={11} />{fmtDate(l.follow_up_date)}</span>
                      </td>
                      <td className="hidden lg:table-cell px-4 py-3 text-[var(--ink-2)]">{userName(l.attended_by) || l.assigned_to}</td>
                      <td className="px-4 py-3 text-right font-mono">{inrFull(l.value)}</td>
                      {customFieldDefs.filter((d) => d.show_table).map((d) => (
                        <td key={d.key} className="hidden lg:table-cell px-4 py-3 text-[var(--ink-2)]">{String((l.custom_fields || {})[d.key] ?? "")}</td>
                      ))}
                      <td className="px-2 py-3 flex items-center gap-1">
                        {l.phone && (
                          <a href={`tel:${l.phone}`} title="Call" className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]" data-testid={`lead-call-${l.id}`}><Phone size={13} /></a>
                        )}
                        {waLink(l.phone) && (
                          <a href={waLink(l.phone)} target="_blank" rel="noreferrer" title="WhatsApp" className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]" data-testid={`lead-wa-${l.id}`}><MessageCircle size={13} /></a>
                        )}
                        <button onClick={() => openEdit(l)} className="p-1.5 rounded-md hover:bg-[var(--surface-2)] text-[var(--ink-2)]" title="Edit lead" data-testid={`lead-edit-${l.id}`}><Pencil size={13} /></button>
                        <button onClick={() => setLogLead(l)} title="Follow-up timeline" className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]" data-testid={`lead-log-${l.id}`}><MessageSquare size={13} /></button>
                        <button onClick={() => remove(l.id)} title="Delete" className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button>
                      </td>
                    </tr>
                  );
                })}
                {!loading && filtered.length === 0 && (
                  <tr><td colSpan={10 + customFieldDefs.filter((d) => d.show_table).length}>
                    <EmptyState icon={Sparkles} title="No leads yet" hint="New leads you add or capture will show up here." />
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center sm:p-4" onClick={() => setShow(false)}>
          <div className="bg-white rounded-t-2xl sm:rounded-xl border border-[var(--border)] w-full max-w-xl shadow-2xl max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">{editing ? "Edit Lead" : "New Lead"}</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="px-5 pt-4">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Search Existing Customer</label>
              <CustomerResolver onSelect={(c) => setForm({ ...form, name: c.name, phone: c.phone })} />
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
              <Fld l="Reference *" v={form.reference} oc={(v) => setForm({ ...form, reference: v })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Attended by</label>
                <select value={form.attended_by} onChange={(e) => setForm({ ...form, attended_by: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
                  <option value="">— Select —</option>
                  {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                </select>
              </div>
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
              <Fld l="Confidence %" t="number" v={form.confidence_level} oc={(v) => setForm({ ...form, confidence_level: v === "" ? "" : parseFloat(v) || 0 })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Team</label>
                <select value={form.team_id} onChange={(e) => setForm({ ...form, team_id: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
                  <option value="">— None —</option>
                  {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
              <Fld l="Value" t="number" v={form.value} oc={(v) => setForm({ ...form, value: parseFloat(v) || 0 })} />
              <Fld l="Remarks" v={form.remarks} oc={(v) => setForm({ ...form, remarks: v })} cls="col-span-2" />
              {customFieldDefs.filter((d) => d.show_detail).map((d) => (
                <CustomFieldInput
                  key={d.key}
                  def={d}
                  value={form.custom_fields?.[d.key]}
                  onChange={(v) => setForm({ ...form, custom_fields: { ...form.custom_fields, [d.key]: v } })}
                />
              ))}
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

      {logLead && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center sm:p-4" onClick={() => setLogLead(null)}>
          <div className="bg-white rounded-t-2xl sm:rounded-xl border border-[var(--border)] w-full max-w-xl shadow-2xl max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">Follow-ups — {logLead.name}</h3>
              <button onClick={() => setLogLead(null)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5">
              <LogTimeline
                entity="lead" itemId={logLead.id} entries={logLead.log || []}
                onAppended={(log) => {
                  setLogLead((p) => ({ ...p, log }));
                  setRows((p) => p.map((x) => x.id === logLead.id ? { ...x, log } : x));
                }}
              />
            </div>
          </div>
        </div>
      )}

      {showImport && (
        <CsvImportModal entity="leads" onClose={() => setShowImport(false)} onImported={load} />
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
