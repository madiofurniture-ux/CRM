import { useCallback, useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Delete } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { formatApiError } from "@/lib/api";
import { toast, Toaster } from "sonner";

const ROLE_CARDS = [
  { username: "admin", name: "Admin", icon: "AD", color: "#1A1D1A", subtitle: "Full access" },
  { username: "raghu", name: "Raghu MF", icon: "RM", color: "#C85A32", subtitle: "Sales" },
  { username: "nenmu", name: "Nenmu", icon: "NM", color: "#4A5D4E", subtitle: "Sales" },
  { username: "gowtham", name: "Gowtham Hive", icon: "GH", color: "#D48B30", subtitle: "Sales" },
];

export default function Login() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [selected, setSelected] = useState(null);
  const [pin, setPin] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (user) nav("/", { replace: true });
  }, [user, nav]);

  const submit = useCallback(async (role, pinValue) => {
    setSubmitting(true);
    setError("");
    try {
      await login(role.username, pinValue);
      toast.success(`Welcome back, ${role.name}`);
      nav(loc.state?.from || "/", { replace: true });
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || "Login failed");
      setPin("");
    } finally {
      setSubmitting(false);
    }
  }, [login, nav, loc.state]);

  const press = (k) => {
    if (submitting || !selected) return;
    setError("");
    if (k === "del") {
      setPin((p) => p.slice(0, -1));
    } else if (pin.length < 4) {
      const next = pin + k;
      setPin(next);
      if (next.length === 4) submit(selected, next);
    }
  };

  return (
    <div className="min-h-screen flex bg-[var(--bg)] relative overflow-hidden">
      <Toaster position="top-right" />

      {/* Left: hero */}
      <div className="hidden lg:flex w-1/2 relative items-end p-12">
        <img
          src="/login-hero.jpg"
          alt=""
          className="absolute inset-0 w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent" />
        <div className="relative z-10 text-white max-w-md">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-11 h-11 rounded-xl bg-[var(--brand)] flex items-center justify-center font-heading font-bold text-lg">M</div>
            <div>
              <div className="font-heading text-xl font-bold tracking-tight">MADIO CRM</div>
              <div className="text-[11px] uppercase tracking-[0.2em] text-white/70">Furniture · Paints · D&W</div>
            </div>
          </div>
          <h2 className="font-heading text-4xl font-bold leading-tight mb-3">
            Every visitor.<br />Every quote.<br />Every deal — captured.
          </h2>
          <p className="text-white/80 text-sm leading-relaxed">
            Built for showrooms that move fast. Track walk-ins, manage pipelines,
            quote on the floor, and watch your inventory in real time.
          </p>
        </div>
      </div>

      {/* Right: login */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12 relative">
        <div className="madio-blob w-72 h-72 bg-[var(--brand-soft)] top-10 right-10" />
        <div className="madio-blob w-64 h-64 bg-[var(--moss-soft)] bottom-20 left-10" />

        <div className="w-full max-w-md relative z-10">
          <div className="lg:hidden mb-8 flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[var(--brand)] flex items-center justify-center text-white font-heading font-bold">M</div>
            <div className="font-heading text-lg font-bold">MADIO CRM</div>
          </div>

          {!selected ? (
            <div className="fadeup">
              <h1 className="font-heading text-3xl font-bold tracking-tight text-[var(--ink)] mb-1">Welcome back</h1>
              <p className="text-[var(--ink-2)] text-sm mb-8">Select your profile to continue</p>
              <div className="grid grid-cols-2 gap-3">
                {ROLE_CARDS.map((r) => (
                  <button
                    key={r.username}
                    onClick={() => { setSelected(r); setPin(""); setError(""); }}
                    className="text-left p-4 rounded-xl bg-[var(--surface)] border border-[var(--border)] hover:border-[var(--brand)] hover:-translate-y-0.5 transition-all duration-150 group"
                    data-testid={`role-${r.username}`}
                  >
                    <div
                      className="w-10 h-10 rounded-lg flex items-center justify-center text-white font-heading font-bold text-sm mb-3"
                      style={{ background: r.color }}
                    >
                      {r.icon}
                    </div>
                    <div className="font-heading font-semibold text-[var(--ink)] text-[15px] leading-tight">{r.name}</div>
                    <div className="text-[11px] text-[var(--ink-3)] uppercase tracking-wider mt-0.5">{r.subtitle}</div>
                  </button>
                ))}
              </div>
              <div className="mt-8 text-xs text-[var(--ink-3)] text-center">
                Admin PIN <span className="font-mono">1234</span> · Sales PINs <span className="font-mono">2222 · 3333 · 4444</span>
              </div>
            </div>
          ) : (
            <div className="fadeup">
              <button
                onClick={() => { setSelected(null); setPin(""); setError(""); }}
                className="text-xs text-[var(--ink-3)] hover:text-[var(--ink)] mb-6"
                data-testid="back-to-roles"
              >
                ← Switch profile
              </button>
              <div className="flex items-center gap-3 mb-6">
                <div
                  className="w-12 h-12 rounded-xl flex items-center justify-center text-white font-heading font-bold"
                  style={{ background: selected.color }}
                >
                  {selected.icon}
                </div>
                <div>
                  <div className="font-heading text-xl font-bold text-[var(--ink)] tracking-tight">{selected.name}</div>
                  <div className="text-xs text-[var(--ink-3)]">{selected.subtitle}</div>
                </div>
              </div>

              <div className="mb-2 text-xs uppercase tracking-[0.16em] text-[var(--ink-3)] font-semibold">Enter 4-digit PIN</div>
              <div className="flex gap-3 mb-6" data-testid="pin-dots">
                {[0, 1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className={`flex-1 h-14 rounded-lg border-2 flex items-center justify-center font-heading font-bold text-2xl ${
                      pin.length > i
                        ? "border-[var(--brand)] bg-[var(--brand-soft)] text-[var(--brand)] pin-dot-active"
                        : "border-[var(--border)] bg-[var(--surface)] text-[var(--ink-3)]"
                    }`}
                  >
                    {pin.length > i ? "●" : ""}
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-3 gap-3">
                {["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "del"].map((k, idx) => (
                  <button
                    key={idx}
                    onClick={() => k && press(k)}
                    disabled={!k || submitting}
                    className={`h-14 rounded-lg font-heading font-semibold text-xl transition-all ${
                      k === ""
                        ? "invisible"
                        : k === "del"
                        ? "bg-[var(--surface-2)] hover:bg-[var(--surface-hover)] text-[var(--ink-2)] border border-[var(--border)] flex items-center justify-center"
                        : "bg-[var(--surface)] hover:bg-[var(--surface-hover)] text-[var(--ink)] border border-[var(--border)] hover:border-[var(--brand)] active:scale-95"
                    }`}
                    data-testid={`pin-key-${k || "spacer"}`}
                  >
                    {k === "del" ? <Delete size={18} /> : k}
                  </button>
                ))}
              </div>

              {error && (
                <div className="mt-6 p-3 rounded-lg bg-[var(--danger-soft)] border border-[var(--danger)]/20 text-[var(--danger)] text-sm" data-testid="login-error">
                  {error}
                </div>
              )}
              {submitting && (
                <div className="mt-4 text-center text-sm text-[var(--ink-3)]">Signing in…</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
