import { useEffect, useMemo, useState } from "react";
import SearchSelect from "@/components/SearchSelect";
import api from "@/lib/api";

/** A supplier or manufacturer from the Vendors list, by name where this
 * person may see it (admin, accounts), else by vendor code. */
export default function VendorSelect({ value, onChange, testId = "vendor-select" }) {
  const [vendors, setVendors] = useState([]);
  useEffect(() => { api.get("/vendors").then(({ data }) => setVendors(data || [])).catch(() => setVendors([])); }, []);
  const options = useMemo(() => vendors
    .filter((v) => v.active !== false && (v.vendor_type || "Supplier") !== "Applicator")
    .map((v) => ({ id: v.id, label: v.name || v.code, sub: [v.code, v.vendor_type, v.division].filter(Boolean).join(" · ") }))
    .sort((a, b) => String(a.label).localeCompare(String(b.label))), [vendors]);
  return <SearchSelect options={options} value={value} onChange={(id) => onChange(id || "")} placeholder="Pick the vendor…"
                       emptyLabel="No vendors yet — add them in Master Data" testId={testId} />;
}
