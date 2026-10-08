import { useEffect, useMemo, useState } from "react";
import SearchSelect from "@/components/SearchSelect";
import api from "@/lib/api";

/** Pick the architect / designer from the Architects list (stores id and
 * name). A name typed on an older record shows until someone picks one. */
export default function ArchitectPicker({ id = "", name = "", onChange, testId = "architect-picker" }) {
  const [rows, setRows] = useState([]);
  useEffect(() => { api.get("/architects").then(({ data }) => setRows(data || [])).catch(() => setRows([])); }, []);
  const options = useMemo(() => {
    const opts = rows.map((a) => ({ id: a.id, label: `${a.type === "Architect" ? "Ar. " : ""}${a.name}`,
                                    sub: [a.firm, a.type, a.phone].filter(Boolean).join(" · "), row: a }))
      .sort((a, b) => a.label.localeCompare(b.label));
    if (!id && name) opts.unshift({ id: `legacy:${name}`, label: name, sub: "typed — not in Architects" });
    return opts;
  }, [rows, id, name]);
  return (
    <SearchSelect options={options} value={id || (name ? `legacy:${name}` : "")} testId={testId}
      placeholder="Pick from Architects…" emptyLabel="Not in Architects — add them there first"
      onChange={(v, opt) => onChange?.(opt?.row ? { id: opt.row.id, name: opt.row.name, row: opt.row } : (v ? { id: "", name } : null))} />
  );
}
