# Deploy / Preview the DAMAN Platform

Three ways to see the app, fastest first.

> The app now renders even **without** environment variables (you'll get the UI
> plus demo content). Add the env vars below to enable live data and AI.

---

## Option A — Netlify (shareable URL, recommended)
1. Go to <https://app.netlify.com> → **Add new site → Import an existing project**.
2. Connect GitHub and pick the `migo1907/blank-app` repo, branch `claude/sweet-hopper-6qqg4c`.
3. **Set Base directory to `daman-platform`.** (Build command `npm run build` and
   publish `dist` are already configured in `netlify.toml`.)
4. (Optional) Add environment variables (see below) under **Site settings → Environment**.
5. Deploy. You'll get a `https://<name>.netlify.app` URL.

## Option B — Vercel (shareable URL)
1. Go to <https://vercel.com/new> → import `migo1907/blank-app`.
2. **Set Root Directory to `daman-platform`.** (`vercel.json` handles the rest.)
3. (Optional) Add the environment variables below.
4. Deploy → `https://<name>.vercel.app`.

## Option C — Run locally
```bash
cd daman-platform
npm install
npm run dev      # http://localhost:5173
# or a production preview:
npm run build && npm run preview
```

---

## Environment variables (optional, for live data + AI)
Set these in the host's environment settings (Netlify/Vercel) or in a local `.env`
(copy from `.env.example`). All are client-exposed `VITE_` vars **except** the
Anthropic key, which is a Supabase function secret (see `AI_COMMENTARY_SETUP.md`).

| Var | Enables |
|-----|---------|
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | Live market data, news, scanners |
| `VITE_ALPACA_API_KEY`, `VITE_ALPACA_SECRET_KEY` | Alpaca market data |
| `VITE_GEMINI_API_KEY` | (legacy) market-expectation AI |
| `VITE_POLYGON_API_KEY` | Polygon data (optional) |
| `ANTHROPIC_API_KEY` *(Supabase secret)* | AI Strategist "Hermes" — see `AI_COMMENTARY_SETUP.md` |

Without any of these, the site still loads and showcases the UI with demo content.
