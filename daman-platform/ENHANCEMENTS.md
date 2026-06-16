# Platform Enhancements

Enhancements layered on top of the DAMAN Securities platform.
**Brand untouched:** colors (`daman-blue`/slate), logo, brand name, and footer
are exactly as before — these changes are performance, responsiveness, and polish only.

## Run locally
```bash
cp .env.example .env   # fill in your keys
npm install
npm run dev            # http://localhost:5173
```

## What changed

### ⚡ Performance
- **Route-based code splitting** — all pages are `React.lazy` + `Suspense`.
  Initial JS dropped from ~272 kB to ~13 kB; the heavy Market Overview page
  (197 kB) loads only when visited.

### 🎬 Animations & polish
- **Page transitions** — fade between pages on navigation.
- **Scroll reveal** — `Reveal` + `useScrollReveal` fade/slide content in on scroll.
- **Animated counters** — `AnimatedCounter` counts up stats when scrolled into view.
- **Animated nav underline** on desktop links.
- **Back-to-top** floating button (`BackToTop`).
- **Staggered entrances** on Portfolio rows, Watchlist cards, and Settings panels.

### 💀 Loading states
- **`Skeleton`** — theme-aware shimmer placeholder, used in Market Pulse,
  Portfolio (table), and Watchlist (cards) while data loads.

### 🆕 New section
- **`MarketPulse`** ("Markets at a Glance") on the homepage — skeleton load →
  animated index cards (S&P 500, Nasdaq 100, Dow, Russell 2000) → CTA into the
  full Market Overview.

### 📱 Mobile fixes
- Bottom nav: dark-mode text/background variants (was unreadable on the dark
  bar); active indicator now anchors to the active tab; active-icon scale.
- Theme toggle added to the mobile dropdown menu (was desktop-only).

## Reusable building blocks added
| File | Purpose |
|------|---------|
| `src/hooks/useScrollReveal.ts` | IntersectionObserver visibility hook |
| `src/components/Reveal.tsx` | Fade/slide-in-on-scroll wrapper |
| `src/components/AnimatedCounter.tsx` | Count-up number on view |
| `src/components/Skeleton.tsx` | Shimmer loading placeholder |
| `src/components/BackToTop.tsx` | Floating scroll-to-top button |
| `src/components/MarketPulse.tsx` | Homepage index-snapshot section |

All animations honor `prefers-reduced-motion`.
