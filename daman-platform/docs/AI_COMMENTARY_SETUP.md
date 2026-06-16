# AI Market Commentary — Setup (Claude / Hermes)

The **AI Strategist (Hermes)** page is powered by Claude (`claude-opus-4-8`) running
inside a Supabase Edge Function, so the Anthropic API key never reaches the browser.

It works in **demo mode out of the box** (clearly-labelled sample output). To switch
it to live Claude analysis, do the two steps below.

## What you get
- **Market Wrap-Up** — a fundamentals-and-technicals-loaded session recap with
  swing-trade and day-trade ideas, plus an audio narration (browser text-to-speech).
- **Hermes Portfolio Analysis** — fundamental + technical review of the holdings
  saved on the Portfolio page, with diversification, risk, and suggestions.
- **Daily commentary subscription** — email opt-in (stored in Supabase).

## 1. Get an Anthropic API key
Create a key at <https://console.anthropic.com>. (Billing must be enabled.)

## 2. Set it as a Supabase function secret
The key is read server-side via `Deno.env.get("ANTHROPIC_API_KEY")` — it is **not**
a `VITE_` variable and must never be committed.

```bash
# With the Supabase CLI, from the project root:
supabase secrets set ANTHROPIC_API_KEY=sk-ant-...

# Deploy the function:
supabase functions deploy ai-market-commentary
```

Or set it in the Supabase dashboard: **Project → Edge Functions → Manage secrets**.

## 3. (Optional) Create the subscribers table
Apply the migration so daily-commentary sign-ups persist server-side:

```bash
supabase db push   # applies supabase/migrations/20260616120000_create_commentary_subscribers.sql
```

Without it, subscriptions still save on the user's device.

## How it works
```
Browser (AIStrategist page)
  └─ POST /functions/v1/ai-market-commentary  { mode, marketData, holdings }
        └─ Edge Function (Deno)  ── Claude Messages API (structured JSON output)
              └─ returns sectioned commentary  →  rendered + narrated in the UI
```

- **Model:** `claude-opus-4-8` with adaptive thinking and structured outputs.
- **Cost control:** `effort: "medium"`; the function caps `max_tokens` at 8000.
- **Safety:** every response includes a not-financial-advice disclaimer; the prompt
  is balanced and risk-aware, and trade ideas always include risk management.
- **Audio:** generated client-side from the model's `audio_script` via the Web Speech API.

## Email delivery (subscriptions) — now included
A scheduled sender is built in: `supabase/functions/send-daily-commentary`.
It reads active `commentary_subscribers`, generates today's wrap-up, and emails it
via **Resend**.

**Enable it:**
1. Create a Resend account + API key (https://resend.com), verify a sending domain.
2. Set function secrets:
   ```bash
   supabase secrets set DAILY_EMAIL_SECRET=<your-secret> RESEND_API_KEY=<key> RESEND_FROM="Hermes <hermes@yourdomain.com>"
   supabase functions deploy send-daily-commentary
   ```
3. Schedule it. The repo ships `.github/workflows/daily-commentary.yml` (12:00 UTC
   weekdays). Add repo secrets `SUPABASE_FUNCTIONS_URL` (`https://<project>.supabase.co/functions/v1`)
   and `DAILY_EMAIL_SECRET`. (Or use Supabase scheduled functions / pg_cron.)
4. Test now: `curl "<functions-url>/send-daily-commentary?secret=<your-secret>"`.

## Files
| File | Role |
|------|------|
| `supabase/functions/ai-market-commentary/index.ts` | Claude call + structured schemas |
| `supabase/migrations/2026..._create_commentary_subscribers.sql` | Subscribers table |
| `src/services/aiCommentaryService.ts` | Frontend client + demo fallback + types |
| `src/services/commentarySubscriptionService.ts` | Subscription persistence |
| `src/hooks/useSpeech.ts` | Text-to-speech narration |
| `src/pages/AIStrategist.tsx` | The page (wrap-up + Hermes tabs) |
