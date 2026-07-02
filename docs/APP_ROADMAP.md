# Sniper Signals — Product Roadmap to Store-Ready Paid App

**Product:** Sniper Signals — a trading-intelligence PWA. Signals, screeners, macro/regime context, news sentiment, and AI commentary.
**Not a brokerage. No order execution. Ever.** All output is informational — "not investment advice" is a permanent product constraint, not a footer.

**Document status:** v1.0 · 2026-07-02 · Owner-reviewed before any phase starts.

---

## 0. Where we are today

React+Vite PWA served from FastAPI on Railway. Passcode gate (shared secret), dark/light theme, web push, breaking-news flash bar, ticker tape.

| Area | Current state |
|---|---|
| Signals | Intraday ML signals (26-feature KNN+RF+GBM+LightGBM ensemble, 9 pools), Swing top-10 screener, SPX 0-1DTE options paper trades |
| Markets | Overview quotes+movers, Pulse & Regime (HMM), AI Wrap-Up with radio TTS |
| Calendar | Economic (Finnhub + Forex Factory) + earnings |
| Portfolio | Holdings / watchlist / research / compare (localStorage only) |
| News | Sentiment-scored feed (Finnhub + RSS) |
| Infra | TradingView webhooks → FastAPI, HMM regime, macro intel (FRED/COT/GLD/VIX), Telegram + web push |

**Structural gaps vs. a store-ready paid product:** shared passcode instead of accounts; all user state in localStorage; single-source data (yfinance-heavy) with no licensing for commercial redistribution; no billing; no store packaging; no legal surface (privacy policy, ToS, disclaimers); English only.

### Competitive bar (what paid trader-intelligence apps ship)
From Benzinga Pro / TradingView / Webull / CNBC / Bloomberg / MarketWatch / IBKR mobile:
- **Table stakes:** real-time or clearly-labeled delayed quotes, watchlists with alerts, interactive charts, economic + earnings calendars, movers (incl. pre-market/after-hours), news with sentiment, screeners.
- **Differentiators we can match:** audio squawk (we have TTS wrap-up), signals scanner (our core), regime/macro dashboard (rare elsewhere), AI commentary.
- **Differentiators we lack:** heatmaps, social sentiment, per-user price/signal alerts, "stocks to watch" editorial list, multi-symbol interactive charting.
- Benzinga Pro anchors pricing: $27/mo basic (delayed quotes) → $197/mo with real-time. TradingView: $12.95–$56.49/mo. **Lesson: a sub-$30 tier with delayed/EOD data is a legitimate commercial product — real-time is the expensive upgrade, not the baseline.**

---

## Phase 1 — Reliability & Polish (foundation for everything)

**Goal:** the app never shows a blank panel, stale data is labeled, and copy reads like a professional desk. **Duration guide: 3–4 weeks.**

| # | Item | Effort | Notes |
|---|---|---|---|
| 1.1 | Data-source redundancy layer | **M** | Provider abstraction in backend (`quote_provider.py`): ordered chain per data type (e.g., Tradier → Polygon → yfinance → Stooq) with health scoring, circuit breakers, and per-source staleness timestamps. Every API response carries `source` + `as_of`. |
| 1.2 | Staleness UI contract | **S** | Every card shows relative freshness ("2m ago"); >5 min stale → amber badge; source down → last-good value greyed with "delayed" chip, never a spinner forever. |
| 1.3 | Per-tab pull-to-refresh + refresh buttons | **S** | Manual refresh per tab (touch pull + button for desktop). Debounced server-side (min 10s) to protect rate limits. |
| 1.4 | Professional AI commentary v2 | **M** | Upgrade Haiku prompts: include S/R levels (existing pivot pipeline + 20/50/200MA reversion distances), event-driven scenarios ("if CPI hot → watch S1 $x,xxx"), regime context. Same "desk's own read" voice, never names indicators/models. Applies to Markets commentary + Wrap-Up. |
| 1.5 | i18n framework, EN + AR first | **M** | `react-i18next` + ICU messages; RTL layout audit (Tailwind logical properties / `dir="rtl"`); Arabic number/date formatting; AI commentary generated per-locale (prompt param). All new strings go through i18n from day one. |
| 1.6 | Error budgets + observability | **S** | Define SLOs: quotes fresh ≤60s during RTH 99%, signal delivery ≤30s from webhook 99.5%, app shell load <2.5s p75. Add `/metrics` endpoint + simple uptime dashboard; Railway restart events logged. |
| 1.7 | PWA hygiene pass | **S** | Lighthouse PWA ≥90, offline shell with cached last state, proper 512px maskable icons, splash screens — prerequisites for TWA (Phase 4). |

