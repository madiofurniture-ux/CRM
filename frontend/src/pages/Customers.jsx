import { useEffect, useState, useMemo } from "react";
import usePersistedState from "@/hooks/usePersistedState";
import Topbar from "@/components/Topbar";
import JourneyDrawer from "@/components/JourneyDrawer";
import StarRating from "@/components/StarRating";
import SavedViewsBar from "@/components/SavedViewsBar";
import CustomFieldInput from "@/components/CustomFieldInput";
import CsvImportModal from "@/components/CsvImportModal";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";
import { useAuth } from "@/context/AuthContext";
import { Skeleton } from "@/components/ui/skeleton";
import useCustomFields from "@/hooks/useCustomFields";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { Compass, X, Pencil, Phone, MessageCircle, Contact, Download, Upload } from "lucide-react";

const waLink = (phone, text = "") => {
  const ph = String(phone || "").replace(/\D/g, "").slice(-10);
  return ph ? `https://wa.me/91${ph}?text=${encodeURIComponent(text)}` : null;
};

const emptyForm = {
  name: "", phone: "", email: "", address: "", gstin: "", division: "Furniture",
  gender: "", confidence_level: "", maps_url: "", lat: "", lng: "",
  alt_contact_name: "", alt_phone: "", team_id: "", custom_fields: {},
};

