import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Rocket, ArrowRight } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

/** Home-screen card for an admin whose company isn't fully set up yet:
 * progress and the next unfinished step from /setup/status. Disappears at
 * 100%. Business Setup is pages/Setup.jsx. */
export default function SetupNudge() {
  const { user, canAccess } = useAuth();
  const [st, setSt] = useState(null);
  const show = user?.role === "admin" && canAccess("setup");

  useEffect(() => {
    if (!show) return;
    api.get("/setup/status").then((r) => setSt(r.data)).catch(() => setSt(null));
  }, [show]);

  if (!show || !st || st.percent >= 100) return null;
  const next = st.steps.find((s) => !s.done);
  return (
    <div className="flex flex-wrap items-center gap-4 p-4 rounded-[var(--radius-lg)] border border-[var(--color-primary)]/30 bg-[var(--color-primary-soft)]" data-testid="setup-nudge">
      <span className="w-10 h-10 rounded-full bg-[var(--color-primary)] text-white flex items-center justify-center shrink-0"><Rocket size={18} /></span>
      <div className="flex-1 min-w-[12rem]">
        <div className="font-semibold text-sm">Finish setting up — {st.done} of {st.total} done</div>
        <div className="mt-1.5 h-1.5 rounded-full bg-white overflow-hidden max-w-xs">
          <div className="h-full bg-[var(--color-success)]" style={{ width: `${st.percent}%` }} />
        </div>
        {next && <div className="text-xs text-[var(--color-text-muted)] mt-1.5">Next: {next.label} — {next.hint}</div>}
      </div>
      <Link to={next?.to || "/admin/setup"} className="btn-primary">
        {next?.label || "Business Setup"} <ArrowRight size={14} />
      </Link>
    </div>
  );
}
