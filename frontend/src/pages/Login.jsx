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
const PRODUCT_TAGLINE = process.env.REACT_APP_PRODUCT_TAGLINE || "Enquiry · Quotation · Delivery · Payment";

// PINs are 4–6 digits (POST /tenants and user creation accept "at least 4").
// After a first successful sign-in the device remembers that user's PIN
// length, so the pad submits by itself on the last digit as it always has.
const PIN_MIN = 4;
const PIN_MAX = 6;
const pinLenKey = (u) => `crm_pin_len:${u}`;
const knownPinLength = (u) => {
  try { return Number(localStorage.getItem(pinLenKey(u))) || 0; } catch { return 0; }
};

// The login hero: the product's own Stage Path chevrons in theme colours —
// no third-party image to break, hot-link or slow the first paint.
function Hero() {
  const steps = [
    { label: "Enquiry", cls: "fill-[var(--color-success)]" },
    { label: "Site visit", cls: "fill-[var(--color-success)]" },
    { label: "Quotation", cls: "fill-[var(--color-primary)]" },
    { label: "Order", cls: "fill-white/25" },
    { label: "Paid", cls: "fill-white/25" },
  ];
  const w = 118;
  return (
    <svg viewBox="0 0 560 64" className="w-full max-w-lg" aria-hidden="true">
      {steps.map((st, i) => {
        const x = i * (w - 6);
        const notch = i === 0 ? `${x},0` : `${x},0 ${x + 12},32`;
        const pts = i === 0
          ? `${x},0 ${x + w - 12},0 ${x + w},32 ${x + w - 12},64 ${x},64`
          : `${notch} ${x},64 ${x + w - 12},64 ${x + w},32 ${x + w - 12},0`;
        return (
          <g key={st.label}>
            <polygon points={pts} className={st.cls} />
            <text x={x + w / 2 + (i ? 4 : -2)} y="37" textAnchor="middle" className="fill-white" fontSize="13" fontWeight="600">{st.label}</text>
          </g>
        );
      })}
    </svg>
  );
}

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
  const [useUsername, setUseUsername] = useState(false);

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

  const autoLen = selected ? knownPinLength(selected.username) : 0;
  useEffect(() => {
    if (selected && autoLen && pin.length === autoLen) {
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
      try { localStorage.setItem(pinLenKey(selected.username), String(pin.length)); } catch { /* private mode */ }
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
    else if (pin.length < PIN_MAX) setPin((p) => p + k);
  };

  // The PIN pad is on-screen buttons, not a text input, so a physical keyboard
  // did nothing unless a button happened to have mouse focus. Digits and
  // Backspace/Delete now drive the same press() a click would.
  useEffect(() => {
    if (!selected) return;
    const onKey = (e) => {
      if (e.key >= "0" && e.key <= "9") press(e.key);
      else if (e.key === "Backspace" || e.key === "Delete") press("del");
      else if (e.key === "Enter" && pin.length >= PIN_MIN && !submitting) doLogin();
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
        <div className="absolute inset-0 bg-[var(--stage-current,#014486)]" />
        <div className="absolute inset-0 opacity-[0.07]" style={{ backgroundImage: "radial-gradient(circle, #fff 1px, transparent 1px)", backgroundSize: "24px 24px" }} />
        <div className="relative z-10 text-white max-w-lg">
          <div className="flex items-center gap-3 mb-10">
            <div className="w-11 h-11 rounded-xl bg-white text-[var(--stage-current,#014486)] flex items-center justify-center font-heading font-bold text-lg">{PRODUCT_NAME.slice(0, 1)}</div>
            <div>
              <div className="font-heading text-xl font-bold tracking-tight">{PRODUCT_NAME}</div>
              <div className="text-[11px] uppercase tracking-[0.2em] text-white/70">{PRODUCT_TAGLINE}</div>
            </div>
          </div>
          <Hero />
          <h2 className="font-heading text-4xl font-bold leading-tight mt-10 mb-3">
            Every enquiry.<br />Every quotation.<br />Every rupee — tracked.
          </h2>
          <p className="text-white/80 text-sm leading-relaxed">
            GST-ready quotations and invoices, WhatsApp follow-ups, site and delivery tracking,
            and the numbers behind them — set up for your trade in minutes.
          </p>
        </div>
      </div>

      {/* Right: login */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12 relative">
        <div className="brand-blob w-72 h-72 bg-[var(--brand-soft)] top-10 right-10" />
        <div className="brand-blob w-64 h-64 bg-[var(--moss-soft)] bottom-20 left-10" />

        <div className="w-full max-w-md relative z-10">
          <div className="lg:hidden mb-8 flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[var(--brand)] flex items-center justify-center text-white font-heading font-bold">{PRODUCT_NAME.slice(0, 1)}</div>
            <div className="font-heading text-lg font-bold">{PRODUCT_NAME}</div>
          </div>

          {!selected ? (
            <div className="fadeup">
              <h1 className="font-heading text-3xl font-bold tracking-tight text-[var(--ink)] mb-1">Welcome back</h1>
              <p className="text-[var(--ink-2)] text-sm mb-8">{cards.length && !useUsername ? "Select your profile to continue" : "Sign in to your company's workspace"}</p>
              {loadingCards ? (
                <div className="text-sm text-[var(--ink-3)]">Loading profiles…</div>
              ) : cards.length && !useUsername ? (
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
              {cards.length > 0 && (
                <button type="button" onClick={() => setUseUsername((v) => !v)} data-testid="toggle-username"
                  className="mt-5 w-full text-sm font-semibold text-[var(--brand)] hover:underline">
                  {useUsername ? "← Choose a profile instead" : "Sign in with your username"}
                </button>
              )}
              <div className="mt-6 text-xs text-[var(--ink-3)] text-center">
                Ask your administrator for your username and PIN.
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

              <div className="mb-2 text-xs uppercase tracking-[0.16em] text-[var(--ink-3)] font-semibold">Enter your PIN</div>
              <div className="flex gap-3 mb-6" data-testid="pin-dots">
                {Array.from({ length: Math.max(PIN_MIN, autoLen || 0, pin.length + (pin.length < PIN_MAX ? 1 : 0)) }, (_, i) => i).map((i) => (
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

              {!autoLen && (
                <button type="button" onClick={doLogin} disabled={pin.length < PIN_MIN || submitting} data-testid="pin-submit"
                  className="mt-4 w-full py-3 rounded-lg bg-[var(--brand)] text-white text-sm font-semibold disabled:opacity-50">
                  Sign in
                </button>
              )}
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
