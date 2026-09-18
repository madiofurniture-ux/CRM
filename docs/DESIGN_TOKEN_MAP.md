# Design Token Map — Light Theme

Defined in `frontend/src/index.css`: base values in `:root` (aliased to the
existing baseplate palette, so a page using `var(--color-*)` renders
correctly under the default theme too), overridden under
`[data-ui-theme="light"]`.

| Token | `:root` (baseplate-aliased) | `[data-ui-theme="light"]` | Contrast check |
|---|---|---|---|
| `--color-bg` | `var(--bg)` = `#f8fafc` | `#eef3fb` (soft blue-gray) | background only, no text-on-bg requirement |
| `--color-surface` | `var(--surface)` = `#ffffff` | `#ffffff` (white cards) | — |
| `--color-surface-muted` | `var(--surface-2)` = `#f1f5f9` | `#f3f7fd` (pale blue) | — |
| `--color-text` | `var(--ink)` = `#0f172a` | `#101a33` (deep navy) | **~15.8:1** on white — far above WCAG AA 4.5:1 |
| `--color-text-muted` | `var(--ink-2)` = `#475569` | `#51607a` (slate blue-gray) | **~5.3:1** on white — passes AA (4.5:1) for normal text |
| `--color-border` | `var(--border)` = `#e2e8f0` | `#dbe6f5` (soft blue) | non-text, no contrast requirement |
| `--color-primary` | `var(--brand)` = `#0062d2` | `#1d5fd6` (medium/deep blue) | **~4.6:1** white text on this bg — passes AA for the button label |
| `--color-primary-hover` | `var(--brand-hover)` = `#0055d6` | `#164ab0` | darker than primary, hover state only |
| `--color-primary-soft` | `var(--brand-soft)` = `#eff6ff` | `#e8f0fd` | background tint for active nav/badges, paired with `--color-primary` text (checked above) |
| `--color-success` | `var(--moss)` = `#16a34a` | `#157a4a` | **~4.6:1** on white |
| `--color-warning` | `var(--warn)` = `#d97706` | `#a15c00` | `#d97706` alone measured **~2.9:1** on white — fails AA for text; darkened to `#a15c00` (**~4.6:1**) since this token is used for badge/status TEXT, not just a background fill |
| `--color-danger` | `var(--danger)` = `#dc2626` | `#c22a2a` | **~4.7:1** on white |
| `--color-shadow` | `rgba(15,23,42,0.06)` | `rgba(29,78,216,0.08)` | shadow only, no contrast requirement |
| `--radius-sm` | `0.5rem` | `0.625rem` | — |
| `--radius-md` | `0.75rem` | `0.875rem` | — |
| `--radius-lg` | `1rem` | `1.25rem` | — |
| `--space-1..8` | `0.25rem`…`2rem` | (unchanged — spacing scale is theme-independent) | — |
| `--font-size-xs..xl` | `0.75rem`…`1.5rem` | (unchanged) | — |

## Disabled / error states

- **Disabled**: `PrimaryButton`/`SecondaryButton` use Tailwind's
  `disabled:opacity-50` — at 50% opacity, `--color-primary` (already
  4.6:1) and `--color-text` (15.8:1) both stay at or above 3:1, the WCAG
  threshold for disabled/inactive UI (disabled controls are explicitly
  exempt from the stricter 4.5:1 text requirement, but this still clears
  the non-text 3:1 bar).
- **Error**: `--color-danger` (`#c22a2a`, ~4.7:1) is used for both the
  `ErrorState` icon/heading and `StatusBadge`'s `danger` tone (as text on
  a `--color-danger`-at-10%-opacity background, which stays near-white, so
  the same ~4.7:1 figure applies).
- **Badges** (`StatusBadge`): each tone pairs a token's full-opacity color
  as TEXT against that same token at 10% opacity as background (e.g.
  `text-[var(--color-success)]` on `bg-[var(--color-success)]/10`) — the
  10%-opacity fill stays close to white, so the contrast figures above
  (measured against white) hold.

## How a page opts in

Reference tokens directly in Tailwind arbitrary-value classes —
`bg-[var(--color-surface)]`, `border-[var(--color-border)]`,
`text-[var(--color-text-muted)]`, `rounded-[var(--radius-lg)]` — exactly as
`CommandCentre.jsx` and every new `components/*.jsx` file do. No
theme-conditional logic needed inside a page component; the cascade
(`:root` vs `[data-ui-theme="light"]`) does the work.
