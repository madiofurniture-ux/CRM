import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import JourneyDrawer from "@/components/JourneyDrawer";
import api from "@/lib/api";
import { toast } from "sonner";
import { MessageCircle, Compass } from "lucide-react";

// Alert groups, in the order the backend emits them.
const GROUPS = [
  { key: "overdue", title: "🔴 Overdue follow-ups" },
  { key: "today", title: "⚡ Due today" },
  { key: "week", title: "📅 This week" },
  { key: "money", title: "💰 Money & stock" },
  { key: "nodate", title: "🆕 No follow-up date" },
];
const SEV = {
  danger: "border-l-[var(--danger)]",
  warn: "border-l-[var(--warn)]",
  info: "border-l-[var(--brand)]",
};

export default function Alerts() {
  const [data, setData] = useState(null);
  const [jny, setJny] = useState(null);

  const load = () => api.get("/alerts").then((r) => setData(r.data));
  useEffect(() => { load(); }, []);

  const grouped = useMemo(() => {
    const g = {};
    (data?.alerts || []).forEach((a) => { (g[a.group] = g[a.group] || []).push(a); });
    return g;
  }, [data]);

  const wa = (a) => {
    const ph = String(a.phone || "").replace(/\D/g, "").slice(-10);
    if (!ph) { toast.error("No phone number for this contact"); return; }
    window.open(`https://wa.me/91${ph}?text=${encodeURIComponent(a.wa_text || "")}`, "_blank");
  };

  return (
    <>
      <Topbar title="Follow-Up Alerts" subtitle={`${data?.count || 0} items need attention`} />
      <div className="p-6 space-y-6" data-testid="alerts-page">
        {(data?.count || 0) === 0 && <div className="text-center py-16 text-[var(--ink-3)]">All clear — nothing needs chasing right now 🎉</div>}
        {GROUPS.map((g) => {
          const items = grouped[g.key] || [];
          if (!items.length) return null;
          return (
            <div key={g.key}>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] mb-2">{g.title} · {items.length}</div>
              <div className="space-y-2">
                {items.map((a, i) => (
                  <div key={i} className={`bg-[var(--surface)] border border-[var(--border)] border-l-4 ${SEV[a.severity] || SEV.info} rounded-lg px-4 py-3 flex items-center gap-3`}>
                    <span className="text-lg shrink-0">{a.icon}</span>
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-[var(--ink)] text-sm">{a.title}</div>
                      <div className="text-xs text-[var(--ink-3)]">{a.detail}</div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {a.phone && <button onClick={() => setJny({ phone: a.phone, name: a.name })} title="Journey" className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]"><Compass size={14} /></button>}
                      {a.wa_text && a.phone && <button onClick={() => wa(a)} title="WhatsApp" className="p-1.5 rounded-md hover:bg-[var(--moss-soft)] text-[var(--moss)]"><MessageCircle size={14} /></button>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <JourneyDrawer phone={jny?.phone} name={jny?.name} onClose={() => setJny(null)} />
    </>
  );
}
