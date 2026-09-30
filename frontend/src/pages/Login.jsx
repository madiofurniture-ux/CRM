import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Delete } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import api, { formatApiError } from "@/lib/api";
import { toast, Toaster } from "sonner";

// Login runs before auth, so it can't know which tenant to brand for yet
// (tenant-specific branding shows post-login, in Sidebar). This is a
// deployment-wide product name, overridable per install without a code change.
const PRODUCT_NAME = process.env.REACT_APP_PRODUCT_NAME || "CRM";

export default function Login() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [selected, setSelected] = useState(null);
  const [pin, setPin] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // Profiles come from the server. They used to be a hardcoded list, which meant
  // renaming a role left real people unable to sign in at all.
  const [cards, setCards] = useState([]);
  const [loadingCards, setLoadingCards] = useState(true);
  const [typedUser, setTypedUser] = useState("");

  useEffect(() => {
    if (user) nav("/", { replace: true });
  }, [user, nav]);

  useEffect(() => {
    let alive = true;
    api.get("/auth/roles")
      .then(({ data }) => { if (alive) setCards(Array.isArray(data) ? data : []); })
      .catch(() => { if (alive) setCards([]); })
      .finally(() => { if (alive) setLoadingCards(false); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (selected && pin.length === 4) {
      doLogin();
    }
    // eslint-disable-next-line
  }, [pin]);

  const doLogin = async () => {
    if (!selected) return;
    setSubmitting(true);
    setError("");
    try {
      await login(selected.username, pin);
      toast.success(`Welcome back, ${selected.name}`);
      nav(loc.state?.from || "/", { replace: true });
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || "Login failed");
      setPin("");
    } finally {
      setSubmitting(false);
    }
  };

  const press = (k) => {
    if (submitting) return;
    setError("");
    if (k === "del") setPin((p) => p.slice(0, -1));
    else if (pin.length < 4) setPin((p) => p + k);
  };

  // The PIN pad is on-screen buttons, not a text input, so a physical keyboard
  // did nothing unless a button happened to have mouse focus. Digits and
  // Backspace/Delete now drive the same press() a click would.
  useEffect(() => {
    if (!selected) return;
    const onKey = (e) => {
      if (e.key >= "0" && e.key <= "9") press(e.key);
      else if (e.key === "Backspace" || e.key === "Delete") press("del");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line
  }, [selected, submitting, pin]);

  return (
    <div className="min-h-screen flex bg-[var(--bg)] relative overflow-hidden">
      <Toaster position="top-right" />

      {/* Left: hero */}
      <div className="hidden lg:flex w-1/2 relative items-end p-12">
        <img
          src="https://images.unsplash.com/photo-1682184805271-11671b7ecf4c?crop=entropy&cs=srgb&fm=jpg&q=85&w=1400"
          alt=""
          className="absolute inset-0 w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent" />
        <div className="relative z-10 text-white max-w-md">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-11 h-11 rounded-xl bg-[var(--brand)] flex items-center justify-center font-heading font-bold text-lg">M</div>
            <div>
              <div className="font-heading text-xl font-bold tracking-tight">{PRODUCT_NAME}</div>
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
        <div className="brand-blob w-72 h-72 bg-[var(--brand-soft)] top-10 right-10" />
        <div className="brand-blob w-64 h-64 bg-[var(--moss-soft)] bottom-20 left-10" />

        <div className="w-full max-w-md relative z-10">
          <div className="lg:hidden mb-8 flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[var(--brand)] flex items-center justify-center text-white font-heading font-bold">M</div>
            <div className="font-heading text-lg font-bold">{PRODUCT_NAME}</div>
          </div>

          {!selected ? (
            <div className="fadeup">
              <h1 className="font-heading text-3xl font-bold tracking-tight text-[var(--ink)] mb-1">Welcome back</h1>
              <p className="text-[var(--ink-2)] text-sm mb-8">Select your profile to continue</p>
              {loadingCards ? (
                <div className="text-sm text-[var(--ink-3)]">Loading profiles…</div>
              ) : cards.length ? (
                <div className="grid grid-cols-2 gap-3" data-testid="role-cards">
                  {cards.map((r) => (
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
              ) : (
                /* Server unreachable or no profiles yet — never strand the user
                   on a screen with nothing to click. */
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    const u = typedUser.trim().toLowerCase();
                    if (u) { setSelected({ username: u, name: u, icon: u.slice(0, 2).toUpperCase(), color: "#3A3F3A", subtitle: "Sign in" }); setPin(""); }
                  }}
                  data-testid="username-fallback"
                >
                  <label className="block text-xs uppercase tracking-[0.16em] text-[var(--ink-3)] font-semibold mb-2">
                    Username
                  </label>
                  <input
                    value={typedUser}
                    onChange={(e) => setTypedUser(e.target.value)}
                    placeholder="e.g. admin"
                    autoFocus
                    className="w-full px-3 py-2.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-sm outline-none focus:border-[var(--brand)]"
                    data-testid="username-input"
                  />
                  <button
                    type="submit"
                    className="mt-3 w-full py-2.5 rounded-lg bg-[var(--brand)] text-white text-sm font-semibold"
                  >
                    Continue
                  </button>
                </form>
              )}
              <div className="mt-8 text-xs text-[var(--ink-3)] text-center">
                Ask your administrator for your PIN.
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
                    key={k || `pin-key-spacer-${idx}`}
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
