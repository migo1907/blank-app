# Performance & Core Web Vitals

Contents: CWV targets · Budgets · Code-splitting · Resource hints · Images · Fonts ·
Skeleton thresholds · Layout shift.

## Core Web Vitals targets (assessed at 75th percentile; pass = ≥75% of views "good")
| Metric | Good | Needs work | Poor |
|---|---|---|---|
| **LCP** (Largest Contentful Paint) | ≤ 2.5s | 2.5–4.0s | > 4.0s |
| **INP** (Interaction to Next Paint) | ≤ 200ms | 200–500ms | > 500ms |
| **CLS** (Cumulative Layout Shift) | ≤ 0.1 | 0.1–0.25 | > 0.25 |

INP replaced FID (March 2024) and measures the worst of *all* interactions. Long
tasks > **50ms** are the usual INP culprits.

## Budgets (mid-range Android / slow 4G)
- **JS < 200KB gzipped** initial load (<100KB excellent); **CSS < 50KB gz**;
  **fonts < 100KB** total; **above-the-fold image < 200KB**.
- Time-to-Interactive < **3.5s on 4G**; Lighthouse Performance ≥ **90**; API p95 < **200ms**.
- ~**1ms JS parse per KB** on mobile (200KB ≈ ~200ms parse). Enforce in CI with
  `size-limit` / `bundlesize`.
- Cache static fingerprinted assets **1 year immutable**; HTML/API short TTL.

## Code-splitting (improves LCP + INP)
- Route-based splitting with `React.lazy()` + `<Suspense>` + dynamic `import()`
  (Vite auto-splits dynamic imports into chunks). Ship only the current route's JS;
  lazy-load below-the-fold and non-critical routes. Less main-thread work → better INP.

## Resource hints
- `<link rel="preconnect">` for critical third-party origins (fonts/API/CDN) — early TCP+TLS.
- `<link rel="preload">` for the **LCP image** and the **first-paint font**.
- `prefetch` likely-next-route chunks/data at idle.

## Images (prevent CLS, speed LCP)
- **Always set explicit `width` + `height`** on `<img>` (browser reserves space
  from aspect-ratio → kills image CLS). For fluid images use CSS `aspect-ratio`.
- Responsive `srcset` + `sizes`; every candidate shares the **same aspect ratio**.
- Reserve space for ALL late-arriving content (ads, embeds, banners), not just images.

## Fonts (prevent CLS + FOIT)
- **`font-display: swap`** for body (shows fallback, swaps in — avoids invisible text).
- **`font-display: optional`** is most layout-stable (≤100ms block, else stays on
  fallback → zero font-swap CLS) — use for perf-critical text.
- **Preload** the first-paint/LCP font: `<link rel="preload" as="font" type="font/woff2" crossorigin>`.
- Kill swap-CLS with `size-adjust` (+ `ascent/descent/line-gap-override`) on a
  fallback `@font-face` to metric-match the web font. Self-host woff2.

## Loading indicators (NN/g response-time model)
- **< 1s:** show **no** indicator (a flashing loader feels slower).
- **>~500ms structured load:** **skeleton screens** (set structure; ~9–20% lower
  bounce; Facebook measured ~300ms faster *perceived* load vs spinner).
- **1–10s indeterminate, single small module:** a spinner is acceptable.
- **> 10s / determinate task (upload/convert):** a **percent-done progress bar**, not a skeleton.
- Pair with optimistic UI / instant tap feedback to keep perceived INP high.

## Layout shift (target CLS = 0)
- Dimensions/aspect-ratio on images, video, iframes, embeds, ads.
- Never insert content **above** existing content after load (banners/cookie bars) —
  reserve space or overlay.
- Animate with `transform` (no reflow); metric-matched fallback fonts so swaps don't reflow.
