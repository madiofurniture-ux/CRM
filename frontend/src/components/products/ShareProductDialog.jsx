import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Copy, Image as ImageIcon, MessageCircle } from "lucide-react";
import api from "@/lib/api";
import { logWhatsAppClick } from "@/lib/whatsapp";
import ProductModal from "./ProductModal";
import { productMessage, waHref } from "./productText";

const field = "w-full px-2.5 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-sm";

async function pictureFile(item) {
  const { data } = await api.get(`/virtual-items/${item.id}`, { skipCache: true });
  const src = (data?.images || [])[0];
  if (!src) return null;
  const blob = await (await fetch(src)).blob();
  return new File([blob], `${item.sku}.jpg`, { type: blob.type || "image/jpeg" });
}

/** One product's details for a customer on WhatsApp: the message (MADIO's
 * name, code, size, price, made to order) ready to send, editable first.
 * On a phone, "Send with the picture" shares the photo and the text together. */
export default function ShareProductDialog({ item, brand, client, onClose }) {
  const [name, setName] = useState(client?.name || "");
  const [phone, setPhone] = useState(client?.phone || "");
  const [text, setText] = useState(() => productMessage({ client: client?.name, item, brand }));
  const [edited, setEdited] = useState(false);
  useEffect(() => {
    if (!edited) setText(productMessage({ client: name.trim(), item, brand }));
  }, [name, item, brand, edited]);
  const canShare = typeof navigator !== "undefined" && typeof navigator.share === "function";
  const log = () => logWhatsAppClick("product-shared", {
    to: phone, customerName: name, refType: client?.kind || "virtual_item", refId: item.sku,
  });

  const withPicture = async () => {
    try {
      const file = item.id ? await pictureFile(item) : null;
      if (file && navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], text });
        log();
      } else {
        await navigator.share({ text });
        log();
      }
    } catch (e) {
      if (e?.name !== "AbortError") toast.error("Couldn't open sharing here; use WhatsApp below");
    }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); toast.success("Message copied"); }
    catch { toast.error("Couldn't copy; select the text and copy it"); }
  };

  return (
    <ProductModal title={`Share ${item.sku} on WhatsApp`} onClose={onClose} testid="share-product">
      <div className="p-5 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <label className="text-sm space-y-1"><span className="font-medium">Customer's name</span>
            <input className={field} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Ravi"
                   data-testid="share-name" /></label>
          <label className="text-sm space-y-1"><span className="font-medium">WhatsApp number</span>
            <input className={field} value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel"
                   placeholder="Leave empty to pick the chat" data-testid="share-phone" /></label>
        </div>
        <label className="block text-sm space-y-1"><span className="font-medium">Message</span>
          <textarea className={field} rows={6} value={text} onChange={(e) => { setEdited(true); setText(e.target.value); }}
                    data-testid="share-text" /></label>
        <p className="text-xs text-[var(--color-text-muted)]">MADIO's code, name and price only — never the vendor's.</p>
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className="lx-btn inline-flex items-center gap-1" onClick={copy}><Copy size={14} /> Copy</button>
          {canShare && (
            <button type="button" className="lx-btn inline-flex items-center gap-1" onClick={withPicture} data-testid="share-native">
              <ImageIcon size={14} /> Send with the picture</button>
          )}
          <a href={waHref(phone, text)} target="_blank" rel="noreferrer" onClick={log}
             className="lx-btn lx-btn-brand inline-flex items-center gap-1" data-testid="share-whatsapp">
            <MessageCircle size={14} /> Open WhatsApp</a>
        </div>
      </div>
    </ProductModal>
  );
}
