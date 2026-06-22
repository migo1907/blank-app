---
name: pwa-design
description: >
  Designs and polishes mobile-first Progressive Web Apps to a professional,
  fintech-grade standard — visual design, color/token systems, typography,
  layout, components, motion, performance, accessibility, dark/light theming,
  and PWA install/icons/splash/push. Use when building or improving a PWA's
  look, feel, layout, or outlook; when creating dashboards, signal/ticket
  cards, data tables, charts, or watchlists; or when output must look
  hand-crafted rather than AI-generated. Encodes a research-backed system
  (tiered dark surfaces, accent-as-signal, semantic green/red for P&L,
  tabular numerals, hairline borders) drawn from Linear, Coinbase,
  TradingView, Robinhood and Bloomberg, plus Material 3, Apple HIG, web.dev
  and WCAG 2.2 specifics.
---

# PWA Design

Make a Progressive Web App look and feel **professional** — quiet, dense, and
trustworthy rather than toy-like. Process, not prose: follow the workflow,
apply the rules, run the checklist. Pull exact numbers from the reference files
on demand (they cost no context until you read them).

## When to use
- Building or restyling a mobile-first PWA (or any phone-first web UI).
- Designing dashboards, quote/watchlist lists, signal/trade "ticket" cards,
  data tables, charts/sparklines, calendars, portfolios.
- Adding dark/light theming, app icons, splash/cover, install flow, push.
- Auditing an existing UI that "looks AI-generated" or feels amateur.

## When NOT to use
- Pure backend/data/ML work with no UI surface.
- A desktop-only data terminal where density beats touch ergonomics (some
  touch-target rules relax — but the color/type/token rules still apply).

## Workflow
1. **Tokenize first.** Establish color/spacing/radius/type/elevation tokens in
   two tiers (primitive → semantic) before styling anything. Components
   reference semantic tokens only — never raw hex. → `references/design-tokens.md`
2. **Set the palette discipline.** One brand accent used ONLY for brand +
   interaction; desaturated green/red reserved for gain/loss, always paired
   with a ▲/▼ glyph. Charts use the SAME hex as the CSS tokens.
3. **Lay out mobile-first.** 5-tab bottom nav (stroke icons), a hero summary
   atop every screen, 8px spacing grid, generous vertical rhythm.
4. **Build components from the kit.** Divided lists (not card-per-row), ticket
   cards, mobile-safe tables, sparklines, forms. → `references/components.md`
5. **Add motion sparingly.** Compositor-only properties, Material-3 durations/
   easing, reduced-motion default. → `references/motion.md`
6. **Hold a performance budget.** Hit Core Web Vitals; code-split; prevent
   layout shift; skeletons over spinners. → `references/performance.md`
7. **Wire the PWA shell + push + a11y.** Manifest, 192/512 maskable icons,
   apple-touch/favicons, preloaded splash, OG tags, in-context push, WCAG 2.2.
   → `references/pwa-and-a11y.md`
8. **Verify.** Run the checklist below; build; render on a real phone if possible.

