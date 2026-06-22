# Design Tokens & Theming

Contents: Token tiers · Color (dark + light) · Spacing · Radius · Type scale ·
Elevation (dark) · State layers · Rules.

## Token tiers (3-tier consensus — DTCG / Material / EightShapes)
- **Primitive / global** — raw context-free values, named by *what they are*:
  `color.gray.900`, `space.4 = 16px`, `font.size.300`. Never referenced by components.
- **Semantic / alias** — reference primitives, named by *role/intent*:
  `color.text.primary`, `color.bg.surface`, `color.border.subtle`,
  `color.action.primary`, `color.feedback.positive/negative`. **Theming happens
  here** — light/dark swap remaps these pointers.
- **Component** — scope a semantic decision to one component:
  `button.primary.bg`, `card.surface.bg`, `input.border.focus`.
- Components reference **only** semantic/component tokens — **never** raw hex or
  primitives. Dark mode is a role *remap*, not a color inversion.

## Color tokens (drop-in CSS variables)

Define once on `:root` (dark default); override on `:root[data-theme="light"]`.
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

**Color-blind-safe categorical palette** (when you need >2 series — Okabe-Ito,
the scientific standard, distinguishable under protanopia/deuteranopia/tritanopia):
Orange `#E69F00`, Sky Blue `#56B4E9`, Bluish Green `#009E73`, Yellow `#F0E442`,
Blue `#0072B2`, Vermillion `#D55E00`, Reddish Purple `#CC79A7`, Black `#000000`.
For >8 categories you MUST add shape/pattern — color alone fails. Avoid
confusable pairs: red↔green, green↔brown, blue↔purple, yellow↔light-green.

## Spacing (8px grid + 4px sub-grid)
- **8px base grid** is the industry standard (Material, Carbon): all spacing =
  multiples of 8. Use a **4px sub-grid** for tight internal spacing (button
  padding, icon+label gap, chips).
- Scale (px): `0, 2, 4, 8, 12, 16, 24, 32, 40, 48, 64`. No arbitrary `13px`/`2.3rem`.

## Radius
- One consistent scale: `--r-sm:6` (chips/badges), `--r-md:10` (cards/inputs),
  `--r-lg:14` (sheets/large cards), `--r-pill:999` (pills). Don't round everything
  to the same big radius (an AI tell).

## Type scale (modular, ratio 1.25 "major third")
- Base **16px** body (mobile min — prevents iOS input zoom). 16 × 1.25 →
  ≈ 12.8, 16, 20, 25, 31.25, 39, 48.8 → round to grid: **12/13, 16, 20, 25, 31, 39, 49**.
- Hierarchy by **weight + tracking + tier**: eyebrow labels 10–12px UPPERCASE
  +.08–.1em tracking in `--text-mut`; values bold in `--text-hi`. Never bold a
  label and its value the same weight.
- Prices/percentages: `font-variant-numeric: tabular-nums` (+ slashed-zero);
  mono font for dense numeric columns so `$1,234.56` never misreads.

## Elevation on dark (lighten the surface, not shadows)
- Shadows are weak/invisible on dark → express elevation by compositing a
  semi-transparent **white overlay** on the base; higher = more opaque = lighter.
- Material 2 reference: base surface `#121212`; overlay opacity ramps **0% (0dp)
  → 16% (24dp)**, e.g. **1dp ≈ 5%**, **8dp ≈ 12%**, **24dp = 16%**.
- Material 3: tonal surfaces (`surface`, `surfaceContainerLowest…Highest`) instead
  of additive overlays. Either way: tiered `bg < surface < surface-raised < overlay`
  by stepped lightness + hairline borders, not heavy drop shadows.
- On-surface text emphasis (Material 2, dark): high **87%**, medium **60%**,
  disabled **38%**.

## State layers (Material 3 — translucent overlay of the content/`on-` color)
- **Hover 8% · Focus 10% · Pressed 10% · Dragged 16%** (enabled = 0%).
- States are **not additive** — the highest-priority single state applies.
- On dark, the layer is white-based (lightens on interaction).

## Rules
- Theme switch remaps semantic tokens only; component code unchanged.
- Avoid pure-black bg / pure-white text (halation) — near-black + slightly-dimmed.
- Borders that convey structure need ≥3:1 contrast (WCAG 1.4.11); purely
  decorative hairlines can be lower.
