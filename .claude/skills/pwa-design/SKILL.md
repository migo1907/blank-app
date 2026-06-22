---
name: pwa-design
description: >
  Design and polish a mobile-first Progressive Web App to a professional,
  "fintech-grade" standard. Use when building or improving a PWA's visual
  design, color system, typography, layout, components, dark/light theming,
  app icons/splash/manifest, install flow, or overall outlook. Encodes a
  research-backed design system (tiered dark surfaces, accent-as-signal,
  tabular numerals, hairline borders) drawn from Linear, Coinbase,
  TradingView, Robinhood and Bloomberg.
---

# PWA Design Skill

A practical system for making a Progressive Web App look and feel professional —
quiet, dense, and trustworthy rather than toy-like. Default to **dark-first**,
**mobile-first**, and **color-as-signal**. Whitespace, type hierarchy, and
restraint do the heavy lifting; accent color is used sparingly.

## Core principles

1. **Tiers + hairlines, not heavy shadows.** Build depth with 2–3 background/
   surface tiers and 1px borders. Reserve large shadows for true overlays
   (modals, drawers, dropdowns). This is the #1 lever that makes a dark UI look
   intentional vs. flat.
2. **One brand accent, used precisely.** Pick a single accent (here: gold) and
   use it ONLY for brand identity, the active state, primary actions, focus
   rings, and selected rows. Never for data meaning.
3. **Color = signal, never decoration.** Green/red are reserved strictly for
   gain/loss / positive-negative semantics. Desaturate them (neon green reads
   consumer). Always pair color with a glyph (▲/▼) — ~8% of users can't rely on
   red/green alone.
4. **Numbers are the hero.** Use `font-variant-numeric: tabular-nums` everywhere
   prices/percentages appear so columns don't jitter on refresh. A mono font
   (IBM Plex Mono / JetBrains Mono) for dense numeric columns.
5. **Hierarchy via weight + tracking + tier, not size alone.** Quiet uppercase
   "eyebrow" labels in a muted tier; bold near-white values. Avoid pure #000 and
   pure #fff (halation) — use near-black bg and near-white text.
6. **Every screen opens with a headline.** A hero summary/strip at the top of
   each view, not a wall of filters or raw rows.
7. **Skeletons over spinners.** Shimmer placeholders that match final layout for
   network/refresh states; explicit, recoverable empty/error states.

## Color tokens (drop-in CSS variables)

Define tokens once on `:root`; theme by overriding on `:root[data-theme="light"]`.
Keep legacy aliases so existing styles don't break.

```css
:root {
  color-scheme: dark;
  --bg:#0a0b0d; --surface:#15171b; --surface-2:#1c1f24; --surface-3:#23272e;
  --border:#23262c; --border-2:#32363e; --border-hi:#3c424d;
  --accent:#f5b027; --accent-dim:rgba(245,176,39,.12); --accent-line:rgba(245,176,39,.32); --accent-text:#fbc04a;
  --pos:#2ebd85; --pos-dim:rgba(46,189,133,.13); --pos-text:#34d399;   /* gains */
  --neg:#f6465d; --neg-dim:rgba(246,70,93,.13);  --neg-text:#ff6076;   /* losses */
  --text-hi:#f5f7fa; --text:#c8cddb; --text-mut:#8089a0; --text-dim:#69718a;
  --r-sm:6px; --r-md:10px; --r-lg:14px; --r-pill:999px;
  --shadow-card:0 1px 2px rgba(0,0,0,.35), 0 6px 20px rgba(0,0,0,.30);
  --shadow-pop:0 12px 40px rgba(0,0,0,.6);
  --mono:'IBM Plex Mono','SF Mono',ui-monospace,monospace;
  --sans:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}
:root[data-theme="light"] {
  color-scheme: light;
  --bg:#eef1f6; --surface:#fff; --surface-2:#f3f5f9; --surface-3:#e7ebf2;
  --border:#e3e7ef; --border-2:#cdd4e0; --border-hi:#b6bece;
  --accent:#c9890d; --accent-dim:rgba(201,137,13,.13); --accent-line:rgba(201,137,13,.42); --accent-text:#9a6a08;
  --pos:#0f9d6b; --pos-text:#0a875b; --neg:#e23149; --neg-text:#c8253c;
  --text-hi:#0e1320; --text:#2b3344; --text-mut:#5a6478; --text-dim:#8089a0;
  --shadow-card:0 1px 2px rgba(20,30,55,.06), 0 4px 14px rgba(20,30,55,.07);
}
```

Rules: gain/loss = tinted badge (`--pos-dim`/`--neg-dim` bg) + colored value +
▲/▼. Accent never encodes gain/loss. Charts must use the SAME hex as the CSS
tokens (define one JS color const and reuse) so a chart green matches a badge green.

