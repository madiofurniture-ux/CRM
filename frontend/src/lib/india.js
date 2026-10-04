// Indian business rules on the client — mirrors backend/india.py so forms can
// validate as the user types. The server re-checks everything on save.

const GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const GSTIN_RE = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;

export const GST_STATES = {
  "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
  "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
  "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
  "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
  "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
  "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka",
  "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
  "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
  "97": "Other Territory",
};

export const STATE_OPTIONS = Object.entries(GST_STATES)
  .map(([code, name]) => ({ code, name }))
  .sort((a, b) => a.name.localeCompare(b.name));

export function gstinCheckChar(first14) {
  let total = 0;
  for (let i = 0; i < first14.length; i += 1) {
    const v = GSTIN_CHARS.indexOf(first14[i]) * (i % 2 ? 2 : 1);
    total += Math.floor(v / 36) + (v % 36);
  }
  return GSTIN_CHARS[(36 - (total % 36)) % 36];
}

/** { valid, gstin, state, pan, error } — offline checks only. */
export function validateGstin(value) {
  const g = String(value || "").replace(/\s+/g, "").toUpperCase();
  const out = { valid: false, gstin: g, state: "", pan: "", error: "" };
  if (!g) return { ...out, error: "" };
  if (g.length !== 15) return { ...out, error: `${g.length}/15 characters` };
  if (!GSTIN_RE.test(g)) return { ...out, error: "Not in GSTIN format" };
  if (!GST_STATES[g.slice(0, 2)]) return { ...out, error: `Unknown state code ${g.slice(0, 2)}` };
  if (gstinCheckChar(g.slice(0, 14)) !== g[14]) return { ...out, error: "Check digit doesn't match — likely a typo" };
  return { ...out, valid: true, state: GST_STATES[g.slice(0, 2)], pan: g.slice(2, 12) };
}

const ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
  "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"];
const TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"];
const two = (n) => (n < 20 ? ONES[n] : `${TENS[Math.floor(n / 10)]}${n % 10 ? ` ${ONES[n % 10]}` : ""}`);
const three = (n) => [n >= 100 ? `${ONES[Math.floor(n / 100)]} Hundred` : "", n % 100 ? two(n % 100) : ""]
  .filter(Boolean).join(" ");

export function numberInWords(n) {
  n = Math.floor(Math.abs(Number(n) || 0));
  if (n === 0) return "Zero";
  const crore = Math.floor(n / 1e7);
  const lakh = Math.floor((n % 1e7) / 1e5);
  const thousand = Math.floor((n % 1e5) / 1e3);
  const rest = n % 1000;
  return [
    crore ? `${numberInWords(crore)} Crore` : "",
    lakh ? `${two(lakh)} Lakh` : "",
    thousand ? `${two(thousand)} Thousand` : "",
    rest ? three(rest) : "",
  ].filter(Boolean).join(" ");
}

/** 125000.5 → "Rupees One Lakh Twenty Five Thousand and Fifty Paise Only" */
export function amountInWords(amount) {
  const v = Math.round(Math.abs(Number(amount) || 0) * 100) / 100;
  let rupees = Math.floor(v);
  let paise = Math.round((v - rupees) * 100);
  if (paise === 100) { rupees += 1; paise = 0; }
  return `${Number(amount) < 0 ? "Minus " : ""}Rupees ${numberInWords(rupees)}${paise ? ` and ${two(paise)} Paise` : ""} Only`;
}
