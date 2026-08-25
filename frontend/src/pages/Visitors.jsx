import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import SearchSelect from "@/components/SearchSelect";
import api, { formatApiError } from "@/lib/api";
import { fmtDate, inrFull } from "@/lib/format";
import { validateIndianPhone } from "@/lib/phone";
import { toast } from "sonner";
import { Trash2, X, Phone, Pencil, Plus } from "lucide-react";

const STAGES = ["New", "Qualified", "Quoted", "Negotiation", "Won", "Lost", "Delivered"];
const isKnownStage = (s) => STAGES.some((x) => x.toLowerCase() === String(s || "").trim().toLowerCase());
const CUSTOMER_TYPES = ["Male", "Female", "Company"];

// Visitors' `remarks` is either the legacy plain string or the newer list of
// dated entries. Always normalize to a list for editing/display so both
// shapes work without the caller needing to know which one it got.
function toRemarksArray(remarks) {
  if (Array.isArray(remarks)) {
    return remarks
      .map((r) => (typeof r === "string" ? { id: r, text: r, at: null } : r))
      .filter((r) => r && String(r.text || "").trim());
  }
  if (typeof remarks === "string" && remarks.trim()) {
    return [{ id: "legacy", text: remarks.trim(), at: null }];
  }
  return [];
}