export default function Customers() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [fStage, setFStage] = usePersistedState("customers.stage", "All");
  const [jny, setJny] = useState(null);
  const [editing, setEditing] = useState(null);   // existing customer being edited, or null
  const [show, setShow] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [teams, setTeams] = useState([]);
  const { defs: customFieldDefs } = useCustomFields("customer");
  const [customFilters, setCustomFilters] = useState({});
  const [showImport, setShowImport] = useState(false);
  const { canDo } = useAuth();
  const canCreate = canDo("customers", "create");
  const canEdit = canDo("customers", "edit");
  const [loadError, setLoadError] = useState(null);

  const load = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const { data } = await api.get("/customers");
      setRows(data);
    } catch (e) {
      setLoadError(e?.response?.status === 401 || e?.response?.status === 403 ? "unauthorized" : "error");
    } finally { setLoading(false); }
  };
  const updateStage = async (c, stage) => {
    await api.put(`/customers/${c.id}`, { ...c, stage });
    setRows((p) => p.map((x) => x.id === c.id ? { ...x, stage } : x));
  };

  const exportCsv = async () => {
    const { data } = await api.get("/customers/export.csv", { skipCache: true, responseType: "blob" });
    const blob = new Blob([data], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `customers_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  useEffect(() => {
    load();
    api.get("/teams").then(({ data }) => setTeams(data)).catch(() => setTeams([]));
  }, []);

  const openNew = () => { setEditing(null); setForm(emptyForm); setShow(true); };
  const openEdit = (c) => { setEditing(c); setForm({ ...emptyForm, ...c, custom_fields: c.custom_fields || {} }); setShow(true); };

  const save = async () => {
    if (saving) return;
    if (!form.name.trim()) return toast.error("Name is required");
    if (!form.phone.trim()) return toast.error("Phone number is required");
    setSaving(true);
    const payload = { ...form,
      // StarRating hands back a number or null (never ""), so this must not
      // parseFloat(null) into a NaN the JSON encoder can't represent.
      confidence_level: form.confidence_level === "" || form.confidence_level == null
        ? null : parseFloat(form.confidence_level),
      lat: form.lat === "" ? null : parseFloat(form.lat),
      lng: form.lng === "" ? null : parseFloat(form.lng),
    };
    try {
      if (editing) await api.put(`/customers/${editing.id}`, payload);
      else await api.post("/customers", payload);
      toast.success(editing ? "Customer updated" : "Customer created");
      setShow(false);
      load();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (detail && typeof detail === "object" && detail.existing_id) {
        toast.error(detail.message, {
          action: { label: "Open existing", onClick: () => setJny({ phone: form.phone, name: detail.existing_name }) },
        });
      } else {
        toast.error(typeof detail === "string" ? detail : "Save failed — check the required fields");
      }
    } finally { setSaving(false); }
  };

  const stages = useMemo(() => ["All", ...new Set(rows.map((r) => r.stage).filter(Boolean))], [rows]);
  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return rows.filter((r) => {
      if (fStage !== "All" && r.stage !== fStage) return false;
      if (q && !(r.name || "").toLowerCase().includes(q) && !(r.phone || "").includes(q)) return false;
      for (const [key, val] of Object.entries(customFilters)) {
        if (!val) continue;
        if (String((r.custom_fields || {})[key] ?? "") !== String(val)) return false;
      }
      return true;
    });
  }, [rows, search, fStage, customFilters]);

  return (
    <>
      <Topbar
        title="Customers"
        subtitle={`${filtered.length} of ${rows.length}`}
        onAdd={canCreate ? openNew : undefined}
        addLabel="New Customer"
        actions={
          <>
            <button onClick={exportCsv} title="Export CSV" className="p-2 rounded-lg hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]" data-testid="customers-export"><Download size={16} /></button>
            <button onClick={() => setShowImport(true)} title="Import CSV" className="p-2 rounded-lg hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]" data-testid="customers-import-open"><Upload size={16} /></button>
          </>
        }
      />
      <div className="p-6" data-testid="customers-page">
        <div className="flex flex-wrap gap-2 mb-4">
          <input
            placeholder="Search name, phone…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-sm outline-none focus:border-[var(--color-primary)] w-72"
          />
          <select value={fStage} onChange={(e) => setFStage(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-sm">
            {stages.map((s) => <option key={s}>{s}</option>)}
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
            entity="customers"
            filters={{ search, fStage, customFilters }}
            onApply={(f) => { setSearch(f.search || ""); setFStage(f.fStage || "All"); setCustomFilters(f.customFilters || {}); }}
          />
        </div>

        {loadError ? (
          <ErrorState
            title={loadError === "unauthorized" ? "You don't have access to Customers" : "Couldn't load customers"}
            hint={loadError === "unauthorized" ? undefined : "The customer list didn't load — check your connection and try again."}
            onRetry={loadError === "unauthorized" ? undefined : load}
          />
        ) : (
        <div className="bg-[var(--color-surface)] border border-[var(--color-primary-soft)] rounded-[var(--radius-lg)] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--color-surface-muted)]">
                <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  <th className="px-4 py-3">Name</th>
                  <th className="hidden md:table-cell px-4 py-3">Phone</th>
                  <th className="px-4 py-3">Stage</th>
                  <th className="hidden lg:table-cell px-4 py-3">Customer since</th>
                  <th className="hidden md:table-cell px-4 py-3 text-right">Lifetime value</th>
                  <th className="hidden lg:table-cell px-4 py-3 text-right">Balance</th>
                  {customFieldDefs.filter((d) => d.show_table).map((d) => (
                    <th key={d.key} className="hidden lg:table-cell px-4 py-3 text-left">{d.label}</th>
                  ))}
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {loading && Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i} className="border-t border-[var(--color-border)]">
                    <td className="px-4 py-3"><Skeleton className="h-4 w-28" /></td>
                    <td className="hidden md:table-cell px-4 py-3"><Skeleton className="h-4 w-24" /></td>
                    <td className="px-4 py-3"><Skeleton className="h-6 w-20" /></td>
                    <td className="hidden lg:table-cell px-4 py-3"><Skeleton className="h-4 w-20" /></td>
                    <td className="hidden md:table-cell px-4 py-3"><Skeleton className="h-4 w-16 ml-auto" /></td>
                    <td className="hidden lg:table-cell px-4 py-3"><Skeleton className="h-4 w-16 ml-auto" /></td>
                    {customFieldDefs.filter((d) => d.show_table).map((d) => (
                      <td key={d.key} className="hidden lg:table-cell px-4 py-3"><Skeleton className="h-4 w-16" /></td>
                    ))}
                    <td className="px-4 py-3"><Skeleton className="h-6 w-20 ml-auto" /></td>
                  </tr>
                ))}
                {!loading && filtered.map((c) => (
                  <tr key={c.id} className="border-t border-[var(--color-border)] hover:bg-[var(--color-surface-muted)]" data-testid={`customer-${c.id}`}>
                    <td className="px-4 py-3 font-medium text-[var(--color-text)]">{c.name}</td>
                    <td className="hidden md:table-cell px-4 py-3 font-mono text-[var(--color-text-muted)]">{c.phone}</td>
                    <td className="px-4 py-3">
                      <select value={c.stage || ""} onChange={(e) => updateStage(c, e.target.value)} disabled={!canEdit} className="px-2 py-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-xs disabled:opacity-60 disabled:cursor-not-allowed" data-testid={`customer-stage-${c.id}`}>
                        {c.stage && !stages.includes(c.stage) && <option value={c.stage}>{c.stage}</option>}
                        {stages.filter((s) => s !== "All").map((s) => <option key={s}>{s}</option>)}
                      </select>
                    </td>
                    <td className="hidden lg:table-cell px-4 py-3 text-[var(--color-text-muted)]">{fmtDate(c.customer_since)}</td>
                    <td className="hidden md:table-cell px-4 py-3 text-right font-mono">{inrFull(c.lifetime_value)}</td>
                    <td className="hidden lg:table-cell px-4 py-3 text-right font-mono">{inrFull(c.balance)}</td>
                    {customFieldDefs.filter((d) => d.show_table).map((d) => (
                      <td key={d.key} className="hidden lg:table-cell px-4 py-3 text-[var(--color-text-muted)]">{String((c.custom_fields || {})[d.key] ?? "")}</td>
                    ))}
                    <td className="px-4 py-3 text-right flex items-center justify-end gap-1">
                      {c.phone && (
                        <a href={`tel:${c.phone}`} title="Call" className="p-1.5 rounded-md hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]" data-testid={`customer-call-${c.id}`}><Phone size={14} /></a>
                      )}
                      {waLink(c.phone) && (
                        <a href={waLink(c.phone)} target="_blank" rel="noreferrer" title="WhatsApp" className="p-1.5 rounded-md hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]" data-testid={`customer-wa-${c.id}`}><MessageCircle size={14} /></a>
                      )}
                      {canEdit && (
                        <button
                          onClick={() => openEdit(c)}
                          title="Edit customer"
                          className="p-1.5 rounded-md hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]"
                          data-testid={`customer-edit-${c.id}`}
                        >
                          <Pencil size={14} />
                        </button>
                      )}
                      <button
                        onClick={() => setJny({ phone: c.phone, name: c.name })}
                        title="Customer 360"
                        className="p-1.5 rounded-md hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]"
                        data-testid={`customer-journey-${c.id}`}
                      >
                        <Compass size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
                {!loading && filtered.length === 0 && (
                  <tr><td colSpan={7 + customFieldDefs.filter((d) => d.show_table).length}>
                    <EmptyState icon={Contact} title="No customers yet" hint="Customers created from a won lead or added manually will show up here." />
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
          <div className="bg-[var(--color-surface)] rounded-t-2xl sm:rounded-xl border border-[var(--color-border)] w-full max-w-2xl shadow-2xl max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">{editing ? "Edit Customer" : "New Customer"}</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--color-surface-muted)]"><X size={16} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-4">
              <CFld l="Customer Name *" v={form.name} oc={(v) => setForm({ ...form, name: v })} />
              <CFld l="Primary Phone *" v={form.phone} oc={(v) => setForm({ ...form, phone: v })} />
              <CFld l="Alternate Contact Name" v={form.alt_contact_name} oc={(v) => setForm({ ...form, alt_contact_name: v })} />
              <CFld l="Alternate Phone" v={form.alt_phone} oc={(v) => setForm({ ...form, alt_phone: v })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">Gender</label>
                <select value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm">
                  <option value="">— Not specified —</option>
                  <option value="Male">Male</option>
                  <option value="Female">Female</option>
                  <option value="Other">Other</option>
                </select>
              </div>
              <StarRating label="Confidence" testId="customer-confidence" value={form.confidence_level}
                onChange={(pct) => setForm({ ...form, confidence_level: pct })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">Team</label>
                <select value={form.team_id} onChange={(e) => setForm({ ...form, team_id: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm">
                  <option value="">— None —</option>
                  {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
              <CFld l="Address" v={form.address} oc={(v) => setForm({ ...form, address: v })} cls="col-span-2" />
              <CFld l="Google Maps Location URL" v={form.maps_url} oc={(v) => setForm({ ...form, maps_url: v })} cls="col-span-2" />
              <CFld l="Latitude" t="number" v={form.lat} oc={(v) => setForm({ ...form, lat: v })} />
              <CFld l="Longitude" t="number" v={form.lng} oc={(v) => setForm({ ...form, lng: v })} />
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
              <button className="btn-primary disabled:opacity-60" onClick={save} disabled={saving} data-testid="customer-save">{saving ? "Saving…" : editing ? "Save Changes" : "Create Customer"}</button>
            </div>
          </div>
        </div>
      )}

      <JourneyDrawer phone={jny?.phone} name={jny?.name} onClose={() => setJny(null)} />

      {showImport && (
        <CsvImportModal entity="customers" onClose={() => setShowImport(false)} onImported={load} />
      )}
    </>
  );
}

function CFld({ l, v, oc, t = "text", cls = "" }) {
  return (
    <div className={cls}>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">{l}</label>
      <input type={t} value={v ?? ""} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm outline-none focus:border-[var(--color-primary)]" />
    </div>
  );
}
