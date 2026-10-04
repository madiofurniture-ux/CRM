import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import { useTenantConfig } from "@/context/TenantConfigContext";

export const VENDOR_TYPES = ["Supplier", "Applicator", "Manufacturer"];

/** Master Data → Vendors & Applicators: one list of outside partners, each
 * tagged by type (Applicators paint MAP projects; Suppliers / Manufacturers
 * supply the rest) and optionally a division. */
export default function VendorsManager() {
  const { divisions } = useTenantConfig();
  const [rows, setRows] = useState(null);
  const [fType, setFType] = useState("All");
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState({ name: "", vendor_type: "Applicator", division: "MAP", phone: "", contact_person: "" });
  const [busy, setBusy] = useState(false);

  const load = () => api.get("/vendors", { skipCache: true }).then(({ data }) => setRows(data || [])).catch(() => setRows([]));
  useEffect(() => { load(); }, []);

  const shown = useMemo(() => (rows || []).filter((v) =>
    (fType === "All" || (v.vendor_type || "Supplier") === fType) &&
    (!q || [v.name, v.code, v.phone, v.contact_person].some((x) => String(x || "").toLowerCase().includes(q.toLowerCase())))
  ).sort((a, b) => String(a.name || a.code).localeCompare(String(b.name || b.code))), [rows, fType, q]);

  const save = async (v, patch) => {
    try {
      const { data } = await api.put(`/vendors/${v.id}`, { ...v, ...patch });
      setRows((list) => list.map((x) => (x.id === v.id ? data : x)));
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Couldn't save"); }
  };
  const add = async () => {
    if (!adding.name.trim()) return toast.error("Name is required");
    setBusy(true);
    try {
      const { data } = await api.post("/vendors", { ...adding, name: adding.name.trim() });
      setRows((list) => [data, ...(list || [])]);
      setAdding((a) => ({ ...a, name: "", phone: "", contact_person: "" }));
      toast.success(`${data.vendor_type} ${data.code} added`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Couldn't add"); }
    finally { setBusy(false); }
  };

  const cell = "px-2 py-1.5 rounded-md border border-[var(--border)] bg-white text-sm";
  return (
    <section className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4 space-y-3" data-testid="vendors-manager">
      <div>
        <h3 className="font-heading font-semibold">Vendors &amp; Applicators</h3>
        <p className="text-xs text-[var(--ink-3)]">Applicators paint MAP projects; Suppliers and Manufacturers supply Furniture and Doors &amp; Windows. Projects pick from this list.</p>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 items-end">
        <input className={`${cell} col-span-2`} placeholder="Name *" value={adding.name} onChange={(e) => setAdding({ ...adding, name: e.target.value })} data-testid="vendor-new-name" />
        <select className={cell} value={adding.vendor_type} onChange={(e) => setAdding({ ...adding, vendor_type: e.target.value, division: e.target.value === "Applicator" ? "MAP" : adding.division })} data-testid="vendor-new-type">
          {VENDOR_TYPES.map((t) => <option key={t}>{t}</option>)}
        </select>
        <select className={cell} value={adding.division} onChange={(e) => setAdding({ ...adding, division: e.target.value })}>
          <option value="">Any division</option>
          {divisions.map((d) => <option key={d.id} value={d.slug}>{d.slug}</option>)}
        </select>
        <input className={cell} placeholder="Phone" value={adding.phone} onChange={(e) => setAdding({ ...adding, phone: e.target.value })} />
        <button className="btn-primary justify-center disabled:opacity-60" onClick={add} disabled={busy} data-testid="vendor-add">Add</button>
      </div>
      <div className="flex flex-wrap gap-2">
        <input className={`${cell} w-56`} placeholder="Search name, code, phone…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className={cell} value={fType} onChange={(e) => setFType(e.target.value)}>
          <option>All</option>
          {VENDOR_TYPES.map((t) => <option key={t}>{t}</option>)}
        </select>
        <span className="text-xs text-[var(--ink-3)] self-center">{shown.length} of {(rows || []).length}</span>
      </div>
      {rows === null ? <div className="text-sm text-[var(--ink-3)]">Loading…</div> : (
        <div className="max-h-96 overflow-y-auto divide-y divide-[var(--border-light)]">
          {shown.map((v) => (
            <div key={v.id} className="flex flex-wrap items-center gap-2 py-2" data-testid={`vendor-row-${v.id}`}>
              <span className="font-mono text-xs text-[var(--ink-3)] w-20">{v.code}</span>
              <span className="flex-1 min-w-[10rem] text-sm">{v.name || <span className="text-[var(--ink-3)]">(name hidden)</span>}</span>
              <select className={cell} value={v.vendor_type || "Supplier"} onChange={(e) => save(v, { vendor_type: e.target.value })} aria-label="Type">
                {VENDOR_TYPES.map((t) => <option key={t}>{t}</option>)}
              </select>
              <select className={cell} value={v.division || ""} onChange={(e) => save(v, { division: e.target.value })} aria-label="Division">
                <option value="">Any division</option>
                {divisions.map((d) => <option key={d.id} value={d.slug}>{d.slug}</option>)}
              </select>
              <span className="text-xs text-[var(--ink-3)] w-28 truncate">{v.phone}</span>
            </div>
          ))}
          {!shown.length && <div className="text-sm text-[var(--ink-3)] py-4 text-center">No vendors match.</div>}
        </div>
      )}
    </section>
  );
}
