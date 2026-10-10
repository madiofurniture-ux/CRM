import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Search, UserPlus } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { fmtDate, todayIST } from "@/lib/format";

const field = "w-full px-2.5 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-sm";

/** Who the products are for: a lead (by name, phone or LD- number) or a
 * walk-in visitor; or a new walk-in, added to Visitors there and then.
 * onPick({kind: "lead" | "visitor", id, name, phone, lead_id, customer_id}). */
export default function ClientPicker({ onPick }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState(null);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", phone: "" });

  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      api.get(`/shortlist/clients?q=${encodeURIComponent(q.trim())}`, { skipCache: true })
        .then(({ data }) => live && setRows(data || []))
        .catch(() => live && setRows([]));
    }, q ? 250 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [q]);

  const addWalkIn = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { toast.error("Give the visitor's name"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/visitors", {
        date: todayIST(), name: form.name.trim(), phone: form.phone.trim(), stage: "New",
        requirement: "Showroom visit — products shortlisted from the catalogue",
      });
      toast.success(`${data.name} added to today's visitors`);
      onPick({ kind: "visitor", id: data.id, name: data.name, phone: data.phone || "", lead_id: "", customer_id: data.customer_id || "" });
    } catch (err) {
      toast.error(formatApiError(err?.response?.data?.detail) || "Couldn't add the visitor");
    } finally { setBusy(false); }
  };

  if (adding) {
    return (
      <form onSubmit={addWalkIn} className="space-y-3" data-testid="client-new-walkin">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <label className="text-sm space-y-1"><span className="font-medium">Visitor's name</span>
            <input className={field} value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} autoFocus
                   data-testid="client-walkin-name" /></label>
          <label className="text-sm space-y-1"><span className="font-medium">Mobile <span className="font-normal text-[var(--color-text-muted)]">(for WhatsApp)</span></span>
            <input className={field} value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} inputMode="tel"
                   placeholder="98765 43210" data-testid="client-walkin-phone" /></label>
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className="lx-btn" onClick={() => setAdding(false)}>Back</button>
          <button type="submit" className="lx-btn lx-btn-brand inline-flex items-center gap-1" disabled={busy} data-testid="client-walkin-save">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <UserPlus size={14} />} Add walk-in</button>
        </div>
      </form>
    );
  }
  return (
    <div className="space-y-2" data-testid="client-picker">
      <div className="relative">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
        <input className={`${field} pl-8`} value={q} onChange={(e) => setQ(e.target.value)} autoFocus
               placeholder="Lead or visitor: name, phone or LD- number" data-testid="client-search" />
      </div>
      <div className="max-h-72 overflow-y-auto rounded-lg border border-[var(--color-border)] divide-y divide-[var(--color-border)]">
        {rows === null ? <div className="p-3 text-sm text-[var(--color-text-muted)]">Loading…</div>
          : !rows.length ? <div className="p-3 text-sm text-[var(--color-text-muted)]">{q ? "No lead or visitor matches." : "No open leads or recent walk-ins."}</div>
            : rows.map((c) => (
              <button key={`${c.kind}-${c.id}`} type="button" onClick={() => onPick(c)}
                      className="w-full text-left px-3 py-2 hover:bg-[var(--color-surface-muted)] flex items-center gap-2" data-testid={`client-${c.kind}-${c.id}`}>
                <span className={`shrink-0 text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded ${c.kind === "lead" ? "bg-[var(--color-primary-soft,#dbeafe)] text-[var(--color-primary)]" : "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]"}`}>
                  {c.kind === "lead" ? "Lead" : "Walk-in"}</span>
                <span className="min-w-0 flex-1">
                  <span className="block font-medium truncate">{c.name}{c.lead_id ? <span className="font-mono text-xs text-[var(--color-text-muted)]"> · {c.lead_id}</span> : null}</span>
                  <span className="block text-xs text-[var(--color-text-muted)] truncate">
                    {[c.phone, c.stage, c.date && fmtDate(c.date), c.shortlist ? `${c.shortlist} shortlisted` : ""].filter(Boolean).join(" · ")}</span>
                </span>
              </button>
            ))}
      </div>
      <button type="button" className="text-sm text-[var(--color-primary)] inline-flex items-center gap-1" onClick={() => setAdding(true)}
              data-testid="client-add-walkin"><UserPlus size={14} /> New walk-in visitor</button>
    </div>
  );
}

/** "Ravi Kumar · LD-2610-001" */
export const clientLabel = (c) => (c ? `${c.name}${c.lead_id ? ` · ${c.lead_id}` : c.kind === "visitor" ? " (walk-in)" : ""}` : "");