## Core principles (the load-bearing ones)
1. **Tiers + hairlines, not heavy shadows.** Depth via 2–3 surface tiers + 1px
   borders. On dark, express elevation by *lightening the surface* (overlay),
   not by drop shadows (they're invisible on dark). Big shadows only for true
   overlays (modals, sheets, dropdowns).
2. **One accent, used precisely.** Brand identity, active state, primary action,
   focus ring, selected row. Never to encode data meaning.
3. **Color = signal, never decoration.** Green/red only for positive/negative;
   desaturate them; ALWAYS double-encode with a glyph (~8% of men can't rely on
   red/green). Never `#00FF00`-style neon — it reads consumer and often fails
   contrast.
4. **Numbers are the hero.** `font-variant-numeric: tabular-nums` everywhere
   prices/percentages appear so columns don't jitter on refresh; a mono font for
   dense numeric columns; right-align numerics.
5. **Hierarchy via weight + tracking + tier, not size alone.** Quiet uppercase
   eyebrow labels in a muted tier; bold near-white values. Avoid pure #000 / #fff.
6. **Every screen opens with a headline.** A hero summary/strip, not a wall of
   filters or raw rows.
7. **Skeletons over spinners** (only when load >~500ms); explicit, recoverable
   empty/error states with a next action.
8. **Touch ergonomics.** ≥44–48px tap targets, ≥8px spacing, primary actions in
   the bottom (thumb) third, safe-area insets on fixed chrome.

## Reference files (load on demand)
- `references/design-tokens.md` — color (dark+light), spacing (8px grid + 4px),
  radius, type scale (1.25), elevation overlays, Material-3 state layers, token tiers.
- `references/components.md` — bottom nav, divided lists, mobile data tables,
  forms/inputs, ticket cards, charts/sparklines, gestures/sheets, empty/loading/
  error states + microcopy.
- `references/motion.md` — durations/easing tokens, spring vs tween, compositor-
  only properties, `prefers-reduced-motion`.
- `references/performance.md` — Core Web Vitals targets, JS/CSS/font/image
  budgets, code-splitting, resource hints, CLS & font rules, skeleton thresholds.
- `references/pwa-and-a11y.md` — manifest/icons/splash/OG, install-prompt timing,
  web-push UX, badging, service-worker caching strategies, iOS-vs-Android, WCAG 2.2
  contrast/target-size/focus/ARIA.

## Anti-"AI-slop" rules (instant tells to avoid)
| Element | AI default (avoid) | Production approach |
|---|---|---|
| Color | purple/indigo gradients | a real palette via semantic tokens |
| Corners | `rounded-2xl` everywhere | one consistent radius scale |
| Spacing | oversized uniform padding; arbitrary `13px` | defined 4/8px scale |
| Shadows | heavily layered | subtle, tier-based; lighten surface on dark |
| Type | Inter as the only tell, everything same weight | weight+tracking hierarchy, tabular nums |
| Layout | centered everything + stock card grids | content-first, left-aligned density, hero-led |
| Data | red/green only | red/green + ▲/▼ + tabular alignment |

## Red flags — stop and fix if you see
- A raw hex value in a component (should be a semantic token).
- The accent color used to mean "good/up" (it must be brand/interaction only).
- A percentage/price column that shifts width on refresh (missing tabular-nums).
- `outline: none` with no replacement focus ring.
- Animating `width`/`height`/`top`/`left`/`margin` (use transform/opacity).
- A spinner shown for a sub-300ms load, or a loader that flashes.
- Tap targets under ~44px, or controls jammed against the screen edge (back-swipe).
- `<img>` without width/height (causes layout shift).
- An empty/error state that's a dead end (no recovery action).

## Verification checklist (copy into your response, tick each)
- [ ] Tokens only — no raw hex in components; light/dark via semantic remap.
- [ ] One accent (brand/interaction); green/red reserved for P&L + ▲/▼ glyphs.
- [ ] Text contrast ≥ 4.5:1 (≥3:1 large / UI components); not color-alone.
- [ ] Tabular numerals on all data; numerics right-aligned.
- [ ] Tap targets ≥ 44px, ≥8px spacing; safe-area insets on fixed chrome.
- [ ] Hero summary atop each screen; 8px spacing rhythm; stroke icons.
- [ ] Motion: transform/opacity only, M3 durations, reduced-motion honored.
- [ ] CWV budget: JS <200KB gz; images have width/height; font-display set.
- [ ] Skeletons (>500ms) + empty/loading/error states with recovery actions.
- [ ] PWA: manifest + 192/512 maskable icons + apple-touch/favicons + preloaded
      splash + OG tags; push asked in-context; SW caching strategy chosen.
- [ ] Verified: builds clean; rendered/tested at 320/768/1024px (and a real phone).

## Sources
Linear, Coinbase CDS, TradingView, Robinhood, Bloomberg (visual language);
Material 3 + Apple HIG (motion, sheets, targets); web.dev / Chrome (Core Web
Vitals, fonts, caching, install, badging); WebKit (iOS web push); WCAG 2.2 +
WAI-ARIA APG (accessibility); EightShapes / DTCG (token taxonomy);
Anthropic Agent Skills authoring guide (this skill's structure).
