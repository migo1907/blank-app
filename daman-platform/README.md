# DAMAN Securities — Trading Platform

A professional online trading platform with real-time market data, stock
screening, technical analysis, portfolio tracking, watchlists with price
alerts, and global market news.

Built with **Vite · React 18 · TypeScript · Tailwind CSS · Supabase**.

## Quick start
```bash
cp .env.example .env     # add your keys (see .env.example)
npm install
npm run dev              # http://localhost:5173
```

## Scripts
| Command | Description |
|---------|-------------|
| `npm run dev` | Start the dev server |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Preview the production build |
| `npm run lint` | Run ESLint |
| `npm run typecheck` | TypeScript type checking |

## Project structure
```
src/
  pages/          Home, Market Overview, Portfolio, Watchlist, Settings, …
  components/     UI + feature components (scanners, tickers, charts, …)
  services/       Market-data, options, news, Alpaca/Polygon services
  hooks/          Reusable hooks (e.g. useScrollReveal)
  contexts/       Theme context (light/dark)
  lib/            Supabase client
supabase/
  functions/      Edge functions (market data, news, options, webhooks)
  migrations/     Database schema
docs/             Setup guides, integration notes, and historical reports
```

## Environment
Client-side keys live in `.env` (see `.env.example`). Server-side secrets are
configured as Supabase Edge Function secrets — never commit real keys.

## Documentation
- [`ENHANCEMENTS.md`](./ENHANCEMENTS.md) — performance, animation & mobile work
- [`docs/`](./docs) — setup guides (Alpaca, Polygon, Tradier, news, TradingView),
  brand identity, and historical build/audit reports

## Recent enhancements
Route-based code splitting, scroll-reveal animations, skeleton loaders,
animated counters, a live "Markets at a Glance" homepage section, mobile dark-mode
fixes, and accessibility/SEO improvements — all while preserving the original
brand (colors, logo, and footer). See [`ENHANCEMENTS.md`](./ENHANCEMENTS.md).
