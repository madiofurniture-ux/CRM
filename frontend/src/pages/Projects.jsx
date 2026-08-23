import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { HardHat, Compass, FileText, Wrench, CheckCircle2, Flag, ChevronRight, X, UserCheck, Calendar, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";

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
  const [activeStage, setActiveStage] = useState("All");
  const [search, setSearch] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);

  const emptyForm = {
    project_no: `PRJ-${Math.floor(1000 + Math.random() * 9000)}`,
    customer: "",
    phone: "",
    division: "Furniture",
    value: 0,
    paid: 0,
    stage: "Survey",
    site_address: "",
    assigned_engineer: "",
    start_date: new Date().toISOString().split("T")[0],
    target_date: "",
    remarks: "",
    quote_ref: "",
  };
  const [form, setForm] = useState(emptyForm);

  const load = async () => {
    try {
      const { data } = await api.get("/projects");
      setRows(data);
    } catch {
      toast.error("Failed to load projects");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return rows.filter((r) => {
      const matchStage = activeStage === "All" || r.stage === activeStage;
      const matchQuery =
        !q ||
        r.customer.toLowerCase().includes(q) ||
        r.project_no.toLowerCase().includes(q) ||
        (r.site_address || "").toLowerCase().includes(q) ||
        (r.assigned_engineer || "").toLowerCase().includes(q);
      return matchStage && matchQuery;
    });
  }, [rows, activeStage, search]);

  const advanceStage = async (p, nextStage) => {
    try {
      await api.put(`/projects/${p.id}/stage`, { stage: nextStage });
      toast.success(`Project ${p.project_no} moved to ${nextStage}`);
      load();
    } catch {
      toast.error("Failed to update project stage");
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
    if (!form.customer || !form.project_no) {
      toast.error("Please fill required fields");
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
    } catch {
      toast.error(editing ? "Failed to update project" : "Failed to create project");
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
    } catch {
      toast.error("Failed to delete project");
    }
  };

  const totalValue = filtered.reduce((a, b) => a + (b.value || 0), 0);
  const totalPaid = filtered.reduce((a, b) => a + (b.paid || 0), 0);

  return (
    <>
      <Topbar
        title="Project Execution Workflow"
        subtitle={`${filtered.length} projects · Value ${inrFull(totalValue)} · Collected ${inrFull(totalPaid)}`}
        onAdd={openNew}
        addLabel="New Project"
      />

      <div className="p-6" data-testid="projects-page">
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
                <span>{s.label}</span>
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

        {/* Filter / Search input */}
        <div className="mb-5 flex items-center justify-between gap-4">
          <input
            type="text"
            placeholder="Search project #, customer, address, engineer..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-80 px-3.5 py-2 text-sm rounded-xl bg-white border border-[var(--border)] outline-none focus:border-[var(--brand)] transition"
          />
        </div>

        {/* Project Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filtered.map((p) => {
            const nextStage = NEXT_STAGE_MAP[p.stage];
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
                        onClick={() => remove(p)}
                        className="p-1 rounded hover:bg-red-50 text-red-600"
                        title="Delete project"
                        data-testid={`project-delete-${p.id}`}
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>

                  <h3 className="font-heading font-bold text-base text-[var(--ink)] mb-1">{p.customer}</h3>
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

                  <div className="flex items-center justify-between text-xs font-mono mb-4 pt-1">
                    <div>
                      <div className="text-[10px] text-[var(--ink-3)] uppercase tracking-wider">Value</div>
                      <div className="font-bold text-[var(--ink)]">{inrFull(p.value)}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] text-[var(--ink-3)] uppercase tracking-wider">Collected</div>
                      <div className="font-bold text-[var(--moss)]">{inrFull(p.paid)}</div>
                    </div>
                  </div>
                </div>

                <div className="pt-3 border-t border-[var(--border-light)] flex items-center justify-between gap-2">
                  <div className="text-[11px] text-[var(--ink-3)] flex items-center gap-1">
                    <Calendar size={12} />
                    <span>{p.target_date ? fmtDate(p.target_date) : "No target"}</span>
                  </div>

                  {nextStage ? (
                    <button
                      onClick={() => advanceStage(p, nextStage)}
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
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[var(--border)] w-full max-w-lg shadow-xl overflow-hidden animate-in fade-in zoom-in duration-150">
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
                    <option value="Furniture">Furniture</option>
                    <option value="MAP">MAP (Paints)</option>
                    <option value="D&W">D&W (Doors & Windows)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Customer Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Krishna Reddy"
                  value={form.customer}
                  onChange={(e) => setForm({ ...form, customer: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Phone Number</label>
                  <input
                    type="text"
                    placeholder="9876543210"
                    value={form.phone}
                    onChange={(e) => setForm({ ...form, phone: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                  />
                </div>
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
                    <option value="Survey">Survey</option>
                    <option value="Quoted">Quoted</option>
                    <option value="Execution">Execution</option>
                    <option value="Review">Review</option>
                    <option value="Closure">Closure</option>
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
    </>
  );
}