function newRemarkId() {
  return typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `r-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function Visitors() {
  const [rows, setRows] = useState([]);
  const [architects, setArchitects] = useState([]);
  const [staff, setStaff] = useState([]);
  const [search, setSearch] = useState("");
  const [fStage, setFStage] = useState("All");
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [remarkDraft, setRemarkDraft] = useState("");
  const [editingRemarkId, setEditingRemarkId] = useState(null);
  const [editingRemarkText, setEditingRemarkText] = useState("");
  const empty = {
    date: new Date().toISOString().slice(0, 10), name: "", customer_type: "Male", location: "",
    reference: "", reference_id: "", phone: "", requirement: "",
    attend_person: "", attend_person_id: "", remarks: [], status: "New", stage: "New", ticket_value: 0,
  };
  const [form, setForm] = useState(empty);

  const load = async () => { const { data } = await api.get("/visitors"); setRows(data); };
  const loadRefs = async () => {
    const [a, s] = await Promise.all([api.get("/architects"), api.get("/staff")]);
    setArchitects(a.data);
    setStaff(s.data);
  };
  useEffect(() => { load(); loadRefs(); }, []);

  const architectOptions = useMemo(() => architects.map((a) => ({
    id: a.id,
    name: a.name,
    label: (a.type === "Architect" ? "Ar. " : "") + a.name,
    sub: [a.firm, a.type, a.location].filter(Boolean).join(" · "),
  })), [architects]);

  const staffOptions = useMemo(() => staff.map((s) => ({
    id: s.id,
    name: s.name || s.username,
    label: s.name || s.username,
    sub: s.username && s.username !== s.name ? `@${s.username}` : "",
  })), [staff]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return rows.filter((r) => {
      const stage = String(r.stage || "New").trim().toLowerCase();
      return (fStage === "All" || stage === fStage.toLowerCase()) &&
        (!q || (r.name || "").toLowerCase().includes(q) || (r.requirement || "").toLowerCase().includes(q) || (r.reference || "").toLowerCase().includes(q));
    });
  }, [rows, search, fStage]);

  const phoneCheck = useMemo(() => validateIndianPhone(form.phone), [form.phone]);
  const sortedRemarks = useMemo(() => {
    return [...toRemarksArray(form.remarks)].sort((a, b) => String(b.at || "").localeCompare(String(a.at || "")));
  }, [form.remarks]);

  const addRemark = () => {
    const text = remarkDraft.trim();
    if (!text) return;
    const entry = { id: newRemarkId(), text, at: new Date().toISOString() };
    setForm((f) => ({ ...f, remarks: [entry, ...toRemarksArray(f.remarks)] }));
    setRemarkDraft("");
  };

  const startEditRemark = (r) => { setEditingRemarkId(r.id); setEditingRemarkText(r.text); };
  const cancelEditRemark = () => { setEditingRemarkId(null); setEditingRemarkText(""); };
  const saveEditRemark = () => {
    const text = editingRemarkText.trim();
    if (!text) return;
    setForm((f) => ({
      ...f,
      remarks: toRemarksArray(f.remarks).map((r) => (r.id === editingRemarkId ? { ...r, text } : r)),
    }));
    cancelEditRemark();
  };
  const deleteRemark = (id) => {
    if (!window.confirm("Delete this remark?")) return;
    setForm((f) => ({ ...f, remarks: toRemarksArray(f.remarks).filter((r) => r.id !== id) }));
    if (editingRemarkId === id) cancelEditRemark();
  };

  const openNew = () => { setEditing(null); setForm(empty); setRemarkDraft(""); cancelEditRemark(); setShow(true); };
  const openEdit = (v) => {
    setEditing(v);
    setForm({ ...empty, ...v, customer_type: v.customer_type || "Male", remarks: toRemarksArray(v.remarks) });
    setRemarkDraft("");
    cancelEditRemark();
    setShow(true);
  };

  const save = async () => {
    if (saving) return;
    if (!phoneCheck.valid) { toast.error(phoneCheck.message); return; }
    setSaving(true);
    const payload = { ...form, phone: phoneCheck.normalized, remarks: toRemarksArray(form.remarks) };
    try {
      if (editing) {
        await api.put(`/visitors/${editing.id}`, payload);
        toast.success("Visitor updated");
      } else {
        await api.post("/visitors", payload);
        toast.success("Visitor logged");
      }
      setShow(false); setEditing(null); setForm(empty); load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Save failed");
    } finally {
      setSaving(false);
    }
  };
  const updateStage = async (v, stage) => {
    await api.put(`/visitors/${v.id}`, { ...v, stage });
    setRows((p) => p.map((x) => x.id === v.id ? { ...x, stage } : x));
  };
  const remove = async (id) => { if (!window.confirm("Delete?")) return; await api.delete(`/visitors/${id}`); load(); };

  return (
    <>
      <Topbar title="Visitors" subtitle={`${filtered.length} walk-ins · today's lobby`} onAdd={openNew} addLabel="Log Visitor" />
      <div className="p-6" data-testid="visitors-page">
        <div className="flex flex-wrap gap-2 mb-4">
          <input placeholder="Search name, requirement, reference…" value={search} onChange={(e) => setSearch(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] w-80" data-testid="visitors-search" />
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
                  <th className="text-left font-semibold px-4 py-2.5">Reference</th>
                  <th className="text-left font-semibold px-4 py-2.5">Requirement</th>
                  <th className="text-left font-semibold px-4 py-2.5">Attended by</th>
                  <th className="text-left font-semibold px-4 py-2.5">Stage</th>
                  <th className="text-right font-semibold px-4 py-2.5">Ticket</th>
                  <th className="w-20"></th>
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
                      <select value={v.stage || "New"} onChange={(e) => updateStage(v, e.target.value)} className="px-2 py-1 rounded-md border border-[var(--border)] bg-white text-xs" title={!isKnownStage(v.stage) ? "Legacy/imported value — pick a stage to normalize it" : undefined}>
                        {v.stage && !isKnownStage(v.stage) && <option value={v.stage}>{v.stage} (unrecognized)</option>}
                        {STAGES.map((s) => <option key={s}>{s}</option>)}
                      </select>
                    </td>
                    <td className="px-4 py-3 text-right font-mono">{inrFull(v.ticket_value)}</td>
                    <td className="px-2 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => openEdit(v)} className="p-1.5 rounded-md hover:bg-[var(--surface-2)] text-[var(--ink-2)]" title="Edit visitor" data-testid={`visitor-edit-${v.id}`}><Pencil size={13} /></button>
                        <button onClick={() => remove(v.id)} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]" title="Delete visitor"><Trash2 size={13} /></button>
                      </div>
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
          <div className="bg-white rounded-xl border border-[var(--border)] w-full max-w-xl shadow-2xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b sticky top-0 bg-white">
              <h3 className="font-heading font-semibold text-lg">{editing ? "Edit Visitor" : "Log Visitor"}</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Customer Type</label>
                <div className="flex gap-2">
                  {CUSTOMER_TYPES.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setForm({ ...form, customer_type: t })}
                      className={`px-3 py-1.5 rounded-lg border text-sm font-medium transition ${form.customer_type === t ? "bg-[var(--brand)] text-white border-[var(--brand)]" : "border-[var(--border)] bg-white text-[var(--ink-2)] hover:bg-[var(--surface-2)]"}`}
                      data-testid={`vf-ctype-${t.toLowerCase()}`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>

              <Fld l={form.customer_type === "Company" ? "Company Name" : "Name"} v={form.name} oc={(v) => setForm({ ...form, name: v })} t2="vf-name" />

              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Phone</label>
                <input
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  placeholder="9876543210 or +919876543210"
                  className={`w-full px-3 py-2 rounded-lg border bg-white text-sm outline-none ${phoneCheck.valid ? "border-[var(--border)] focus:border-[var(--brand)]" : "border-[var(--danger)] focus:border-[var(--danger)]"}`}
                  data-testid="vf-phone"
                />
                {!phoneCheck.valid && <div className="text-[11px] text-[var(--danger)] mt-1" data-testid="vf-phone-error">{phoneCheck.message}</div>}
              </div>

              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Reference (Architect)</label>
                <SearchSelect
                  options={architectOptions}
                  value={form.reference_id}
                  onChange={(id, opt) => setForm({ ...form, reference_id: id, reference: opt ? opt.name : "" })}
                  placeholder="Search architect by name, firm…"
                  emptyLabel="No architects found — add one on the Architects page"
                  testId="vf-ref"
                />
                {!form.reference_id && form.reference && (
                  <div className="text-[11px] text-[var(--ink-3)] mt-1">Currently: {form.reference} (unlinked — pick from the list to link)</div>
                )}
              </div>

              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Attended by (Staff)</label>
                <SearchSelect
                  options={staffOptions}
                  value={form.attend_person_id}
                  onChange={(id, opt) => setForm({ ...form, attend_person_id: id, attend_person: opt ? opt.name : "" })}
                  placeholder="Search staff by name…"
                  emptyLabel="No staff found"
                  testId="vf-by"
                />
                {!form.attend_person_id && form.attend_person && (
                  <div className="text-[11px] text-[var(--ink-3)] mt-1">Currently: {form.attend_person} (unlinked — pick from the list to link)</div>
                )}
              </div>

              <Fld l="Requirement" v={form.requirement} oc={(v) => setForm({ ...form, requirement: v })} cls="col-span-2" t2="vf-req" />

              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Stage</label>
                <select value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value, status: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm" data-testid="vf-stage">
                  {STAGES.map((s) => <option key={s}>{s}</option>)}
                </select>
              </div>

              <div className="col-span-2">
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Remarks</label>
                <div className="flex gap-2 mb-2">
                  <input
                    value={remarkDraft}
                    onChange={(e) => setRemarkDraft(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addRemark(); } }}
                    placeholder="Add a remark…"
                    className="flex-1 px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]"
                    data-testid="vf-remark-draft"
                  />
                  <button type="button" onClick={addRemark} className="btn-ghost shrink-0" data-testid="vf-remark-add">
                    <Plus size={14} /> Add Remark
                  </button>
                </div>
                <div className="max-h-52 overflow-y-auto space-y-2 border border-[var(--border-light)] rounded-lg p-2 bg-[var(--surface-2)]" data-testid="vf-remark-list">
                  {sortedRemarks.length === 0 && <div className="text-xs text-[var(--ink-3)] px-1 py-2">No remarks yet</div>}
                  {sortedRemarks.map((r, i) => (
                    <div key={r.id || i} className="bg-white border border-[var(--border-light)] rounded-md px-3 py-2">
                      {editingRemarkId === r.id ? (
                        <div className="flex gap-2">
                          <input
                            autoFocus
                            value={editingRemarkText}
                            onChange={(e) => setEditingRemarkText(e.target.value)}
                            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); saveEditRemark(); } if (e.key === "Escape") cancelEditRemark(); }}
                            className="flex-1 px-2 py-1 rounded-md border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]"
                            data-testid={`vf-remark-edit-input-${r.id}`}
                          />
                          <button type="button" onClick={saveEditRemark} className="btn-primary px-2 py-1 text-xs" data-testid={`vf-remark-save-${r.id}`}>Save</button>
                          <button type="button" onClick={cancelEditRemark} className="btn-ghost px-2 py-1 text-xs">Cancel</button>
                        </div>
                      ) : (
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="text-[11px] text-[var(--ink-3)]">{r.at ? fmtDate(r.at) : "Earlier"}</div>
                            <div className="text-sm text-[var(--ink)] break-words">{r.text}</div>
                          </div>
                          <div className="flex items-center gap-1 shrink-0">
                            <button type="button" onClick={() => startEditRemark(r)} className="p-1 rounded hover:bg-[var(--surface-2)] text-[var(--ink-2)]" title="Edit remark" data-testid={`vf-remark-edit-${r.id}`}><Pencil size={12} /></button>
                            <button type="button" onClick={() => deleteRemark(r.id)} className="p-1 rounded hover:bg-[var(--danger-soft)] text-[var(--danger)]" title="Delete remark" data-testid={`vf-remark-delete-${r.id}`}><Trash2 size={12} /></button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2 sticky bottom-0 bg-white">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary disabled:opacity-60" onClick={save} disabled={saving || !phoneCheck.valid} data-testid="visitor-save">
                {saving ? "Saving…" : editing ? "Save Changes" : "Log Visitor"}
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
