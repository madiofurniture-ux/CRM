import { useEffect, useState } from "react";
import { MessageCircle } from "lucide-react";
import { waLink, logWhatsAppClick } from "@/lib/whatsapp";

/** WhatsApp click-to-chat icon button. Renders nothing if `phone` has no
 * usable number. href is precomputed on mount (not inside the click
 * handler) so the click is a plain <a> navigation — no popup blocker risk
 * from an async window.open(). */
export default function WhatsAppButton({ phone, context, customerName = "", ref = "",
                                          refType = "", refId = "", className = "", testId, label }) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    let alive = true;
    waLink(phone, context, { customerName, ref }).then((u) => { if (alive) setUrl(u); });
    return () => { alive = false; };
  }, [phone, context, customerName, ref]);

  if (!url) return null;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      title="WhatsApp"
      data-testid={testId}
      onClick={() => logWhatsAppClick(context, { to: phone, customerName, refType, refId })}
      className={className || "p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]"}
    >
      <MessageCircle size={13} />
      {label}
    </a>
  );
}