## Typography scale

`Inter` (variable) for UI; tabular figures for numbers; a mono for dense columns.

| Token | Size/Line | Weight | Use |
|---|---|---|---|
| hero | 28–34 / 1.15 | 800, tnum | portfolio value / top quote |
| h2 | 17 / 1.4 | 700 | section header |
| price | 15–17 | 700, tnum | row price |
| body | 14–15 / 1.6 | 400 | default text |
| label | 11–12, +.08em | 600 | field labels |
| eyebrow | 10–11, UPPERCASE, +.1em | 700, muted | section/card titles |

## Layout & component patterns

- **Bottom tab bar, 5 anchors max.** Stroke icons only (1.5–2px, e.g. lucide),
  never filled/duotone. Active = accent icon+label; inactive = muted. Overflow
  goes in a "More" sheet or a side drawer.
- **Quote/watchlist = divided list, not a card per row.** Dividers inside one
  card; ticker+name left, price + colored % right, optional sparkline. Right-
  align numbers, tabular-nums, sticky first column on horizontal scroll.
- **Trade/signal cards = structured "tickets":** bold direction at top, a
  confidence meter, a key-value grid (Entry · Stop · TP) in mono, an accent
  chip, timestamp in the dim tier. Show R:R. Use a left-border color to encode
  direction/sentiment — reuse that left-border language across news, calendar,
  watchlist, P&L for a "designed by one hand" feel.
- **Cards:** `--surface` on `--bg`, 1px `--border`, `--r-md`, subtle
  `--shadow-card`. Section title gets a small accent rail (`::before`).
- **Sparklines:** single 1.5px line colored by net direction + a 12% gradient
  fill, no axes. Full charts: gridlines at `rgba(255,255,255,.05)`, dotted
  reference lines for prior-close/levels, axis labels in the dim tier.
- **8px spacing grid** (8/12/16/24). Generous vertical rhythm between sections.
- **Micro-interactions:** `:active{transform:scale(.97)}` on tappables; 120–150ms
  transitions; real `:focus-visible` ring (`box-shadow: 0 0 0 2px var(--bg), 0 0 0 4px var(--accent-line)`).

## PWA essentials

- **manifest.json:** name, short_name, `start_url`, `display:"standalone"`,
  `theme_color`/`background_color` matching the app canvas, `orientation`, and
  PNG icons **192** + **512** (`purpose:"any maskable"`).
- **Icons/head:** `<link rel="apple-touch-icon" href=…180px>`, `favicon-32/16`,
  and `<meta name="theme-color">`. Generate icons from one square source.
- **Splash/cover:** a branded full-screen cover; **preload the logo**
  (`<link rel="preload" as="image" fetchpriority="high">`) so it loads in
  parallel with the JS bundle, and animate text in independently so it never
  looks blank.
- **Link previews:** Open Graph + Twitter Card meta (title, description, 512
  image) so shared links render a branded card, not a bare URL.
- **Installability:** ship a service worker; "Add to Home Screen" then hides the
  URL bar (standalone). Test install on iOS Safari + Android Chrome.
- **Safe areas:** `viewport-fit=cover` + `env(safe-area-inset-*)` padding on
  fixed nav/headers/FABs.
- **Theme persistence:** store the dark/light choice in `localStorage` and set
  `data-theme` on `<html>` before first paint.

## Accessibility & comfort

- Text contrast ≥ 4.5:1 at small sizes; never encode meaning by color alone.
- Tap targets ≥ 40px. Respect `prefers-reduced-motion`.
- Comfortable base size: 14–15px body, not 11–12px. Bump the type scale before
  shrinking to fit more in.

## Working checklist

1. Tokenize colors/spacing/radii; one accent, semantic green/red, text tiers.
2. Tabular numerals + mono columns; right-align + sticky-first-column tables.
3. Tiered surfaces + hairline borders; shadows only for overlays.
4. Stroke icon set; 5-tab bottom nav; hero summary atop each screen.
5. Skeletons + empty/error states; micro-interactions + focus rings.
6. PWA: manifest, 192/512 maskable icons, apple-touch + favicons, preload splash,
   OG tags, service worker, safe-area insets, persisted dark/light theme.
7. Verify it **builds** and, where possible, **renders** on a real phone.

## References

Linear (tiered onyx surfaces, Inter), Coinbase CDS (Woodsmoke base, 4.5:1
discipline), TradingView (IBM Plex Mono + density), Robinhood (green/red
semantics), Bloomberg (concealing complexity, color-accessibility). Reserve a
multi-accent "terminal" palette (amber/cyan for non-P&L data) only for a future
heatmap view, not the default.
