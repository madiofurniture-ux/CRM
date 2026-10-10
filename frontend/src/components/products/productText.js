import { inrFull } from "@/lib/format";

/** A division's short brand tag from its brand name: "Madio Furniture" → MF,
 * "Madio Doors & Windows" → MDW; MAP stays MAP. */
export function brandTag(division, brand) {
  if (String(division || "").toUpperCase() === "MAP") return "MAP";
  const words = String(brand || division || "").replace(/[—–-]/g, " ").split(/\s+/).filter((w) => /^[A-Za-z]/.test(w));
  return words.map((w) => w[0].toUpperCase()).join("").slice(0, 4) || String(division || "").slice(0, 3).toUpperCase();
}

const SIZE_LINE = /^\s*(?:overall\s+)?(?:size|dimensions?|dims?)\b\s*[:：\-=]*\s*/i;

/** The product's size: its own field, else the size line of its specification. */
export function dimsOf(item) {
  if (item?.dimensions) return item.dimensions;
  const line = (item?.features || []).find((f) => SIZE_LINE.test(f));
  return line ? line.replace(SIZE_LINE, "").trim() : "";
}

/** The specification without its size line (the size has a field of its own;
 * the server writes "Size: …" back as the first line). */
export const withoutSizeLines = (features) => (features || []).filter((f) => !SIZE_LINE.test(f));

/** wa.me number: Indian 10-digit numbers get the 91 country code. */
export function waNumber(phone) {
  const d = String(phone || "").replace(/\D/g, "");
  if (d.length === 10) return `91${d}`;
  if (d.length === 11 && d.startsWith("0")) return `91${d.slice(1)}`;
  return d;
}

export const waHref = (phone, text) => `https://wa.me/${waNumber(phone)}?text=${encodeURIComponent(text)}`;

const madeToOrder = (item) => `Made to order${item?.lead_time ? `, ${item.lead_time.replace(/^made[\s-]*to[\s-]*order[,;\s-]*/i, "")}` : ""}`
  .replace(/,\s*$/, "");

/** The message a customer gets about one product. */
export function productMessage({ client, item, brand }) {
  const dims = dimsOf(item);
  const price = Number(item?.mrp) ? inrFull(item.mrp) : "on request";
  return [
    `Hello${client ? ` ${client}` : ""}, here are the details for the ${item.name} (Code: ${item.sku})${brand ? ` from ${brand}` : ""}.`,
    dims ? `Dimensions: ${dims}.` : "",
    `Price: ${price} (${madeToOrder(item)}).`,
    "Please let us know if you would like to proceed with customized finishes or 3D render kits.",
  ].filter(Boolean).join(" ");
}

// "Dining Table 240 × 110 cm" already says its size; "240 × 110 × 75 cm" again would be noise.
const sizeIn = (name, dims) => {
  const n = String(dims || "").match(/\d+(?:\.\d+)?/g) || [];
  return n.length >= 2 && new RegExp(`${n[0]}\\s*[x×*]\\s*${n[1]}`, "i").test(String(name || ""));
};

/** The estimate for several products: one line each, and the total. */
export function estimateMessage({ client, lines, brand, terms }) {
  const total = lines.reduce((t, l) => t + (Number(l.item.mrp) || 0) * (Number(l.qty) || 0), 0);
  const rows = lines.map((l, i) => {
    const each = Number(l.item.mrp) || 0;
    const dims = dimsOf(l.item);
    return `${i + 1}. ${l.item.name} (${l.item.sku})${dims && !sizeIn(l.item.name, dims) ? `, ${dims}` : ""}: ` +
      `${l.qty} × ${each ? inrFull(each) : "price on request"}` + (each && l.qty > 1 ? ` = ${inrFull(each * l.qty)}` : "");
  });
  const said = /\bgst\b/i.test(terms || "") ? terms : `prices include GST${terms ? `; ${terms}` : ""}`;
  return [
    `Hello${client ? ` ${client}` : ""}, here is your estimate${brand ? ` from ${brand}` : ""}:`,
    ...rows,
    `Total: ${inrFull(total)} (${said}; made to order).`,
    "Please let us know if you would like to proceed, or if you'd like customized finishes or 3D render kits.",
  ].join("\n");
}
