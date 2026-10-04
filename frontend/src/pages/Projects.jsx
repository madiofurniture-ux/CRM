import { useEffect, useState, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import usePersistedState from "@/hooks/usePersistedState";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import LogTimeline from "@/components/LogTimeline";
import AttachmentPanel from "@/components/AttachmentPanel";
import PettyCashBurnWidget from "@/components/PettyCashBurnWidget";
import LinkedTasksPanel from "@/components/LinkedTasksPanel";
import StageProgressBar from "@/components/StageProgressBar";
import StagePath from "@/components/StagePath";
import useWorkflow, { stageErrorMessage } from "@/hooks/useWorkflow";
import StakeholdersCard from "@/components/StakeholdersCard";
import ProjectTrackingTab from "@/components/ProjectTrackingTab";
import JourneyDrawer from "@/components/JourneyDrawer";
import ProjectOpsPanel from "@/components/ProjectOpsPanel";
import { useTenantConfig } from "@/context/TenantConfigContext";
import { usePrivacyMode } from "@/context/PrivacyModeContext";
import { projectLifecycleStages } from "@/lib/lifecycle";
import api from "@/lib/api";
import { inrFull, fmtDate, marginTone, todayIST } from "@/lib/format";
import { HardHat, Compass, FileText, Wrench, CheckCircle2, Flag, ChevronRight, X, UserCheck, Calendar, Pencil, Trash2, FolderOpen, Phone, MessageCircle } from "lucide-react";
import { toast } from "sonner";
import CustomerProjectPicker from "@/components/CustomerProjectPicker";
import ColumnFilters from "@/components/ColumnFilters";
import useColumnFilters from "@/hooks/useColumnFilters";

const COLUMNS = [
  { key: "project_no", label: "Project #", type: "text" },
  { key: "project_name", label: "Project name", type: "text" },
  { key: "customer", label: "Customer", type: "text" },
  { key: "phone", label: "Phone", type: "text" },
  { key: "site_address", label: "Site", type: "text" },
  { key: "stage", label: "Stage", type: "select" },
  { key: "project_type", label: "Type", type: "select" },
  { key: "assigned_engineer", label: "Engineer", type: "select" },
  { key: "project_manager", label: "Project manager", type: "select" },
  { key: "start_date", label: "Start", type: "date" },
  { key: "target_date", label: "Target", type: "date" },
  { key: "value", label: "Value", type: "number" },
  { key: "linked", label: "Customer link", type: "select", get: (r) => (r.customer_id ? "Linked" : "Not linked"), options: ["Linked", "Not linked"] },
];

const STAGES = [
  { id: "Survey", label: "Survey", icon: Compass, color: "#D48B30" },
  { id: "Quoted", label: "Quoted", icon: FileText, color: "#3B82F6" },
  { id: "Execution", label: "Execution", icon: Wrench, color: "#C85A32" },
  { id: "Review", label: "Review", icon: CheckCircle2, color: "#8B5CF6" },
  { id: "Closure", label: "Closure", icon: Flag, color: "#4A5D4E" },
];

const NEXT_STAGE_MAP = {
  Survey: "Quoted",
  Quoted: "Execution",
  Execution: "Review",
  Review: "Closure",
};

export default function Projects() {
  const [rows, setRows] = useState([]);
  const [activeStage, setActiveStage] = usePersistedState("projects.stage", "All");
  const [search, setSearch] = useState("");
  const cf = useColumnFilters("projects", COLUMNS);
  const applyColumns = cf.apply;
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [logProject, setLogProject] = useState(null);
  const pw = useWorkflow("project", STAGES.map((s) => s.id));
  // A workflow that restricts transitions decides the "Move to" button;
  // otherwise the fixed build order below does.
  const nextStageOf = (stage) => {
    const st = pw.stageOf(stage);
    if (st?.next?.length) {
      const first = pw.stages.find((s) => st.next.includes(s.key));
      if (first) return first.label;
    }
    return NEXT_STAGE_MAP[stage];
  };
  // Customer-360 slide-over, keyed on phone — this app joins a customer's
  // history by phone number, not by a customer_id foreign key (a Project
  // stores `customer` as a plain display string). Same drawer Customers.jsx
  // and Alerts.jsx already open.
  const [jny, setJny] = useState(null);

  const emptyForm = {
    project_no: `PRJ-${Math.floor(1000 + Math.random() * 9000)}`,
    customer: "",
    customer_id: "",
    phone: "",
    division: "Furniture",
    value: 0,
    paid: 0,
    stage: "Survey",
    site_address: "",
    assigned_engineer: "",
    start_date: todayIST(),
    target_date: "",
    remarks: "",
    quote_ref: "",
    project_name: "",
    project_type: "",
    project_manager: "",
    architect_name: "",
  };
  const [form, setForm] = useState(emptyForm);
  const [searchParams, setSearchParams] = useSearchParams();
  const [pnlByProject, setPnlByProject] = useState({});
  const [divisionFilter, setDivisionFilter] = usePersistedState("projects.division", "All");
  const [divisionPulse, setDivisionPulse] = useState([]);
  const { divisions } = useTenantConfig();
  const { isOtherHidden } = usePrivacyMode();

  const load = async () => {
    try {
      const { data } = await api.get("/projects");
      setRows(data);
    } catch {
      toast.error("Failed to load projects");
    }
  };

  const loadDivisionPulse = () => {
    api.get("/reports/division-pulse").then(({ data }) => setDivisionPulse(data)).catch(() => setDivisionPulse([]));
  };

  useEffect(() => {
    load();
    loadDivisionPulse();
  }, []);

  // /projects?open=<id> (global search, service tickets, customer 360) opens
  // that project's detail directly.
  useEffect(() => {
    const id = searchParams.get("open");
    if (!id || !rows.length) return;
    const p = rows.find((r) => r.id === id);
    if (p) setLogProject(p);
  }, [searchParams, rows]);
  const closeDetail = () => {
    setLogProject(null);
    if (searchParams.get("open")) { searchParams.delete("open"); setSearchParams(searchParams, { replace: true }); }
  };

  // Margin is masked server-side under Privacy Mode, so this refetches on
  // unlock/relock instead of holding a stale figure.
  useEffect(() => {
    api.get("/reports/project-pnl", { params: { mask_other: isOtherHidden } })
      .then(({ data }) => setPnlByProject(Object.fromEntries(data.projects.map((p) => [p.project_id, p]))))
      .catch(() => setPnlByProject({}));
  }, [isOtherHidden]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    const base = rows.filter((r) => {
      const matchStage = activeStage === "All" || r.stage === activeStage;
      const matchDivision = divisionFilter === "All" || r.division === divisionFilter;
      const matchQuery =
        !q ||
        (r.customer || "").toLowerCase().includes(q) ||
        (r.project_no || "").toLowerCase().includes(q) ||
        (r.site_address || "").toLowerCase().includes(q) ||
        (r.project_name || "").toLowerCase().includes(q) ||
        (r.phone || "").includes(q) ||
        (r.assigned_engineer || "").toLowerCase().includes(q);
      return matchStage && matchDivision && matchQuery;
    });
    return applyColumns(base);
  }, [rows, activeStage, divisionFilter, search, applyColumns]);

  const advanceStage = async (p, nextStage) => {
    try {
      const { data } = await api.put(`/projects/${p.id}/stage`, { stage: nextStage });
      toast.success(`Project ${p.project_no} moved to ${nextStage}`);
      setLogProject((cur) => (cur && cur.id === p.id ? { ...cur, ...data } : cur));
      load();
    } catch (e) {
      // Workflow gates (required fields / allowed next stages) explain themselves.
      toast.error(stageErrorMessage(e));
      throw e;
    }
  };

  const openNew = () => {
    setEditing(null);
    setForm(emptyForm);
    setShowModal(true);
  };

  const openEdit = (p) => {
    setEditing(p);
    setForm({ ...emptyForm, ...p });
    setShowModal(true);
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (saving) return;
    if ((!form.customer && !form.customer_id) || !form.project_no) {
      toast.error("Pick the customer (or add a new one) and give the project a number");
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await api.put(`/projects/${editing.id}`, form);
        toast.success("Project updated");
      } else {
        await api.post("/projects", form);
        toast.success("Project created successfully");
      }
      setShowModal(false);
      setForm(emptyForm);
      load();
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : editing ? "Failed to update project" : "Failed to create project");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (p) => {
    if (!window.confirm(`Delete project "${p.project_no}" for ${p.customer}?`)) return;
    try {
      await api.delete(`/projects/${p.id}`);
      toast.success("Project deleted");
      load();
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Failed to delete project");
    }
  };

  const totalValue = filtered.reduce((a, b) => a + (b.value || 0), 0);
  const totalPaid = filtered.reduce((a, b) => a + (b.paid || 0), 0);

  return (
    <>
      <Topbar
        title="Projects"
        subtitle={`${filtered.length} projects · Value ${inrFull(totalValue)} · Collected ${inrFull(totalPaid)}`}
        onAdd={openNew}
        addLabel="New Project"
      />

      <div className="p-3 sm:p-6" data-testid="projects-page">
        {/* Stage Workflow Pipeline Bar */}
        <div className="flex items-center gap-2 mb-6 overflow-x-auto pb-2">
          <button
            onClick={() => setActiveStage("All")}
            className={`px-3.5 py-2 rounded-xl text-xs font-semibold transition border ${
              activeStage === "All"
                ? "bg-[var(--ink)] text-white border-[var(--ink)] shadow-sm"
                : "bg-white text-[var(--ink-2)] border-[var(--border)] hover:bg-[var(--surface-hover)]"
            }`}
          >
            All Projects ({rows.length})
          </button>
          {STAGES.map((s) => {
            const Icon = s.icon;
            const count = rows.filter((r) => r.stage === s.id).length;
            const isActive = activeStage === s.id;
            const activeDivision = divisionFilter !== "All" ? divisions.find((d) => d.slug === divisionFilter) : null;
            const label = activeDivision?.stage_labels?.[s.id] || s.label;
            return (
              <button
                key={s.id}
                onClick={() => setActiveStage(s.id)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition border ${
                  isActive
                    ? "bg-white text-[var(--ink)] border-[var(--brand)] shadow-sm ring-1 ring-[var(--brand)]"
                    : "bg-white text-[var(--ink-2)] border-[var(--border)] hover:bg-[var(--surface-hover)]"
                }`}
              >
                <Icon size={14} style={{ color: s.color }} />
                <span>{label}</span>
                <span
                  className="px-1.5 py-0.5 rounded-full text-[10px] font-mono"
                  style={{
                    backgroundColor: isActive ? "var(--brand-light)" : "var(--surface-2)",
                    color: isActive ? "var(--brand)" : "var(--ink-2)",
                  }}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Division health overview */}
        {divisionPulse.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5" data-testid="division-health-card">
            {divisionPulse.map((d) => (
              <div key={d.division} className="bg-white border border-[var(--border)] rounded-xl p-3.5">
                <div className="text-xs font-semibold text-[var(--ink)] mb-2">{d.division}</div>
                <div className="flex items-center justify-between text-[11px] text-[var(--ink-2)]">
                  <span>{d.active_project_count} active</span>
                  <span>{inrFull(d.total_contract_value)}</span>
                </div>
                <div className="flex items-center justify-between text-[11px] text-[var(--ink-2)] mt-1">
                  <span>Avg completion {d.average_completion_percentage}%</span>
                  {d.flagged_hindrances > 0 && (
                    <span className="text-amber-700 font-medium">{d.flagged_hindrances} hindrance{d.flagged_hindrances === 1 ? "" : "s"}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Filter / Search input */}
        <div className="mb-5 flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-4">
          <input
            type="text"
            placeholder="Search project #, customer, address, engineer..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full sm:w-80 px-3.5 py-2 text-sm rounded-xl bg-white border border-[var(--border)] outline-none focus:border-[var(--brand)] transition"
          />
          <select
            value={divisionFilter}
            onChange={(e) => setDivisionFilter(e.target.value)}
            className="px-3 py-2 text-sm rounded-xl bg-white border border-[var(--border)] outline-none focus:border-[var(--brand)]"
            data-testid="division-filter"
          >
            <option value="All">All Divisions</option>
            {divisions.map((d) => (
              <option key={d.id} value={d.slug}>{d.name}</option>
            ))}
          </select>
        </div>
        <div className="mb-5 -mt-2">
          <ColumnFilters filters={cf} rows={rows} shown={filtered.length} testid="projects-filters" />
        </div>

        {/* Project Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filtered.map((p) => {
            const nextStage = nextStageOf(p.stage);
            return (
              <div
                key={p.id}
                className="bg-white border border-[var(--border)] rounded-2xl p-5 shadow-sm hover:shadow-md transition flex flex-col justify-between"
                data-testid={`project-card-${p.id}`}
              >
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded bg-[var(--surface-2)] text-[var(--ink-2)]">
                      {p.project_no}
                    </span>
                    <div className="flex items-center gap-1.5">
                      <StageBadge stage={p.stage} />
                      <button
                        onClick={() => openEdit(p)}
                        className="p-1 rounded hover:bg-[var(--surface-2)] text-[var(--ink-2)]"
                        title="Edit project"
                        data-testid={`project-edit-${p.id}`}
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        onClick={() => setLogProject(p)}
                        className="p-1 rounded hover:bg-[var(--surface-2)] text-[var(--ink-2)]"
                        title="Open project"
                        data-testid={`project-log-${p.id}`}
                      >
                        <FolderOpen size={13} />
                      </button>
                      <button
                        onClick={() => remove(p)}
                        className="p-1 rounded hover:bg-red-50 text-red-600"
                        title="Delete project"
                        data-testid={`project-delete-${p.id}`}
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>

                  {p.customer_id ? (
                    <Link to={`/customers/${p.customer_id}`}
                      className="block font-heading font-bold text-base text-[var(--ink)] mb-1 hover:text-[var(--brand)] hover:underline"
                      title={`Open ${p.customer}`} data-testid={`project-customer-${p.id}`}>
                      {p.customer}
                    </Link>
                  ) : p.phone ? (
                    <button
                      type="button"
                      onClick={() => setJny({ phone: p.phone, name: p.customer })}
                      className="font-heading font-bold text-base text-[var(--ink)] mb-1 text-left hover:text-[var(--brand)] hover:underline"
                      title={`Open ${p.customer}'s full history`}
                      data-testid={`project-customer-${p.id}`}
                    >
                      {p.customer}
                    </button>
                  ) : (
                    // No phone means nothing to join the history on, so this
                    // stays plain text rather than a control that does nothing.
                    <h3 className="font-heading font-bold text-base text-[var(--ink)] mb-1">{p.customer}</h3>
                  )}
                  <Link to={`/projects/${p.id}`} className="block text-xs text-[var(--brand)] hover:underline -mt-0.5 mb-1" data-testid={`project-open-${p.id}`}>
                    {p.project_name || "Open project"} →
                  </Link>
                  <div className="text-xs text-[var(--ink-2)] mb-3 flex items-center gap-1.5">
                    <span className="font-medium text-[var(--brand)] bg-[var(--brand-light)] px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider">
                      {p.division}
                    </span>
                    <span>·</span>
                    <span>{p.phone || "No contact"}</span>
                  </div>

                  <div className="text-xs text-[var(--ink-2)] mb-4 bg-[var(--surface-2)] p-2.5 rounded-xl border border-[var(--border-light)] space-y-1">
                    <div className="flex items-start gap-1.5">
                      <span className="text-[var(--ink-3)] font-semibold shrink-0">Site:</span>
                      <span className="truncate">{p.site_address || "Not specified"}</span>
                    </div>
                    {p.assigned_engineer && (
                      <div className="flex items-center gap-1.5 text-[11px]">
                        <UserCheck size={12} className="text-[var(--brand)] shrink-0" />
                        <span>Lead/Engineer: <strong>{p.assigned_engineer}</strong></span>
                      </div>
                    )}
                    {p.remarks && (
                      <div className="text-[11px] text-[var(--ink-3)] italic pt-1 border-t border-[var(--border-light)]">
                        "{p.remarks}"
                      </div>
                    )}
                  </div>

                  <button type="button" onClick={() => setLogProject(p)} className="w-full text-left mb-3" data-testid={`project-progress-${p.id}`}>
                    <div className="flex items-center justify-between text-[11px] mb-1">
                      <span className="text-[var(--ink-2)]">
                        {p.current_milestone ? <>Next: <b className="text-[var(--ink)]">{p.current_milestone}</b></> : "Open stage checklist"}
                      </span>
                      <span className="font-mono text-[var(--ink-3)]">{p.completion_percentage || 0}%</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-[var(--surface-2)] overflow-hidden">
                      <div className="h-full bg-[var(--moss)]" style={{ width: `${Math.min(100, p.completion_percentage || 0)}%` }} />
                    </div>
                  </button>
                  {p.phone && (
                    <div className="flex gap-2 mb-3">
                      <a href={`tel:${p.phone}`} className="flex-1 inline-flex items-center justify-center gap-1.5 py-2 rounded-lg border border-[var(--border)] text-xs font-semibold text-[var(--ink)] hover:bg-[var(--surface-2)]">
                        <Phone size={13} /> Call
                      </a>
                      <a href={`https://wa.me/91${String(p.phone).replace(/\D/g, "").slice(-10)}`} target="_blank" rel="noreferrer"
                        className="flex-1 inline-flex items-center justify-center gap-1.5 py-2 rounded-lg border border-emerald-200 text-xs font-semibold text-emerald-700 hover:bg-emerald-50">
                        <MessageCircle size={13} /> WhatsApp
                      </a>
                    </div>
                  )}
                  <div className="flex items-center justify-between text-xs font-mono mb-2 pt-1">
                    <div>
                      <div className="text-[10px] text-[var(--ink-3)] uppercase tracking-wider">Value</div>
                      <div className="font-bold text-[var(--ink)]">{inrFull(p.value)}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] text-[var(--ink-3)] uppercase tracking-wider">Collected</div>
                      <div className="font-bold text-[var(--moss)]">{inrFull(p.paid)}</div>
                    </div>
                  </div>
                  {pnlByProject[p.id]?.wallet_count > 0 && (() => {
                    // null = withheld by the server under Privacy Mode, not 0%.
                    const masked = pnlByProject[p.id].margin_pct == null;
                    const tone = marginTone(pnlByProject[p.id].margin_pct);
                    return (
                      <div className="mb-4">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold ${masked ? "bg-[var(--surface-2)] text-[var(--ink-3)]" : `${tone.bg} ${tone.text}`}`} data-testid={`project-margin-${p.id}`}>
                          Margin {masked ? "••••••" : `${pnlByProject[p.id].margin_pct}%`}
                        </span>
                      </div>
                    );
                  })()}
                </div>

                <div className="pt-3 border-t border-[var(--border-light)] flex items-center justify-between gap-2">
                  <div className="text-[11px] text-[var(--ink-3)] flex items-center gap-1">
                    <Calendar size={12} />
                    <span>{p.target_date ? fmtDate(p.target_date) : "No target"}</span>
                  </div>

                  {nextStage ? (
                    <button
                      onClick={() => advanceStage(p, nextStage).catch(() => {})}
                      className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-[var(--brand-light)] text-[var(--brand)] font-medium text-xs hover:bg-[var(--brand)] hover:text-white transition"
                    >
                      <span>Move to {nextStage}</span>
                      <ChevronRight size={14} />
                    </button>
                  ) : (
                    <span className="text-xs font-medium text-[var(--moss)] flex items-center gap-1 bg-emerald-50 px-2.5 py-1 rounded-lg">
                      <CheckCircle2 size={13} />
                      Completed
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {filtered.length === 0 && (
          <div className="text-center py-16 bg-white border border-[var(--border)] rounded-2xl">
            <HardHat size={40} className="mx-auto text-[var(--ink-3)] mb-2" strokeWidth={1.2} />
            <h4 className="font-bold text-[var(--ink)]">No projects found</h4>
            <p className="text-xs text-[var(--ink-3)] mt-1">Try switching stage filters or create a new project workflow.</p>
          </div>
        )}
      </div>

      {/* New Project Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center sm:p-4">
          <div className="bg-white rounded-t-2xl sm:rounded-2xl border border-[var(--border)] w-full max-w-lg shadow-xl max-h-[95vh] overflow-y-auto animate-in fade-in zoom-in duration-150">
            <div className="px-6 py-4 border-b border-[var(--border)] flex items-center justify-between bg-[var(--surface-2)]">
              <h3 className="font-heading font-bold text-base text-[var(--ink)]">{editing ? "Edit Project" : "Create Project Workflow"}</h3>
              <button onClick={() => setShowModal(false)} className="p-1 rounded-lg text-[var(--ink-3)] hover:bg-white">
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSave} className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Project #</label>
                  <input
                    type="text"
                    required
                    value={form.project_no}
                    onChange={(e) => setForm({ ...form, project_no: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)] font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Division</label>
                  <select
                    value={form.division}
                    onChange={(e) => setForm({ ...form, division: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)] bg-white"
                  >
                    {divisions.map((d) => (
                      <option key={d.id} value={d.slug}>{d.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Project Name</label>
                  <input type="text" placeholder="e.g. Villa 12 living + dining" value={form.project_name || ""}
                    onChange={(e) => setForm({ ...form, project_name: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Project Type</label>
                  <select value={form.project_type || ""} onChange={(e) => setForm({ ...form, project_type: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)] bg-white">
                    {["", "Villa", "Apartment", "Independent House", "Office", "Showroom", "Hospitality", "Other"].map((t) => <option key={t} value={t}>{t || "—"}</option>)}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Customer *</label>
                {!form.customer_id && form.customer && (
                  <div className="text-xs text-[var(--warn)] mb-1.5">Typed as “{form.customer}”{form.phone ? ` · ${form.phone}` : ""} — not linked. Pick or add the customer to link it.</div>
                )}
                <CustomerProjectPicker customerId={form.customer_id} withProject={false} division={form.division}
                  onChange={({ customer }) => setForm((f) => ({ ...f, customer_id: customer?.id || "",
                    customer: customer ? customer.name : "", phone: customer ? (customer.phone || "") : "",
                    site_address: f.site_address || customer?.address || "" }))}
                  testid="project-cpp" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Assigned Lead/Engineer</label>
                  <input
                    type="text"
                    placeholder="e.g. Raghu MF"
                    value={form.assigned_engineer}
                    onChange={(e) => setForm({ ...form, assigned_engineer: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Project Manager</label>
                  <input type="text" value={form.project_manager || ""} onChange={(e) => setForm({ ...form, project_manager: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Architect / Designer</label>
                  <input type="text" value={form.architect_name || ""} onChange={(e) => setForm({ ...form, architect_name: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Start Date</label>
                  <input type="date" value={form.start_date || ""} onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Expected Completion</label>
                  <input type="date" value={form.target_date || ""} min={form.start_date || undefined} onChange={(e) => setForm({ ...form, target_date: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]" />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Site Address</label>
                <input
                  type="text"
                  placeholder="e.g. Villa 12, Banjara Hills"
                  value={form.site_address}
                  onChange={(e) => setForm({ ...form, site_address: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Project Value (₹)</label>
                  <input
                    type="number"
                    value={form.value}
                    onChange={(e) => setForm({ ...form, value: +e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)] font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Initial Stage</label>
                  <select
                    value={form.stage}
                    onChange={(e) => setForm({ ...form, stage: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)] bg-white"
                  >
                    {STAGES.map((s) => {
                      const formDivision = divisions.find((d) => d.slug === form.division);
                      return <option key={s.id} value={s.id}>{formDivision?.stage_labels?.[s.id] || s.label}</option>;
                    })}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Remarks / Survey Notes</label>
                <textarea
                  rows={2}
                  value={form.remarks}
                  onChange={(e) => setForm({ ...form, remarks: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-xs font-semibold rounded-lg border border-[var(--border)] hover:bg-[var(--surface-2)] transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-5 py-2 text-xs font-semibold rounded-lg bg-[var(--brand)] text-white hover:opacity-90 transition shadow-sm disabled:opacity-60"
                  data-testid="project-save"
                >
                  {saving ? "Saving…" : editing ? "Save Changes" : "Create Project"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <JourneyDrawer phone={jny?.phone} name={jny?.name} onClose={() => setJny(null)} />

      {logProject && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center sm:p-4" onClick={closeDetail}>
          <div className="bg-white rounded-t-2xl sm:rounded-xl border border-[var(--border)] w-full max-w-2xl shadow-2xl max-h-[96vh] overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="project-detail">
            <div className="sticky top-0 z-10 bg-white flex items-center justify-between px-4 sm:px-5 py-3 sm:py-4 border-b">
              <h3 className="font-heading font-semibold text-base sm:text-lg flex flex-wrap items-center gap-2">
                {logProject.project_no} · {logProject.customer}
                {pnlByProject[logProject.id]?.wallet_count > 0 && (() => {
                  const masked = pnlByProject[logProject.id].margin_pct == null;
                  const tone = marginTone(pnlByProject[logProject.id].margin_pct);
                  return (
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${masked ? "bg-[var(--surface-2)] text-[var(--ink-3)]" : `${tone.bg} ${tone.text}`}`} data-testid={`project-drawer-margin-${logProject.id}`}>
                      Margin {masked ? "••••••" : `${pnlByProject[logProject.id].margin_pct}%`}
                    </span>
                  );
                })()}
              </h3>
              <button onClick={closeDetail} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]" aria-label="Close"><X size={16} /></button>
            </div>
            <div className="p-3 sm:p-5 space-y-4">
              <ProjectOpsPanel
                project={logProject}
                onProjectUpdated={(updated) => {
                  setLogProject(updated);
                  setRows((p) => p.map((x) => x.id === updated.id ? { ...x, ...updated } : x));
                }}
              />
              <Link to={`/finance/pnl?project_id=${logProject.id}`} className="inline-flex text-sm font-medium text-[var(--color-primary)] hover:underline">
                View deal P&L: visitor to profit
              </Link>
              <StagePath wf={pw} value={logProject.stage} record={logProject}
                         onChange={(stage) => advanceStage(logProject, stage)} />
              <StageProgressBar stages={projectLifecycleStages(logProject, pnlByProject[logProject.id])} />
              <StakeholdersCard
                project={logProject}
                onUpdated={(updated) => {
                  setLogProject(updated);
                  setRows((p) => p.map((x) => x.id === updated.id ? updated : x));
                }}
              />
              <ProjectTrackingTab
                project={logProject}
                onProjectUpdated={(updated) => {
                  setLogProject(updated);
                  setRows((p) => p.map((x) => x.id === updated.id ? updated : x));
                }}
              />
              <PettyCashBurnWidget projectId={logProject.id} />
              <LogTimeline
                entity="project" itemId={logProject.id} entries={logProject.log || []}
                onAppended={(log) => {
                  setLogProject((p) => ({ ...p, log }));
                  setRows((p) => p.map((x) => x.id === logProject.id ? { ...x, log } : x));
                }}
              />
              <LinkedTasksPanel refId={logProject.id} refType="project" entityName={logProject.customer} />
              <AttachmentPanel entity="project" itemId={logProject.id} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
