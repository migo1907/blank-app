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

## Email delivery (subscriptions)
Storing subscribers is included; **sending** the daily email is not — wire the
`commentary_subscribers` table to your email provider (e.g. a scheduled Edge Function
that calls the wrap-up function and sends via Resend/SendGrid). This is intentionally
left to your infrastructure choice.

## Files
| File | Role |
|------|------|
| `supabase/functions/ai-market-commentary/index.ts` | Claude call + structured schemas |
| `supabase/migrations/2026..._create_commentary_subscribers.sql` | Subscribers table |
| `src/services/aiCommentaryService.ts` | Frontend client + demo fallback + types |
| `src/services/commentarySubscriptionService.ts` | Subscription persistence |
| `src/hooks/useSpeech.ts` | Text-to-speech narration |
| `src/pages/AIStrategist.tsx` | The page (wrap-up + Hermes tabs) |
