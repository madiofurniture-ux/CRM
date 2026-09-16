// Applies a tenant's custom brand color to the CSS variables index.css
// defines (--brand family for hex-based utilities, --primary/--ring for the
// shadcn HSL-based components) so Business Settings' color pickers actually
// change how the app looks, not just what's stored.

function hexToHsl(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return null;
  const r = parseInt(m[1].slice(0, 2), 16) / 255;
  const g = parseInt(m[1].slice(2, 4), 16) / 255;
  const b = parseInt(m[1].slice(4, 6), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h, s;
  const l = (max + min) / 2;
  if (max === min) { h = s = 0; }
  else {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      default: h = (r - g) / d + 4;
    }
    h /= 6;
  }
  return { h: Math.round(h * 360), s: Math.round(s * 100), l: Math.round(l * 100) };
}

function shade(hex, amount) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return hex;
  const clamp = (v) => Math.max(0, Math.min(255, v));
  const c = m[1].match(/.{2}/g).map((h) => clamp(parseInt(h, 16) + amount));
  return "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");
}

/** Applies tenant.primary_color / secondary_color as CSS custom properties
 * on the document root. Falls back to the default palette (no-op) when a
 * tenant hasn't set one, so entities that never touch branding keep the
 * shipped Aura Blue look. */
export function applyTenantTheme(tenant) {
  const root = document.documentElement.style;
  const primary = tenant?.primary_color;
  const hsl = hexToHsl(primary);
  if (hsl) {
    root.setProperty("--brand", primary);
    root.setProperty("--brand-hover", shade(primary, -18));
    root.setProperty("--primary", `${hsl.h} ${hsl.s}% ${hsl.l}%`);
    root.setProperty("--ring", `${hsl.h} ${hsl.s}% ${hsl.l}%`);
  } else {
    root.removeProperty("--brand");
    root.removeProperty("--brand-hover");
    root.removeProperty("--primary");
    root.removeProperty("--ring");
  }

  const secondary = tenant?.secondary_color;
  const secHsl = hexToHsl(secondary);
  if (secHsl) {
    root.setProperty("--moss", secondary);
  } else {
    root.removeProperty("--moss");
  }
}
