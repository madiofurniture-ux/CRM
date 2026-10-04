import { useEffect, useState, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import usePersistedState from "@/hooks/usePersistedState";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import SearchSelect from "@/components/SearchSelect";
import LogTimeline from "@/components/LogTimeline";
import AttachmentPanel from "@/components/AttachmentPanel";
import LinkedTasksPanel from "@/components/LinkedTasksPanel";
import StageProgressBar from "@/components/StageProgressBar";
import StagePath from "@/components/StagePath";
import useWorkflow, { stageErrorMessage } from "@/hooks/useWorkflow";
import { leadLifecycleStages } from "@/lib/lifecycle";
import CustomerResolver from "@/components/CustomerResolver";
import SavedViewsBar from "@/components/SavedViewsBar";
import CustomFieldInput from "@/components/CustomFieldInput";
import CsvImportModal from "@/components/CsvImportModal";
import RemarksTimeline from "@/components/RemarksTimeline";
import StarRating from "@/components/StarRating";
import EmptyState from "@/components/EmptyState";
import { useTenantConfig } from "@/context/TenantConfigContext";
import ErrorState from "@/components/ErrorState";
import { useAuth } from "@/context/AuthContext";
import { Skeleton } from "@/components/ui/skeleton";
import useCustomFields from "@/hooks/useCustomFields";
import api, { formatApiError } from "@/lib/api";
import { fmtDate, inrFull, todayIST } from "@/lib/format";
import { validateIndianPhone } from "@/lib/phone";
import { toast } from "sonner";
import { Phone, Calendar, X, Trash2, Pencil, MessageSquare, Sparkles, Download, Upload } from "lucide-react";
import WhatsAppButton from "@/components/WhatsAppButton";

// Fallback only: the live stage list is the tenant's lead workflow
// (Admin → Workflows), loaded by useWorkflow below.
const DEFAULT_STAGES = ["New", "Contacted", "Qualified", "Quoted", "Negotiation", "Won", "Lost"];

const PRIORITIES = ["Low", "Medium", "High", "Hot"];
const PRIORITY_TONE = { Hot: "bg-red-50 text-red-700", High: "bg-amber-50 text-amber-700", Medium: "", Low: "" };

export default function Leads() {
  const [rows, setRows] = useState([]);
  const [architects, setArchitects] = useState([]);
  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [fStage, setFStage] = usePersistedState("leads.stage", "All");
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [users, setUsers] = useState([]);
  const [logLead, setLogLead] = useState(null);
  const { defs: customFieldDefs } = useCustomFields("lead");
  const [customFilters, setCustomFilters] = useState({});
  const [fDivision, setFDivision] = usePersistedState("leads.division", "All");
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [converting, setConverting] = useState("");
  const [showImport, setShowImport] = useState(false);
  const { user, canDo } = useAuth();
  const canCreate = canDo("leads", "create");
  const canEdit = canDo("leads", "edit");
  const lw = useWorkflow("lead", DEFAULT_STAGES);
  const STAGES = lw.labels;
  // Divisions and lead sources are the tenant's own (Business Settings /
  // industry pack), not one company's hardcoded lists. A lead whose source
  // isn't in the list still shows it, marked "(unrecognized)".
  const { divisions: tenantDivisions, leadSources: SOURCES } = useTenantConfig();
  const DIVISIONS = tenantDivisions.map((d) => d.slug);
  const isKnownSource = (src) => SOURCES.some((x) => x.toLowerCase() === String(src || "").trim().toLowerCase());
  const isKnownStage = lw.isKnownStage;
  const canDelete = canDo("leads", "delete");
  // null = the inline "new architect" sub-form is closed. It lives in its own
  // state so opening or cancelling it never touches `form` — the lead being
  // edited keeps every unsaved field the user has already typed.
  const [archDraft, setArchDraft] = useState(null);
  const [archSaving, setArchSaving] = useState(false);
  // `team_id` is intentionally absent: the Team row was removed from this
  // modal. It stays on the Lead record (CSV export still reads it) and rides
  // through untouched on edit via the `...l` spread in openEdit below.
  const empty = {
    date: todayIST(), name: "", phone: "", source: "Walk-in",
    architect_id: "", architect_name: "",
    reference: "", attended_by: "", confidence_level: "",
    stage: "New", follow_up_date: "", remarks_history: [], assigned_to: "", assigned_to_id: "", value: 0,
    custom_fields: {},
    division: "", email: "", whatsapp: "", location: "", requirement: "", priority: "Medium", next_action: "",
  };
  const [form, setForm] = useState(empty);

  const [loadError, setLoadError] = useState(null);
  const load = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const { data } = await api.get("/leads");
      setRows(data);
    } catch (e) {
      setLoadError(e?.response?.status === 401 || e?.response?.status === 403 ? "unauthorized" : "error");
    } finally { setLoading(false); }
  };
  useEffect(() => {
    load();
    api.get("/architects").then(({ data }) => setArchitects(data)).catch(() => setArchitects([]));
    api.get("/staff").then(({ data }) => setStaff(data)).catch(() => setStaff([]));
    api.get("/users/directory").then(({ data }) => setUsers(data)).catch(() => setUsers([]));
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
  const waCheck = useMemo(() => validateIndianPhone(form.whatsapp), [form.whatsapp]);

  // /leads?open=<id> (global search, follow-ups) opens that lead's timeline.
  useEffect(() => {
    const id = searchParams.get("open");
    if (!id || !rows.length) return;
    const l = rows.find((r) => r.id === id);
    if (l) setLogLead(l);
  }, [searchParams, rows]);
  const closeLog = () => {
    setLogLead(null);
    if (searchParams.get("open")) { searchParams.delete("open"); setSearchParams(searchParams, { replace: true }); }
  };

  const convert = async (lead, kind) => {
    if (converting) return;
    setConverting(kind);
    try {
      if (kind === "quote") {
        const { data } = await api.post(`/convert/lead-to-quote/${lead.id}`);
        toast.success(`Quotation ${data.quote_no || ""} created`);
        navigate(data.id ? `/quotes/ws/${data.id}` : "/quotes");
      } else {
        const { data } = await api.post(`/leads/${lead.id}/start-project`);
        toast.success(`Project ${data.project_no} ready`);
        navigate(`/projects?open=${data.id}`);
      }
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Conversion failed");
    } finally {
      setConverting("");
    }
  };

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return rows.filter((r) => {
      const stage = String(r.stage || "New").trim().toLowerCase();
      if (fStage !== "All" && stage !== fStage.toLowerCase()) return false;
      if (fDivision !== "All" && (r.division || "") !== fDivision) return false;
      // Search the legacy flat remark AND every entry in the history, so a
      // note added after this change is still findable.
      const remarkText = [r.remarks || "", ...(r.remarks_history || []).map((e) => e.text || "")].join(" ").toLowerCase();
      if (q && !(r.name || "").toLowerCase().includes(q) && !remarkText.includes(q)
          && !String(r.phone || "").includes(q) && !String(r.email || "").toLowerCase().includes(q)
          && !String(r.location || "").toLowerCase().includes(q)) return false;
      for (const [key, val] of Object.entries(customFilters)) {
        if (!val) continue;
        if (String((r.custom_fields || {})[key] ?? "") !== String(val)) return false;
      }
      return true;
    });
  }, [rows, search, fStage, fDivision, customFilters]);

  const today = todayIST();

  const openNew = () => { setEditing(null); setForm(empty); setArchDraft(null); setShow(true); };
  const openEdit = (l) => {
    setEditing(l);
    setForm({ ...empty, ...l, custom_fields: l.custom_fields || {}, remarks_history: l.remarks_history || [] });
    setArchDraft(null);
    setShow(true);
  };

  // "+ Create …" in the architect picker. Posts to the same /architects
  // endpoint the Architects page uses, with type "Architect" — the field that
  // distinguishes an architect from a Builder/Designer/Vendor contact — then
  // selects the result. setForm is functional so nothing else the user has
  // typed into the lead form is lost.
  const saveArchitect = async () => {
    if (archSaving) return;
    const name = archDraft.name.trim();
    if (!name) return toast.error("Architect name is required");
    const phoneOk = validateIndianPhone(archDraft.phone);
    if (!phoneOk.valid) return toast.error(phoneOk.message);
    setArchSaving(true);
    try {
      const { data } = await api.post("/architects", {
        name, phone: phoneOk.normalized, firm: archDraft.firm.trim(),
        email: archDraft.email.trim(), type: "Architect",
      });
      setArchitects((p) => [data, ...p]);
      setForm((f) => ({ ...f, architect_id: data.id, architect_name: data.name }));
      setArchDraft(null);
      toast.success("Architect created");
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Could not create architect");
    } finally {
      setArchSaving(false);
    }
  };

  const save = async () => {
    if (saving) return;
    if (!phoneCheck.valid) { toast.error(phoneCheck.message); return; }
    if (!form.source.trim()) return toast.error("Source is required");
    if (!editing && !form.reference.trim()) return toast.error("Reference is required");
    if (!waCheck.valid) { toast.error(`WhatsApp: ${waCheck.message}`); return; }
    if (form.email && !/^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(form.email.trim())) { toast.error("Enter a valid email address"); return; }
    const closed = ["won", "lost"].includes(String(form.stage || "").toLowerCase());
    if (!closed && !form.follow_up_date) toast.warning("No follow-up date — this lead will show under 'No follow-up date' until one is set.");
    setSaving(true);
    const payload = { ...form, phone: phoneCheck.normalized, whatsapp: waCheck.normalized, email: (form.email || "").trim() };
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
  // Sends ONLY the stage — never `{...l, stage}`. `l` is a read-shaped snapshot
  // from the last GET /leads, so resending it whole re-writes every other field
  // from that snapshot: any edit landed since (a rename from this modal, another
  // rep's edit, a value/assignment change) is silently reverted, and the
  // remarks_history that _lead_out synthesizes from a legacy `remarks` string
  // gets materialized with the acting user forged in as its author. PUT /leads
  // is a partial update ($set on exactly the keys sent — see
  // validate_partial_update, which only validates fields the caller changed),
  // so one key is the correct payload for a one-field edit.
  // The workflow's gates (required fields, allowed next stages) are enforced
  // server-side; a refusal comes back as a 400 whose message says what to fix.
  const updateStage = async (l, stage) => {
    try {
      const { data } = await api.put(`/leads/${l.id}`, { stage });
      const patch = { stage: data.stage, stage_history: data.stage_history, stage_entered_at: data.stage_entered_at };
      setRows((p) => p.map((x) => x.id === l.id ? { ...x, ...patch } : x));
      setLogLead((p) => (p && p.id === l.id ? { ...p, ...patch } : p));
    } catch (e) {
      toast.error(stageErrorMessage(e));
      throw e;
    }
  };
  const remove = async (id) => { if (!window.confirm("Delete?")) return; await api.delete(`/leads/${id}`); load(); };

  const exportCsv = async () => {
    const { data } = await api.get("/leads/export.csv", { skipCache: true, responseType: "blob" });
    const blob = new Blob([data], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `leads_${todayIST()}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <>
      <Topbar
        title="Leads"
        subtitle={`${filtered.length} leads · pipeline ${inrFull(filtered.reduce((a, b) => a + (b.value || 0), 0))}`}
        onAdd={canCreate ? openNew : undefined}
        addLabel="Add Lead"
        actions={
          <>
            <button onClick={exportCsv} title="Export CSV" className="p-2 rounded-lg hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]" data-testid="leads-export"><Download size={16} /></button>
            <button onClick={() => setShowImport(true)} title="Import CSV" className="p-2 rounded-lg hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]" data-testid="leads-import-open"><Upload size={16} /></button>
          </>
        }
      />
      <div className="p-3 sm:p-6" data-testid="leads-page">
        <div className="flex flex-wrap gap-2 mb-3">
          <input placeholder="Search name, phone, email, remarks…" value={search} onChange={(e) => setSearch(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-sm outline-none focus:border-[var(--color-primary)] w-full sm:w-72" data-testid="leads-search" />
          <select value={fDivision} onChange={(e) => setFDivision(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-sm" data-testid="leads-division-filter">
            <option value="All">All divisions</option>
            {DIVISIONS.map((d) => <option key={d}>{d}</option>)}
          </select>
          <select value={fStage} onChange={(e) => setFStage(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-sm">
            <option value="All">All</option>
            {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          {customFieldDefs.filter((d) => d.show_filter).map((d) => (
            <select key={d.key} value={customFilters[d.key] || ""} title={d.label}
                    onChange={(e) => setCustomFilters((p) => ({ ...p, [d.key]: e.target.value }))}
                    className="px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-sm">
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

        {loadError ? (
          <ErrorState
            title={loadError === "unauthorized" ? "You don't have access to Leads" : "Couldn't load leads"}
            hint={loadError === "unauthorized" ? undefined : "The leads list didn't load — check your connection and try again."}
            onRetry={loadError === "unauthorized" ? undefined : load}
          />
        ) : (
        <div className="bg-[var(--color-surface)] border border-[var(--color-primary-soft)] rounded-[var(--radius-lg)] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--color-surface-muted)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
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
                  <tr key={i} className="border-t border-[var(--color-border)]">
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
                    <tr key={l.id} className="border-t border-[var(--color-border)] hover:bg-[var(--color-surface-muted)]/50">
                      <td className="hidden lg:table-cell px-4 py-3 text-[var(--color-text-muted)] whitespace-nowrap">{fmtDate(l.date)}</td>
                      <td className="px-4 py-3">
                        <button type="button" onClick={() => setLogLead(l)} className="font-medium text-left hover:underline">{l.name}</button>
                        <div className="flex flex-wrap items-center gap-1 mt-0.5">
                          {l.division && <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-primary-soft)] text-[var(--color-primary)] font-semibold">{l.division}</span>}
                          {l.priority && PRIORITY_TONE[l.priority] && <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${PRIORITY_TONE[l.priority]}`}>{l.priority}</span>}
                          <span className={`md:hidden text-[10px] ${overdue ? "text-[var(--color-danger)] font-semibold" : "text-[var(--color-text-muted)]"}`}>{l.follow_up_date ? `FU ${fmtDate(l.follow_up_date)}` : ""}</span>
                        </div>
                      </td>
                      <td className="hidden md:table-cell px-4 py-3 font-mono text-xs text-[var(--color-text-muted)]">
                        {l.phone && <span className="inline-flex items-center gap-1"><Phone size={11} className="text-[var(--color-text-muted)]" />{l.phone}</span>}
                      </td>
                      <td className="hidden lg:table-cell px-4 py-3 text-[var(--color-text-muted)]">{l.source}</td>
                      <td className="hidden lg:table-cell px-4 py-3 text-[var(--color-text-muted)]">{l.reference}</td>
                      <td className="px-4 py-3">
                        <select value={l.stage || "New"} onChange={(e) => updateStage(l, e.target.value).catch(() => {})} disabled={!canEdit} className="px-2 py-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-xs disabled:opacity-60 disabled:cursor-not-allowed" title={!canEdit ? "You don't have permission to change a lead's stage" : !isKnownStage(l.stage) ? "Legacy/imported value — pick a stage to normalize it" : undefined}>
                          {l.stage && !isKnownStage(l.stage) && <option value={l.stage}>{l.stage} (unrecognized)</option>}
                          {STAGES.map((s) => <option key={s}>{s}</option>)}
                        </select>
                      </td>
                      <td className={`hidden md:table-cell px-4 py-3 whitespace-nowrap ${overdue ? "text-[var(--color-danger)] font-semibold" : "text-[var(--color-text-muted)]"}`}>
                        <span className="inline-flex items-center gap-1"><Calendar size={11} />{fmtDate(l.follow_up_date)}</span>
                        {l.next_action
                          ? <div className="text-[11px] text-[var(--color-text)] truncate max-w-[180px]" title={l.next_action}>{l.next_action}</div>
                          : !["Won", "Lost"].includes(l.stage) && <div className="text-[11px] text-[var(--color-danger)]">no next action</div>}
                      </td>
                      <td className="hidden lg:table-cell px-4 py-3 text-[var(--color-text-muted)]">{userName(l.attended_by) || l.assigned_to}</td>
                      <td className="px-4 py-3 text-right font-mono">{inrFull(l.value)}</td>
                      {customFieldDefs.filter((d) => d.show_table).map((d) => (
                        <td key={d.key} className="hidden lg:table-cell px-4 py-3 text-[var(--color-text-muted)]">{String((l.custom_fields || {})[d.key] ?? "")}</td>
                      ))}
                      <td className="px-2 py-3 flex items-center gap-1">
                        {l.phone && (
                          <a href={`tel:${l.phone}`} title="Call" className="p-1.5 rounded-md hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]" data-testid={`lead-call-${l.id}`}><Phone size={13} /></a>
                        )}
                        <WhatsAppButton phone={l.phone} context="follow-up" customerName={l.name}
                                        refType="lead" refId={l.id} testId={`lead-wa-${l.id}`} />
                        {canEdit && (
                          <button onClick={() => openEdit(l)} className="p-1.5 rounded-md hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]" title="Edit lead" data-testid={`lead-edit-${l.id}`}><Pencil size={13} /></button>
                        )}
                        <button onClick={() => setLogLead(l)} title="Follow-up timeline" className="p-1.5 rounded-md hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]" data-testid={`lead-log-${l.id}`}><MessageSquare size={13} /></button>
                        {canDelete && (
                          <button onClick={() => remove(l.id)} title="Delete" className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--color-danger)]"><Trash2 size={13} /></button>
                        )}
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
        )}
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center sm:p-4" onClick={() => setShow(false)}>
          <div className="bg-[var(--color-surface)] rounded-t-2xl sm:rounded-xl border border-[var(--color-border)] w-full max-w-xl shadow-2xl max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">{editing ? "Edit Lead" : "New Lead"}</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--color-surface-muted)]"><X size={16} /></button>
            </div>
            <div className="px-5 pt-4">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">Search Existing Customer</label>
              <CustomerResolver onSelect={(c) => setForm({ ...form, name: c.name, phone: c.phone })} />
            </div>
            <div className="p-5 grid grid-cols-2 gap-4">
              <Fld l="Date" t="date" v={form.date} oc={(v) => setForm({ ...form, date: v })} />
              <Fld l="Name" v={form.name} oc={(v) => setForm({ ...form, name: v })} t2="lf-name" />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">Phone</label>
                <input
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  placeholder="9876543210 or +919876543210"
                  className={`w-full px-3 py-2 rounded-lg border bg-[var(--color-surface)] text-sm outline-none ${phoneCheck.valid ? "border-[var(--color-border)] focus:border-[var(--color-primary)]" : "border-[var(--color-danger)] focus:border-[var(--color-danger)]"}`}
                  data-testid="lf-phone"
                />
                {!phoneCheck.valid && <div className="text-[11px] text-[var(--color-danger)] mt-1" data-testid="lf-phone-error">{phoneCheck.message}</div>}
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">Source</label>
                <select
                  value={form.source}
                  onChange={(e) => {
                    const source = e.target.value;
                    setForm((f) => source === "Architect"
                      ? { ...f, source }
                      : { ...f, source, architect_id: "", architect_name: "" });
                  }}
                  className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm"
                  data-testid="lf-source"
                >
                  {form.source && !isKnownSource(form.source) && <option value={form.source}>{form.source} (unrecognized)</option>}
                  {SOURCES.map((s) => <option key={s}>{s}</option>)}
                </select>
              </div>
              {form.source === "Architect" && (
                <div className="col-span-2">
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">Architect</label>
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
                    emptyLabel="No architects found"
                    testId="lf-architect"
                    createLabel="Architect"
                    onCreate={(term) => setArchDraft({ name: term, phone: "", firm: "", email: "" })}
                  />
                  {archDraft && (
                    <div className="mt-2 border border-[var(--color-primary)] rounded-lg p-3 bg-[var(--color-surface-muted)]" data-testid="lf-architect-new">
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-2">New Architect</div>
                      <div className="grid grid-cols-2 gap-3">
                        <Fld l="Name *" v={archDraft.name} oc={(v) => setArchDraft((d) => ({ ...d, name: v }))} t2="lf-arch-name" />
                        <Fld l="Phone *" v={archDraft.phone} oc={(v) => setArchDraft((d) => ({ ...d, phone: v }))} t2="lf-arch-phone" />
                        <Fld l="Firm Name" v={archDraft.firm} oc={(v) => setArchDraft((d) => ({ ...d, firm: v }))} t2="lf-arch-firm" />
                        <Fld l="Email" t="email" v={archDraft.email} oc={(v) => setArchDraft((d) => ({ ...d, email: v }))} t2="lf-arch-email" />
                      </div>
                      <div className="flex justify-end gap-2 mt-3">
                        <button type="button" className="btn-ghost" onClick={() => setArchDraft(null)}>Cancel</button>
                        <button type="button" className="btn-primary disabled:opacity-60" onClick={saveArchitect} disabled={archSaving} data-testid="lf-arch-save">
                          {archSaving ? "Saving…" : "Save & Select"}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
              <Fld l="Reference *" v={form.reference} oc={(v) => setForm({ ...form, reference: v })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">Division</label>
                <select value={form.division || ""} onChange={(e) => setForm({ ...form, division: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm" data-testid="lf-division">
                  <option value="">— Select —</option>
                  {DIVISIONS.map((d) => <option key={d}>{d}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">WhatsApp (if different)</label>
                <input value={form.whatsapp || ""} onChange={(e) => setForm({ ...form, whatsapp: e.target.value })} inputMode="tel"
                  className={`w-full px-3 py-2 rounded-lg border bg-[var(--color-surface)] text-sm outline-none ${waCheck.valid ? "border-[var(--color-border)]" : "border-[var(--color-danger)]"}`} data-testid="lf-whatsapp" />
                {!waCheck.valid && <div className="text-[11px] text-[var(--color-danger)] mt-1">{waCheck.message}</div>}
              </div>
              <Fld l="Email" t="email" v={form.email || ""} oc={(v) => setForm({ ...form, email: v })} t2="lf-email" />
              <Fld l="Location / Area" v={form.location || ""} oc={(v) => setForm({ ...form, location: v })} t2="lf-location" />
              <Fld l="Requirement" v={form.requirement || ""} oc={(v) => setForm({ ...form, requirement: v })} cls="col-span-2" t2="lf-requirement" />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">Priority</label>
                <select value={form.priority || "Medium"} onChange={(e) => setForm({ ...form, priority: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm" data-testid="lf-priority">
                  {PRIORITIES.map((p) => <option key={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">Attended by</label>
                <select value={form.attended_by} onChange={(e) => setForm({ ...form, attended_by: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm">
                  <option value="">— Select —</option>
                  {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">Stage</label>
                <select value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm">
                  {STAGES.map((s) => <option key={s}>{s}</option>)}
                </select>
              </div>
              <Fld l="Follow up" t="date" v={form.follow_up_date} oc={(v) => setForm({ ...form, follow_up_date: v })} />
              <Fld l="Next action" v={form.next_action || ""} oc={(v) => setForm({ ...form, next_action: v })} cls="col-span-2" t2="lf-next-action" />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">Assigned to (Staff)</label>
                <SearchSelect
                  options={staffOptions}
                  value={form.assigned_to_id}
                  onChange={(id, opt) => setForm({ ...form, assigned_to_id: id, assigned_to: opt ? opt.name : "" })}
                  placeholder="Search staff by name…"
                  emptyLabel="No staff found"
                  testId="lf-assigned"
                />
                {!form.assigned_to_id && form.assigned_to && (
                  <div className="text-[11px] text-[var(--color-text-muted)] mt-1">Currently: {form.assigned_to} (unlinked — pick from the list to link)</div>
                )}
              </div>
              <StarRating label="Confidence" testId="lead-confidence" value={form.confidence_level}
                onChange={(pct) => setForm({ ...form, confidence_level: pct })} />
              <Fld l="Estimated budget / value (₹)" t="number" v={form.value} oc={(v) => setForm({ ...form, value: parseFloat(v) || 0 })} />
              <div className="col-span-2">
                <RemarksTimeline
                  entries={form.remarks_history}
                  authorName={user?.name || ""}
                  onAdd={(entry) => setForm((f) => ({ ...f, remarks_history: [...(f.remarks_history || []), entry] }))}
                />
              </div>
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
        <div className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center sm:p-4" onClick={closeLog}>
          <div className="bg-[var(--color-surface)] rounded-t-2xl sm:rounded-xl border border-[var(--color-border)] w-full max-w-xl shadow-2xl max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">{logLead.name}</h3>
              <button onClick={closeLog} className="p-1.5 rounded-md hover:bg-[var(--color-surface-muted)]" aria-label="Close"><X size={16} /></button>
            </div>
            <div className="p-4 sm:p-5 space-y-4">
              <div className="text-xs text-[var(--color-text-muted)] space-y-0.5">
                <div>{[logLead.phone, logLead.email, logLead.location].filter(Boolean).join(" · ") || "No contact details"}</div>
                <div>{[logLead.division, logLead.source, logLead.assigned_to && `Owner: ${logLead.assigned_to}`, logLead.value ? inrFull(logLead.value) : ""].filter(Boolean).join(" · ")}</div>
                {logLead.requirement && <div>Requirement: {logLead.requirement}</div>}
                <div>Next: <b className="text-[var(--color-text)]">{logLead.next_action || "—"}</b>{logLead.follow_up_date ? ` on ${fmtDate(logLead.follow_up_date)}` : ""}</div>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {logLead.phone && <a href={`tel:${logLead.phone}`} className="btn-ghost justify-center"><Phone size={14} /> Call</a>}
                {(logLead.whatsapp || logLead.phone) && (
                  <a href={`https://wa.me/91${String(logLead.whatsapp || logLead.phone).replace(/\D/g, "").slice(-10)}`} target="_blank" rel="noreferrer" className="btn-ghost justify-center">WhatsApp</a>
                )}
                {canCreate && <button className="btn-ghost justify-center" disabled={!!converting} onClick={() => convert(logLead, "quote")} data-testid="lead-to-quote">{converting === "quote" ? "Creating…" : "Create quotation"}</button>}
                {canCreate && <button className="btn-primary justify-center" disabled={!!converting} onClick={() => convert(logLead, "project")} data-testid="lead-to-project">{converting === "project" ? "Starting…" : "Start project"}</button>}
              </div>
              <StagePath wf={lw} value={logLead.stage} record={logLead} canEdit={canEdit}
                         onChange={(stage) => updateStage(logLead, stage)} />
              <StageProgressBar stages={leadLifecycleStages(logLead)} />
              <LogTimeline
                entity="lead" itemId={logLead.id} entries={logLead.log || []}
                onAppended={(log) => {
                  setLogLead((p) => ({ ...p, log }));
                  setRows((p) => p.map((x) => x.id === logLead.id ? { ...x, log } : x));
                }}
              />
              <LinkedTasksPanel refId={logLead.id} refType="lead" entityName={logLead.name} />
              <AttachmentPanel entity="lead" itemId={logLead.id} />
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
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">{l}</label>
      <input type={t} value={v} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm outline-none focus:border-[var(--color-primary)]" data-testid={t2} />
    </div>
  );
}
