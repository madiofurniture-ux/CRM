import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import SearchSelect from "@/components/SearchSelect";
import api, { formatApiError } from "@/lib/api";

/** The project's Applicator (MAP) or Supplier (Furniture, D&W), picked from
 * the Vendors list by type; "+ New" adds one without leaving the form. */
export const partnerRole = (division) => (String(division || "").toUpperCase() === "MAP" ? "Applicator" : "Supplier");

export default function PartnerPicker({ division, value = "", onChange, testId = "partner-picker" }) {
  const role = partnerRole(division);
  const [vendors, setVendors] = useState([]);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  useEffect(() => { api.get("/vendors").then(({ data }) => setVendors(data || [])).catch(() => setVendors([])); }, []);

  const options = useMemo(() => {
    const wanted = role === "Applicator" ? ["Applicator"] : ["Supplier", "Manufacturer"];
    return vendors
      .filter((v) => v.active !== false && wanted.includes(v.vendor_type || "Supplier")
        && (!v.division || !division || v.division === division || v.id === value))
      .map((v) => ({ id: v.id, label: v.name || v.code, sub: [v.code, v.vendor_type, v.division].filter(Boolean).join(" · ") }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [vendors, role, division, value]);

  const add = async () => {
    if (!name.trim()) return;
    try {
      const { data } = await api.post("/vendors", { name: name.trim(), vendor_type: role, division: division || "" });
      setVendors((l) => [data, ...l]);
      onChange?.(data.id);
      setAdding(false); setName("");
      toast.success(`${role} ${data.code} added`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Couldn't add"); }
  };

  return (
    <div className="space-y-1.5">
      <div className="flex gap-2 items-center">
        <div className="flex-1 min-w-0">
          <SearchSelect options={options} value={value} onChange={(id) => onChange?.(id || "")}
            placeholder={`Pick the ${role.toLowerCase()}…`} emptyLabel={`No ${role.toLowerCase()} yet — add one`} testId={testId} />
        </div>
        <button type="button" onClick={() => setAdding((a) => !a)} className="text-xs font-medium text-[var(--brand)] inline-flex items-center gap-1 shrink-0" data-testid={`${testId}-new`}>
          <Plus size={13} /> New
        </button>
      </div>
      {adding && (
        <div className="flex gap-2">
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder={`${role} name`} className="flex-1 px-2.5 py-1.5 rounded-md border border-[var(--border)] text-sm" data-testid={`${testId}-new-name`} />
          <button type="button" onClick={add} className="text-xs font-medium text-[var(--brand)]" data-testid={`${testId}-new-save`}>Add</button>
        </div>
      )}
    </div>
  );
}