**Dependencies:** none — start immediately. 1.1/1.2 unblock everything visual later.
**Definition of done:** kill any single upstream source in staging and every tab still renders labeled last-good data; full app usable in Arabic RTL without layout breakage; SLO dashboard live for 2 consecutive weeks within budget; Lighthouse PWA ≥90.

---

## Phase 2 — Trader-Grade Content (the reason to pay)

**Goal:** match the Benzinga/TradingView content checklist where it's cheap, and lean into our unique signal/regime edge. **Duration guide: 4–6 weeks.**

| # | Item | Effort | Notes |
|---|---|---|---|
| 2.1 | Market sentiment dashboard | **S–M** | New "Sentiment" panel on Pulse: CNN Fear & Greed (already integrated backend-side), CBOE put/call (already `cboe_data.py`), VIX term structure (have it), plus breadth (advancers/decliners, % above 50MA — computable from existing watchlist universe). Single composite gauge + history sparkline. |
| 2.2 | Social sentiment | **M** | StockTwits public API (message volume + bull/bear ratio per symbol) + Reddit mention counts (r/stocks, r/wallstreetbets via public JSON, cached hourly, honest rate-limit handling). Per-ticker "social heat" score on Research + Signals; trending-mentions widget. Egress allowlist additions required. |
| 2.3 | "Stocks to Watch" daily list | **S** | Auto-generated at 08:30 ET from what we already compute: gap >2% vs prev close, earnings today/tomorrow, unusual pre-market volume, swing-screener top movers, high-impact events. 5–10 names with one-line AI reason each. Push-notified. |
| 2.4 | Interactive charts | **M** | `lightweight-charts` (TradingView's OSS lib, Apache-2.0 — safe to ship in a paid app; the embedded TradingView *widget* has commercial-use restrictions and phones home — avoid inside store builds). Candles + volume + our pivot/S/R overlays + signal entry/TP/SL markers on chart. Daily bars from licensed source (see Risks). |
| 2.5 | Heatmaps | **M** | S&P sector heatmap (treemap by market-cap weight, colored by %change) from existing quote universe + XL* sector ETFs; second view: our 9 signal pools colored by rolling win-rate/PF (unique to us). |
| 2.6 | Pre-market / after-hours movers | **S** | Extend Movers with session tagging; pre/post prices from provider chain (Tradier supports pre/post; label clearly when unavailable). |
| 2.7 | Signal quality surfacing | **S** | Per-pool honest stats page: OOS accuracy, PF, sample size, conformal certainty — from the Strategy Lab data we already persist. This is the trust feature paid conversion depends on. |

**Dependencies:** 1.1 (provider layer) for 2.4/2.6; 1.5 (i18n) for all new strings.
**Definition of done:** a trader can, inside the app, answer "what's the market mood, what's moving, what should I watch today, and why should I trust these signals" without opening another app; charts render 1y daily + intraday for any watchlist symbol in <1.5s p75.

---

## Phase 3 — Accounts & Monetization

**Goal:** real users, server-side state, paid tiers. This is the hard prerequisite for stores (both stores require real auth + account deletion for account-based apps). **Duration guide: 5–7 weeks.**

| # | Item | Effort | Notes |
|---|---|---|---|
| 3.1 | Real authentication | **L** | Replace shared passcode. Recommended: managed auth (Supabase Auth or Firebase Auth) — email+password, magic link, Google sign-in, **Sign in with Apple (mandatory on iOS if any third-party login is offered)**. JWT verified by FastAPI middleware; passcode retired after migration window. |
| 3.2 | User profiles & server-side state | **M** | Postgres (Railway addon or Supabase): profiles, preferences (theme, locale, notification prefs), watchlists, portfolio holdings. Migration path: on first login, import localStorage state → server. Push subscriptions keyed per-user. |
| 3.3 | Account deletion + data export | **S** | In-app "Delete account" (hard requirement: Apple 5.1.1(v) since 2022; Google Play requires in-app + web deletion URL in Data safety form). Deletes profile, watchlists, push subs; confirms subscription cancellation path. |
| 3.4 | Subscription tiers | **M** | **Free:** delayed quotes, EOD movers, 1 watchlist (10 symbols), daily wrap-up, calendar. **Pro (~$15–25/mo, $149–199/yr):** all signal tabs, real-time/faster data (subject to licensing — see Risks), sentiment + social dashboards, unlimited watchlists, push signal alerts, AI commentary, options paper feed. Gate server-side by entitlement claim, never client-only. |
| 3.5 | Billing: RevenueCat as entitlement backbone | **M–L** | RevenueCat unifies StoreKit (iOS IAP), Google Play Billing, and Stripe/Web Billing into one entitlement check (`CustomerInfo`). Web: Stripe via RevenueCat Web Billing. iOS: **must** use IAP for in-app digital subscription purchase (guideline 3.1.1; US external-link entitlement exists but adds review friction — defer). Android TWA: Play Billing via Digital Goods API + Payment Request API (Billing Library 7+ required since Aug 2025). Backend validates entitlement on every premium endpoint. |
| 3.6 | Paywall + upgrade UX | **S** | Locked-tab previews (blurred content + value copy), trial (7-day, store-native), restore purchases, manage-subscription deep links to store. |
| 3.7 | Legal surface | **S** | Privacy policy, Terms of Service, prominent "informational only — not investment advice; past performance does not guarantee future results" disclaimer at onboarding + on every signals surface. Public URLs (required by both stores). |

**Dependencies:** Phase 1 complete (don't sell an unreliable product). 3.1 → 3.2 → 3.3; 3.5 depends on 3.1/3.4.
**Definition of done:** a stranger can sign up, subscribe on web via Stripe, see Pro content on the PWA, delete their account, and every premium API endpoint returns 403 without a valid entitlement; billing state survives cross-device login.

---

## Phase 4 — Store Packaging & Compliance

**Goal:** live listings on Google Play and the App Store. **Duration guide: 4–6 weeks, plus review iteration buffer (plan 2 rejection cycles on iOS).**

| # | Item | Effort | Notes |
|---|---|---|---|
| 4.1 | Google Play via TWA (Bubblewrap) | **M** | Bubblewrap generates the TWA project + AAB from our manifest; `assetlinks.json` served at `/.well-known/` for domain verification (removes browser chrome); $25 one-time dev account; Play Billing wired per 3.5. Closed-testing track first. Note Play's 12-tester/14-day requirement for new personal dev accounts — use an org account. |
| 4.2 | iOS via Capacitor | **L** | Capacitor shell with **bundled** web assets (remote-URL wrappers get rejected as "web clippings", guideline 4.2.2). Add genuinely native touches to clear 4.2 minimum-functionality: native push (APNs replaces web push on iOS), haptics on signal alerts, offline last-state, native share sheet, biometric app lock. Apple dev account $99/yr. |
| 4.3 | Push notification unification | **M** | Abstraction over web push (PWA/TWA) and APNs/FCM (Capacitor); per-user routing from 3.2. Signal alerts, breaking news, stocks-to-watch. |
| 4.4 | Financial-app review compliance | **M** | We are an information/analysis app, **not** trading/money-management (which Apple restricts to licensed financial institutions) — position the listing accordingly: "market intelligence & analytics", no language implying we execute trades or manage money. Disclaimers in-app + in store description. Age rating per store questionnaires. Demo account + reviewer notes for App Review (they must see Pro content). |
| 4.5 | Data safety / privacy labels | **S** | Apple privacy nutrition labels + Google Data safety form; both must match actual telemetry. Account deletion URL published (3.3). |
| 4.6 | Store assets | **S** | Name/subtitle/keywords, screenshots (6.7"/6.5"/iPad if targeted; Play phone+tablet), feature graphic, preview video optional. Localized EN + AR listings (leverage 1.5). |
| 4.7 | Crash reporting & analytics | **S** | Sentry (web + native shells) for crashes; privacy-respecting product analytics (PostHog/self-hosted or Firebase) — funnel: install → signup → trial → paid. Disclosed in privacy labels. |

**Dependencies:** all of Phase 3 (auth, deletion, billing, legal) — stores will reject without them. 1.7 (PWA hygiene) for 4.1.
**Definition of done:** approved listings live in both stores; a purchase made on iOS unlocks Pro on web and Android (RevenueCat entitlement sync); crash-free sessions ≥99.5% over first two release weeks; review-compliance checklist archived per release.

---

## Phase 5 — Scale & Differentiation

**Goal:** retention and organic growth after launch. **Duration guide: ongoing, first pass 6–8 weeks.**

| # | Item | Effort | Notes |
|---|---|---|---|
| 5.1 | Per-user watchlist alerts | **M** | Price crosses, % moves, RSI/MA triggers, "signal fired on my symbol", earnings reminders — user-defined, server-evaluated on existing refresh cycles, pushed per 4.3. The single stickiest feature in this category. |
| 5.2 | AI portfolio review | **M** | Weekly Haiku-generated review of user holdings: concentration, sector tilt vs regime, correlation to open signals, upcoming earnings/events exposure. Pro-only. Hard disclaimer framing; never "buy/sell" imperatives. |
| 5.3 | Multi-language expansion | **M** | Post EN/AR: ES, DE, HI by market signal from analytics. AI content per-locale; store listings localized. |
| 5.4 | Referral program | **S–M** | Give-a-month/get-a-month via RevenueCat offer codes + Stripe coupons; deep links. |
| 5.5 | Community | **L** | Start minimal: public read-only "signal room" feed + reactions; defer full chat (moderation cost, store UGC rules — need reporting/blocking to comply). Alternative: keep community on Telegram/Discord, deep-linked. |
| 5.6 | Signal transparency reports | **S** | Monthly public performance report (auto-generated from Strategy Lab). Marketing asset + trust moat; competitors rarely publish honest OOS numbers. |

**Dependencies:** Phase 3 (users) for all; Phase 4 (push infra) for 5.1.
**Definition of done (first pass):** ≥30% of Pro users have ≥1 custom alert; D30 retention measurably above pre-alerts baseline; referral attribution wired into analytics.

---

## Quick Wins — Next Sprint (all S, no dependencies)

1. **Per-tab refresh buttons** (1.3) — most-requested polish, hours of work.
2. **Staleness badges** (1.2) — trust win, mostly frontend.
3. **Stocks to Watch daily list** (2.3) — assembled from data we already compute.
4. **Sentiment panel v0** (2.1) — Fear&Greed + CBOE P/C + VIX term structure are already in the backend; just surface them together.
5. **Pool honesty stats page** (2.7) — Strategy Lab data → one new tab section.
6. **Disclaimer + privacy policy pages** (3.7) — needed eventually regardless; do the writing now.
7. **Lighthouse/PWA hygiene audit** (1.7) — cheap now, blocking later.

---

## Risks & Mitigations

### R1 — Market-data licensing (**#1 commercial blocker — must resolve before charging money**)
- **The problem:** displaying real-time (and even delayed) exchange quotes in a public, paid app is *redistribution* — it requires vendor **and** per-exchange display licenses. Exchange fees are vendor-agnostic and real (e.g., Nasdaq professional/internal-distribution starts around $2k/mo; OPRA for options is its own fee schedule). **yfinance and scraped sources (Finviz, Yahoo, Google) are NOT licensable for commercial redistribution — shipping them in a paid product is a ToS violation and a legal liability.** This is independent of how good our ML is.
- **Options, in order of pragmatism:**
  1. **Launch tier on EOD + 15-min-delayed data** with a licensed API that permits commercial display of delayed/EOD (delayed data is dramatically cheaper to license; many exchanges free or near-free for delayed display). Benzinga's $27 basic tier proves the model.
  2. **Polygon.io** — Advanced $199/mo (individual); **commercial-use redistribution requires Business tier (~$1,999/mo)** — viable only past ~150–200 Pro subs. We already have `polygon_data.py` integration.
  3. **Twelve Data** — commercial/external-use licensing on Business plans; broader multi-asset (forex/gold spot matters for us); typically cheaper entry than Polygon Business — get a written quote for "display in paid consumer app".
  4. **databento** — transparent licensing docs, strong for derived/analytics use; evaluate for the signals backend (non-display use) vs display use separately.
  5. **Derived-data angle:** our *signals, scores, and levels* are derived analytics, not quote redistribution — a genuinely defensible free/low-cost tier can lead with signals + delayed context while quotes upgrade sits behind licensed real-time.
- **Action now:** inventory every user-visible number by source; get written commercial quotes from Polygon, Twelve Data, databento; pick a "delayed-first" launch posture. **Gate:** no paid launch until every displayed datapoint has a licensed source or is internally derived.

### R2 — Apple review risk (guidelines 4.2 / 3.1.1 / 3.1.5)
Wrapped-PWA rejection ("repackaged website") is the classic failure. Mitigate: bundle assets locally, add native capabilities (4.2), use IAP for subscriptions (3.1.1), position as information/analytics not trading (3.1.5), demo account + detailed reviewer notes, budget 2+ review cycles.

### R3 — Store fees compress margin
15–30% App Store/Play cut vs ~3% Stripe. Mitigate: push web signup in marketing (allowed outside the app), price consistently, treat store subs as CAC.

### R4 — Regulatory perception of "signals"
Signals sold to the public can attract investment-advice scrutiny in some jurisdictions. Mitigate: education/informational framing, prominent disclaimers, no personalized "you should buy" language (5.2 framing rules), no performance guarantees in marketing; get a one-time legal review of copy before paid launch (budget item).

### R5 — Single-developer bus factor & upstream fragility
TradingView webhook + free-API dependence. Mitigate: Phase 1 redundancy, documented runbooks, provider health alarms; Railway restart catch-up logic already exists — extend to all user-facing jobs.

### R6 — AI content cost & quality at scale
Per-locale AI commentary multiplies token spend. Mitigate: cache per (asset, locale, day), Haiku-class models, hard monthly budget alarm.

---

## Sequencing Summary

```
Phase 1 (reliability, i18n)  ──►  Phase 2 (content)  ──►  Phase 3 (auth+billing)  ──►  Phase 4 (stores)  ──►  Phase 5 (scale)
   3–4 wks                        4–6 wks                 5–7 wks                     4–6 wks + review        ongoing
                └── R1 data-licensing decision must land before Phase 3 pricing is final ──┘
```

**Non-negotiable gates:** no paid tier without licensed data (R1); no store submission without auth + deletion + legal (Phase 3); no feature ships unlabeled for staleness (Phase 1 contract).

---

## Appendix — Key external references
- TWA/Bubblewrap + Play Billing: developer.chrome.com (Digital Goods API), chromeos.dev "List your PWA in Google Play", github.com/chromeos/pwa-play-billing
- iOS packaging: Apple App Review Guidelines (4.2 minimum functionality, 3.1.1 IAP, 5.1.1(v) account deletion), Capacitor docs, Capgo iOS IAP review guide
- Billing: RevenueCat docs (Web Billing/Stripe, cross-platform entitlements)
- Data licensing: databento licensing blog series, marketdata.app licensing explainers, polygon.io/pricing, twelvedata.com/pricing-business
- Competitive: Benzinga Pro plan/feature reviews, TradingView plans, Webull app feature set
