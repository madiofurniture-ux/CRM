import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { inr, fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { GripVertical } from "lucide-react";

const STAGES = ["New", "Qualified", "Quoted", "Negotiation", "Won", "Lost"];
const STAGE_TINTS = {
  New: "border-t-[var(--ink-3)]",
  Qualified: "border-t-blue-500",
  Quoted: "border-t-[var(--warn)]",
  Negotiation: "border-t-[var(--brand)]",
  Won: "border-t-[var(--moss)]",
  Lost: "border-t-[var(--danger)]",
};

export default function Pipeline() {
  const [quotes, setQuotes] = useState([]);
  const [dragId, setDragId] = useState(null);

  const load = async () => {
    const { data } = await api.get("/quotes");
    setQuotes(data);
  };
  useEffect(() => { load(); }, []);

  const onDrop = async (stage) => {
    if (!dragId) return;
    const q = quotes.find((x) => x.id === dragId);
    if (!q || q.stage === stage) { setDragId(null); return; }
    setQuotes((prev) => prev.map((x) => (x.id === dragId ? { ...x, stage } : x)));
    setDragId(null);
    try {
      await api.put(`/quotes/${q.id}`, { ...q, stage });
      toast.success(`Moved to ${stage}`);
    } catch (e) {
      toast.error("Failed to update");
      load();
    }
  };

  return (
    <>
      <Topbar title="Pipeline" subtitle="Drag deals between stages" />
      <div className="p-6" data-testid="pipeline-page">
        <div className="flex gap-4 overflow-x-auto pb-4">
          {STAGES.map((s) => {
            const items = quotes.filter((q) => q.stage === s);
            const total = items.reduce((a, b) => a + (b.value || 0), 0);
            return (
              <div
                key={s}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => onDrop(s)}
                className="w-[300px] shrink-0 bg-[var(--surface-2)] rounded-xl p-3 min-h-[400px]"
                data-testid={`kanban-col-${s}`}
              >
                <div className="flex items-center justify-between px-1 mb-3">
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${
                      s === "New" ? "bg-[var(--ink-3)]" :
                      s === "Qualified" ? "bg-blue-500" :
                      s === "Quoted" ? "bg-[var(--warn)]" :
                      s === "Negotiation" ? "bg-[var(--brand)]" :
                      s === "Won" ? "bg-[var(--moss)]" : "bg-[var(--danger)]"
                    }`} />
                    <span className="font-heading font-semibold text-[var(--ink)] text-sm">{s}</span>
                    <span className="text-xs text-[var(--ink-3)] font-mono">{items.length}</span>
                  </div>
                  <span className="text-[11px] font-mono font-semibold text-[var(--ink-2)]">{inr(total)}</span>
                </div>
                <div className="space-y-2">
                  {items.map((q) => (
                    <div
                      key={q.id}
                      draggable
                      onDragStart={() => setDragId(q.id)}
                      onDragEnd={() => setDragId(null)}
                      className={`bg-[var(--surface)] border border-[var(--border)] border-t-2 ${STAGE_TINTS[s]} rounded-lg p-3 cursor-grab active:cursor-grabbing hover:shadow-md transition-shadow ${dragId === q.id ? "kanban-card-dragging" : ""}`}
                      data-testid={`kanban-card-${q.id}`}
                    >
                      <div className="flex items-start justify-between gap-2 mb-1.5">
                        <div className="font-semibold text-sm text-[var(--ink)] leading-tight">{q.customer}</div>
                        <GripVertical size={14} className="text-[var(--ink-3)] shrink-0" />
                      </div>
                      <div className="text-[11px] text-[var(--ink-3)] mb-2 truncate">{q.remarks}</div>
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">{q.division}</span>
                        <span className="font-mono text-xs font-semibold text-[var(--ink)]">{inr(q.value)}</span>
                      </div>
                      <div className="mt-2 pt-2 border-t border-[var(--border-light)] flex items-center justify-between text-[10px] text-[var(--ink-3)]">
                        <span className="font-mono">{q.quote_no}</span>
                        <span>{fmtDate(q.date)} · {q.by_user}</span>
                      </div>
                    </div>
                  ))}
                  {items.length === 0 && (
                    <div className="text-center text-[11px] text-[var(--ink-3)] py-6 border border-dashed border-[var(--border)] rounded-lg">
                      Drop deals here
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
