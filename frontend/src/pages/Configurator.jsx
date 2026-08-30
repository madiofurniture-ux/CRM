import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import api from "@/lib/api";
import { inrFull } from "@/lib/format";
import { ArrowRightCircle } from "lucide-react";
import { toast } from "sonner";

export default function Configurator() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const focus = params.get("config");
  const [rows, setRows] = useState([]);
  const [busyId, setBusyId] = useState(null);

  const load = async () => { const { data } = await api.get("/product-configs"); setRows(data); };
  useEffect(() => { load(); }, []);

  const toQuote = async (c) => {
    if (busyId) return;
    setBusyId(c.id);
    try {
      const { data } = await api.post(`/product-configs/${c.id}/to-quote`);
      toast.success(`Quote ${data.quote_no} created`);
      nav(`/quotes/ws/${data.id}`);
    } catch {
      toast.error("Could not create the quote");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <Topbar title="Configurator" subtitle={`${rows.length} configurations`} />
      <div className="p-6" data-testid="configurator-page">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {rows.map((c) => (
            <div
              key={c.id}
              className={`bg-[var(--surface)] border rounded-xl p-5 ${c.id === focus ? "border-[var(--brand)]" : "border-[var(--border)]"}`}
              data-testid={`config-${c.id}`}
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="font-heading font-semibold text-[var(--ink)]">{c.name || "Configuration"}</div>
                  <div className="text-xs text-[var(--ink-2)]">{c.division}</div>
                </div>
                <StageBadge stage={c.status} />
              </div>
              <div className="text-xs text-[var(--ink-3)] mb-1">{(c.line_items || []).length} line item(s)</div>
              <div className="font-heading font-bold text-lg text-[var(--ink)] mb-3">{inrFull(c.grand_total)}</div>
              <button
                onClick={() => toQuote(c)}
                disabled={busyId === c.id || c.status !== "Draft"}
                className="btn-primary w-full justify-center disabled:opacity-50"
                data-testid={`config-to-quote-${c.id}`}
              >
                <ArrowRightCircle size={14} /> {c.status === "Draft" ? "Convert to Quote" : c.status}
              </button>
            </div>
          ))}
          {rows.length === 0 && (
            <div className="col-span-full text-center py-12 text-[var(--ink-3)]">
              No configurations yet — start one from a Requirement.
            </div>
          )}
        </div>
      </div>
    </>
  );
}
