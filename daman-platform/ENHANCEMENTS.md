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

### 🤖 AI Strategist "Hermes" (powered by Claude)
- **Market Wrap-Up** — `claude-opus-4-8` generates a fundamentals-and-technicals-loaded
  session recap (technical levels, fundamental drivers, macro, sector rotation,
  swing-trade and day-trade ideas, risks, what-to-watch).
- **Hermes Portfolio Analysis** — fundamental + technical review of the user's saved
  holdings, with diversification/risk and actionable suggestions.
- **Audio commentary** — browser text-to-speech narration of the AI's `audio_script`.
- **Daily subscription** — email opt-in for daily commentary (Supabase-backed).
- **Ticker Research** — type any symbol for a Claude deep-dive: rating, fundamentals,
  technicals, explicit bull/bear case, catalysts, risks (+ audio).
- **Ask Hermes chat** — streaming (live-typing) conversational assistant, available
  as a tab *and* a global floating button on every page; persists across sessions and
  stays portfolio-aware.
- **Copy / Share** on all AI output (clipboard + native share on mobile).
- Runs server-side in Supabase Edge Functions (`ai-market-commentary`, `ai-chat`) — the
  key never hits the browser — with structured JSON output and a graceful demo fallback.
  **Setup:** `docs/AI_COMMENTARY_SETUP.md`.

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
