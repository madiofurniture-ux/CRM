import api from "@/lib/api";

let templatesCache = null;
async function templates() {
  if (!templatesCache) {
    const { data } = await api.get("/notifications/templates");
    templatesCache = data;
  }
  return templatesCache;
}

function render(template, vars) {
  return (template || "").replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
}

function toE164(phone) {
  const digits = String(phone || "").replace(/\D/g, "").slice(-10);
  return digits.length === 10 ? `91${digits}` : "";
}

/** Builds a wa.me click-to-chat URL for a context ("quote-shared" |
 * "payment-reminder" | "installation-scheduled" | "follow-up"), using the
 * same message copy as an automated notify() send so the two never drift. */
export async function waLink(phone, context, { customerName = "", ref = "" } = {}) {
  const e164 = toE164(phone);
  if (!e164) return null;
  const tpl = await templates();
  const message = render(tpl[context], { customer_name: customerName, ref });
  return `https://wa.me/${e164}?text=${encodeURIComponent(message)}`;
}

/** Fire-and-forget: logs a click-to-chat button press into notification_logs. */
export function logWhatsAppClick(context, { to, customerName = "", refType = "", refId = "" }) {
  api.post("/notifications/whatsapp-click", {
    context, to, customer_name: customerName, ref_type: refType, ref_id: refId,
  }).catch(() => {});
}
