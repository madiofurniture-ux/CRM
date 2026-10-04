import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, Building2, ExternalLink, FolderKanban, Plus, Search, UserPlus, X } from "lucide-react";
import api from "@/lib/api";
import { validateIndianPhone } from "@/lib/phone";

/**
 * Pick who a record is for: a customer and (optionally) one of their
 * projects. Used by every form that used to take a typed name + phone.
 *
 *   <CustomerProjectPicker customerId={f.customer_id} projectId={f.project_id}
 *       onChange={({ customer, project }) => …} />
 *
 * - Search finds customers (name, phone, code, email, company) and projects
 *   (name, number, site); picking a project also picks its customer.
 * - Once a customer is picked, their projects are a dropdown (the cascade).
 * - "+ New customer" / "+ New project" open a small inline form, so the
 *   record being written is never lost. A customer with the same phone or
 *   email is shown as a warning with "Use this one" — never a hard block.
 * - onChange gets the full customer / project objects so the form can fill
 *   name, phone, site address etc. without another lookup.
 */
export default function CustomerProjectPicker({
  customerId = "", projectId = "", onChange, withProject = true, allowNewProject = true,
  division = "Furniture", disabled = false, required = false, testid = "cpp", compact = false,
}) {
  const [customer, setCustomer] = useState(null);
  const [missing, setMissing] = useState(false);
  const [projects, setProjects] = useState([]);
  const [q, setQ] = useState("");
  const [results, setResults] = useState({ customers: [], projects: [] });
  const [searching, setSearching] = useState(false);
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(null); // "customer" | "project" | null
  const timer = useRef(null);
  const rootRef = useRef(null);

  // Load the linked customer (editing an existing record).
  useEffect(() => {
    let live = true;
    if (!customerId) { setCustomer(null); setMissing(false); return undefined; }
    if (customer?.id === customerId) return undefined;
    api.get(`/customers/search?q=${encodeURIComponent(customerId)}`)
      .then(({ data }) => {
        if (!live) return;
        const c = (data || []).find((x) => x.id === customerId);
        setCustomer(c || null);
        setMissing(!c);
      })
      .catch(() => live && setMissing(true));
    return () => { live = false; };
  }, [customerId]); // eslint-disable-line react-hooks/exhaustive-deps

  // The customer's projects (the cascade).
  useEffect(() => {
    let live = true;
    if (!withProject || !customerId) { setProjects([]); return undefined; }
    api.get(`/projects/search?customer_id=${encodeURIComponent(customerId)}`)
      .then(({ data }) => live && setProjects(data || []))
      .catch(() => live && setProjects([]));
    return () => { live = false; };
  }, [customerId, withProject]);

  useEffect(() => {
    const onDoc = (e) => { if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const search = (v) => {
    setQ(v);
    clearTimeout(timer.current);
    if (!v.trim()) { setResults({ customers: [], projects: [] }); setOpen(false); return; }
    timer.current = setTimeout(async () => {
      setSearching(true);
      const term = encodeURIComponent(v.trim());
      const [c, p] = await Promise.all([
        api.get(`/customers/search?q=${term}`).then((r) => r.data || []).catch(() => []),
        withProject ? api.get(`/projects/search?q=${term}`).then((r) => r.data || []).catch(() => []) : [],
      ]);
      setResults({ customers: c, projects: p.slice(0, 8) });
      setSearching(false);
      setOpen(true);
    }, 250);
  };

  const pickCustomer = (c, project = null) => {
    setCustomer(c);
    setMissing(false);
    setQ("");
    setOpen(false);
    setAdding(null);
    onChange?.({ customer: c, project });
  };

  const pickProject = async (p) => {
    if (!p) { onChange?.({ customer, project: null }); return; }
    if (p.customer_id && p.customer_id !== customer?.id) {
      const { data } = await api.get(`/customers/search?q=${encodeURIComponent(p.customer_id)}`).catch(() => ({ data: [] }));
      const c = (data || []).find((x) => x.id === p.customer_id);
      if (c) { pickCustomer(c, p); return; }
      toast.error("This project isn't linked to a customer yet — pick the customer first.");
      return;
    }
    setOpen(false);
    onChange?.({ customer, project: p });
  };

  const clear = () => { setCustomer(null); setMissing(false); setProjects([]); onChange?.({ customer: null, project: null }); };

  const box = "rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]";
  const selectedProject = projects.find((p) => p.id === projectId) || null;

  return (
    <div className="space-y-2" ref={rootRef} data-testid={testid}>
      {customer ? (
        <div className={`${box} px-3 py-2 flex items-start justify-between gap-2`} data-testid={`${testid}-selected`}>
          <div className="min-w-0">
            <div className="text-sm font-medium text-[var(--color-text)] truncate">
              {customer.name}
              {customer.code && <span className="ml-2 text-[11px] font-mono px-1.5 py-0.5 rounded bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]">{customer.code}</span>}
              {customer.stage && <span className="ml-1.5 text-[11px] text-[var(--color-text-muted)]">{customer.stage}</span>}
            </div>
            <div className="text-xs text-[var(--color-text-muted)] truncate">
              {[customer.phone, customer.email, customer.company].filter(Boolean).join(" · ")}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Link to={`/customers/${customer.id}`} target="_blank" className="text-xs text-[var(--color-primary)] inline-flex items-center gap-0.5" title="Open the customer in a new tab">
              View <ExternalLink size={11} />
            </Link>
            {!disabled && (
              <button type="button" onClick={clear} className="text-[var(--color-text-muted)] hover:text-[var(--color-text)]" aria-label="Change customer" data-testid={`${testid}-clear`}>
                <X size={14} />
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="relative">
          {missing && customerId && (
            <div className="mb-1.5 text-xs text-[var(--color-warning)] flex items-center gap-1">
              <AlertTriangle size={12} /> The linked customer no longer exists — pick another.
            </div>
          )}
          <div className={`${box} flex items-center gap-2 px-3 py-2`}>
            <Search size={14} className="text-[var(--color-text-muted)]" />
            <input
              value={q} disabled={disabled}
              onChange={(e) => search(e.target.value)}
              onFocus={() => (results.customers.length || results.projects.length) && setOpen(true)}
              placeholder={withProject ? "Customer or project — name, phone, code, site…" : "Customer — name, phone, code, email…"}
              className="flex-1 bg-transparent outline-none text-sm min-w-0"
              aria-label="Search customer"
              aria-required={required}
              data-testid={`${testid}-search`}
            />
            {!disabled && (
              <button type="button" onClick={() => setAdding("customer")} className="text-xs font-medium text-[var(--color-primary)] inline-flex items-center gap-1 shrink-0" data-testid={`${testid}-new-customer`}>
                <UserPlus size={13} /> New
              </button>
            )}
          </div>
          {open && (
            <div className="absolute z-30 mt-1 w-full max-h-72 overflow-y-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] shadow-lg" data-testid={`${testid}-results`}>
              {searching && <div className="p-3 text-xs text-[var(--color-text-muted)]">Searching…</div>}
              {!searching && !results.customers.length && !results.projects.length && (
                <div className="p-3 text-xs text-[var(--color-text-muted)]">No customer or project matches “{q}”.</div>
              )}
              {results.customers.length > 0 && <div className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">Customers</div>}
              {results.customers.map((c) => (
                <button key={c.id} type="button" onClick={() => pickCustomer(c)}
                        className="w-full text-left px-3 py-2 hover:bg-[var(--color-surface-muted)] flex items-center justify-between gap-2"
                        data-testid={`${testid}-customer-${c.id}`}>
                  <span className="min-w-0">
                    <span className="block text-sm truncate">{c.name} {c.code && <span className="text-[11px] font-mono text-[var(--color-text-muted)]">{c.code}</span>}</span>
                    <span className="block text-xs text-[var(--color-text-muted)] truncate">{[c.phone, c.company, c.email].filter(Boolean).join(" · ")}</span>
                  </span>
                  <span className="text-[10px] text-[var(--color-text-muted)] text-right shrink-0">{c.project_count || 0} projects<br />{c.quote_count || 0} quotes</span>
                </button>
              ))}
              {results.projects.length > 0 && <div className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">Projects</div>}
              {results.projects.map((p) => (
                <button key={p.id} type="button" onClick={() => pickProject(p)}
                        className="w-full text-left px-3 py-2 hover:bg-[var(--color-surface-muted)]"
                        data-testid={`${testid}-project-${p.id}`}>
                  <span className="block text-sm truncate"><FolderKanban size={12} className="inline mr-1 -mt-0.5" />{p.project_name || p.project_no} <span className="text-[11px] font-mono text-[var(--color-text-muted)]">{p.project_no}</span></span>
                  <span className="block text-xs text-[var(--color-text-muted)] truncate">{[p.customer, p.site_address, p.stage].filter(Boolean).join(" · ")}</span>
                </button>
              ))}
              <button type="button" onClick={() => { setAdding("customer"); setOpen(false); }}
                      className="w-full text-left px-3 py-2 text-xs font-medium text-[var(--color-primary)] border-t border-[var(--color-border)] inline-flex items-center gap-1">
                <UserPlus size={12} /> None of these — add a new customer
              </button>
            </div>
          )}
        </div>
      )}

      {adding === "customer" && !customer && (
        <NewCustomerForm initial={q} division={division} testid={`${testid}-nc`}
                         onCancel={() => setAdding(null)} onPicked={(c) => pickCustomer(c)} />
      )}

      {withProject && customer && (
        <div className="flex items-center gap-2">
          <Building2 size={14} className="text-[var(--color-text-muted)] shrink-0" />
          <select
            value={projectId || ""} disabled={disabled}
            onChange={(e) => pickProject(projects.find((p) => p.id === e.target.value) || null)}
            className={`${box} flex-1 px-2 py-2 text-sm min-w-0`}
            aria-label="Project"
            data-testid={`${testid}-project`}
          >
            <option value="">{projects.length ? "No particular project" : "No projects yet"}</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{[p.project_name || "Project", p.project_no, p.site_address].filter(Boolean).join(" · ")}</option>
            ))}
            {projectId && !selectedProject && <option value={projectId}>Linked project</option>}
          </select>
          {allowNewProject && !disabled && (
            <button type="button" onClick={() => setAdding(adding === "project" ? null : "project")}
                    className="text-xs font-medium text-[var(--color-primary)] inline-flex items-center gap-1 shrink-0" data-testid={`${testid}-new-project`}>
              <Plus size={13} /> {compact ? "" : "New project"}
            </button>
          )}
          {selectedProject && (
            <Link to={`/projects/${selectedProject.id}`} target="_blank" className="text-xs text-[var(--color-primary)] shrink-0" title="Open the project in a new tab">
              <ExternalLink size={12} />
            </Link>
          )}
        </div>
      )}

      {adding === "project" && customer && (
        <NewProjectForm customer={customer} division={division} testid={`${testid}-np`}
                        onCancel={() => setAdding(null)}
                        onCreated={(p) => { setProjects((list) => [p, ...list]); setAdding(null); onChange?.({ customer, project: p }); }} />
      )}
    </div>
  );
}


function NewCustomerForm({ initial = "", division, onCancel, onPicked, testid }) {
  const looksLikePhone = /^[+\d\s-]{6,}$/.test(initial.trim());
  const [f, setF] = useState({ name: looksLikePhone ? "" : initial.trim(), phone: looksLikePhone ? initial.trim() : "", email: "", company: "" });
  const [dupes, setDupes] = useState([]);
  const [saving, setSaving] = useState(false);
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));

  // Warn (don't block) when someone with this phone / email / name exists.
  useEffect(() => {
    const t = setTimeout(() => {
      const ph = validateIndianPhone(f.phone);
      if (!(ph.valid && ph.normalized) && !f.email.includes("@") && f.name.trim().length < 3) { setDupes([]); return; }
      const qs = new URLSearchParams({ phone: ph.normalized || "", email: f.email.trim(), name: f.name.trim() }).toString();
      api.get(`/customers/duplicates?${qs}`, { skipCache: true }).then(({ data }) => setDupes(data || [])).catch(() => setDupes([]));
    }, 350);
    return () => clearTimeout(t);
  }, [f.phone, f.email, f.name]);

  const save = async () => {
    const ph = validateIndianPhone(f.phone);
    if (!f.name.trim()) return toast.error("Customer name is required");
    if (!ph.valid || !ph.normalized) return toast.error(ph.message || "A 10-digit mobile number is required");
    setSaving(true);
    try {
      const { data } = await api.post("/customers", { ...f, name: f.name.trim(), phone: ph.normalized, division, stage: "Prospect" });
      toast.success(`Customer ${data.code || ""} added`);
      onPicked(data);
    } catch (e) {
      const d = e.response?.data?.detail;
      if (d?.existing_id) {
        toast.error(`${d.existing_name || "A customer"} already has this number — picked them instead.`);
        const { data } = await api.get(`/customers/search?q=${encodeURIComponent(d.existing_id)}`);
        const c = (data || []).find((x) => x.id === d.existing_id);
        if (c) onPicked(c);
      } else {
        toast.error(typeof d === "string" ? d : (d?.message || "Couldn't add the customer"));
      }
    } finally { setSaving(false); }
  };

  const input = "w-full px-2.5 py-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-sm outline-none focus:border-[var(--color-primary)]";
  return (
    <div className="rounded-lg border border-dashed border-[var(--color-primary)] p-3 space-y-2 bg-[var(--color-surface)]" data-testid={testid}>
      <div className="text-xs font-semibold text-[var(--color-text)]">New customer</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <input className={input} placeholder="Name *" value={f.name} onChange={set("name")} aria-label="Customer name" data-testid={`${testid}-name`} />
        <input className={input} placeholder="Mobile *" inputMode="tel" value={f.phone} onChange={set("phone")} aria-label="Customer mobile" data-testid={`${testid}-phone`} />
        <input className={input} placeholder="Email" type="email" value={f.email} onChange={set("email")} aria-label="Customer email" />
        <input className={input} placeholder="Company" value={f.company} onChange={set("company")} aria-label="Company" />
      </div>
      {dupes.length > 0 && (
        <div className="rounded-md border border-[var(--color-warning)] p-2 space-y-1" data-testid={`${testid}-dupes`}>
          <div className="text-xs text-[var(--color-warning)] flex items-center gap-1"><AlertTriangle size={12} /> Possibly already a customer:</div>
          {dupes.slice(0, 4).map((d) => (
            <div key={d.id} className="flex items-center justify-between gap-2 text-xs">
              <span className="truncate">{d.name} {d.code && <span className="font-mono text-[var(--color-text-muted)]">{d.code}</span>} · {d.phone} <span className="text-[var(--color-text-muted)]">({d.match.join(", ")})</span></span>
              <button type="button" onClick={() => onPicked(d)} className="font-medium text-[var(--color-primary)] shrink-0" data-testid={`${testid}-use-${d.id}`}>Use this one</button>
            </div>
          ))}
        </div>
      )}
      <div className="flex justify-end gap-3 text-xs">
        <button type="button" onClick={onCancel} className="text-[var(--color-text-muted)]">Cancel</button>
        <button type="button" onClick={save} disabled={saving} className="font-medium text-[var(--color-primary)] disabled:opacity-50" data-testid={`${testid}-save`}>
          {saving ? "Adding…" : "Add customer"}
        </button>
      </div>
    </div>
  );
}


export function NewProjectForm({ customer, division, onCancel, onCreated, testid }) {
  const [f, setF] = useState({ project_name: "", site_address: customer.address || "" });
  const [saving, setSaving] = useState(false);
  const save = async () => {
    if (!f.project_name.trim()) return toast.error("Give the project a name (e.g. Villa 12, Office fit-out)");
    setSaving(true);
    try {
      const { data } = await api.post("/projects", {
        project_no: "", customer: customer.name, phone: customer.phone || "", customer_id: customer.id,
        project_name: f.project_name.trim(), site_address: f.site_address.trim(), division,
      });
      toast.success(`Project ${data.project_no} added`);
      onCreated(data);
    } catch (e) {
      const d = e.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Couldn't add the project");
    } finally { setSaving(false); }
  };
  const input = "w-full px-2.5 py-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-sm outline-none focus:border-[var(--color-primary)]";
  return (
    <div className="rounded-lg border border-dashed border-[var(--color-primary)] p-3 space-y-2 bg-[var(--color-surface)]" data-testid={testid}>
      <div className="text-xs font-semibold">New project for {customer.name}</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <input className={input} placeholder="Project name *" value={f.project_name} onChange={(e) => setF({ ...f, project_name: e.target.value })} aria-label="Project name" data-testid={`${testid}-name`} />
        <input className={input} placeholder="Site address" value={f.site_address} onChange={(e) => setF({ ...f, site_address: e.target.value })} aria-label="Site address" />
      </div>
      <div className="flex justify-end gap-3 text-xs">
        <button type="button" onClick={onCancel} className="text-[var(--color-text-muted)]">Cancel</button>
        <button type="button" onClick={save} disabled={saving} className="font-medium text-[var(--color-primary)] disabled:opacity-50" data-testid={`${testid}-save`}>
          {saving ? "Adding…" : "Add project"}
        </button>
      </div>
    </div>
  );
}
