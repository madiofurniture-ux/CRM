// Indian mobile number validation/normalization, mirroring the backend rule
// in backend/server.py::normalize_indian_phone. Kept in sync deliberately —
// this gives instant field-level feedback while the backend stays the source
// of truth (never rely on this alone).

const ALLOWED = /^\+?[0-9][0-9\s-]*$/;
const VALID_10 = /^[6-9]\d{9}$/;

// Returns { valid: boolean, normalized: string, message: string }
// normalized is the bare 10-digit form on success, "" for an empty input.
export function validateIndianPhone(raw) {
  const s = String(raw || "").trim();
  if (!s) return { valid: true, normalized: "", message: "" };

  if (!ALLOWED.test(s)) {
    return { valid: false, normalized: "", message: "Only digits, spaces, - and a leading + are allowed." };
  }
  let digits = s.replace(/[\s-]/g, "").replace(/^\+/, "");
  if (digits.length === 12 && digits.startsWith("91")) digits = digits.slice(2);

  if (!VALID_10.test(digits)) {
    return {
      valid: false,
      normalized: "",
      message: "Enter a valid 10-digit Indian mobile number starting with 6, 7, 8 or 9 (e.g. 9876543210 or +919876543210).",
    };
  }
  return { valid: true, normalized: digits, message: "" };
}

export function formatIndianPhone(digits) {
  const s = String(digits || "");
  return VALID_10.test(s) ? `+91 ${s.slice(0, 5)} ${s.slice(5)}` : s;
}
