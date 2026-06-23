# PWA Capabilities & Accessibility

Contents: Manifest & installability · Icons/splash/OG · Install prompt · Web push ·
Badging · Service-worker caching · iOS vs Android · WCAG contrast · Targets · Focus ·
ARIA · Color independence.

## Manifest & installability (Chromium)
- Required: **`name` or `short_name`**, **`start_url`** (land *inside* the app, not a
  marketing page), **`display`** = `standalone` | `fullscreen` | `minimal-ui`,
  **`icons` incl. 192×192 and 512×512**, and `prefer_related_applications` not `true`.
- Plus **HTTPS** + a registered **service worker** with a fetch handler.
- Add a **maskable** icon for adaptive Android shapes; `theme_color`/`background_color`
  matching the app canvas.

## Icons / splash / link previews
- Generate from one square source: **192 + 512 PNG** (`purpose:"any maskable"`),
  **apple-touch-icon 180**, **favicon 32/16**. `<meta name="theme-color">`.
- **Splash/cover:** branded full-screen cover; **preload the logo**
  (`<link rel="preload" as="image" fetchpriority="high">`) so it loads in parallel
  with the JS bundle; animate text in independently so it never looks blank.
- **Open Graph + Twitter Card** meta (title, description, 512 image) so shared links
  render a branded card, not a bare URL.

## Install prompt (`beforeinstallprompt`)
- Fires when installable (needs **≥30s domain engagement**). Call `e.preventDefault()`,
  stash the event, show your OWN install UI; call `event.prompt()` only inside a
  user-gesture handler, once per event instance.
- **Timing:** not on first visit — after ~5 min on site OR 3 page views OR right after
  a completed key journey. Limit ~1×/session. Custom prompts drive up to ~5× engagement,
  ~6× add-to-home-screen.
- **iOS Safari has no `beforeinstallprompt`** — show manual "Share → Add to Home Screen".

## Web push UX
- **Never ask on load.** Use a **soft pre-prompt** (your own in-page "Enable / Not now"
  explaining value); only on positive signal call native `Notification.requestPermission()`
  — a hard "Block" is effectively permanent. Pre-prompts lift opt-in ~20% (well-designed
  reach 60–70%). Trigger on a **user gesture**, in context.
- **iOS/iPadOS:** web push requires the PWA be **Added to Home Screen (iOS 16.4+)** — it
  does NOT work in the Safari tab; prompt must be user-triggered. Uses standard Web Push
  (Push API + SW + VAPID), no Apple Developer fee. (Declarative Web Push, iOS 18.4+, works
  without an active SW.)

## Badging (`navigator.setAppBadge`)
- `setAppBadge(n)` = number; `setAppBadge()` = dot; `clearAppBadge()` clears. **Installed
  PWA only.** Chrome/Edge/Samsung + **iOS 16.4+ Safari**. **Android shows only a dot** —
  don't rely on the integer being visible.

## Service-worker caching strategies (pick per resource type)
- **Precache / app shell** — cache static HTML/CSS/JS at install → instant offline boot.
- **Cache-first** — versioned/fingerprinted assets (JS/CSS/fonts/images). NOT for HTML
  or unversioned APIs (stale after deploys).
- **Network-first** (with ~5s timeout → cache) — HTML documents and fresh-data APIs.
- **Stale-while-revalidate** — best speed/freshness balance: avatars, non-critical API
  data, frequently-updated-but-not-critical content.
- Workbox default mapping: versioned JS/CSS → cache-first; APIs → network-first(5s);
  images → stale-while-revalidate.

## WCAG 2.2 — contrast (1.4.3 / 1.4.11, AA)
- **Normal text ≥ 4.5:1**; **large text ≥ 3:1** (large = ≥18pt/24px regular or
  ≥14pt/18.66px bold). **UI components & graphics ≥ 3:1** (button borders, input
  outlines, focus rings, meaningful icons/chart strokes).
- **Don't round** — 4.499:1 fails. Exempt: logos, disabled controls, pure decoration.
- Fintech: a green/red P&L number on dark must still hit 4.5:1 — pure neon often fails.

## Target size (2.5.8 AA / 2.5.5 AAA)
- **AA ≥ 24×24px** (exception: a 24px circle centered on each target doesn't overlap
  another); **AAA ≥ 44×44px**. Apple 44pt, Material 48dp. Use 44–48px; ≥8px spacing.

## Focus
- **2.4.7 Focus Visible:** never `outline:none` without a replacement ring.
- **2.4.11 Focus Not Obscured:** focused element not entirely hidden by sticky chrome.
- **2.4.13 (AAA):** indicator ≥ a 2px perimeter at ≥3:1 contrast.
- **Dialogs:** trap focus while open; focus first element on open; **Esc closes**;
  **return focus to the trigger** on close.

## ARIA patterns (WAI-ARIA APG)
- **Tabs:** `role="tablist"` › `role="tab"` (`aria-selected`, `aria-controls`) ›
  `role="tabpanel"` (`aria-labelledby`); arrow keys switch; roving `tabindex` (active 0, rest −1).
- **Modal:** `role="dialog"` + `aria-modal="true"` + `aria-labelledby`/`describedby`;
  background inert.
- **Live numbers/prices:** wrap changing value in `aria-live="polite"` (must exist in
  DOM before the update); `assertive` only for critical alerts.

## Color independence & screen readers
- **Never +/- by color alone** (1.4.1): `▲ +2.4%` / `▼ −1.1%` or visually-hidden text.
- `aria-label` on icon-only buttons, sparklines, chart canvases (summarize the trend:
  "AAPL up 2.4% today, ranging 187–192"); decorative icons `aria-hidden="true"`.
- Tabular numerals for aligned price columns.
