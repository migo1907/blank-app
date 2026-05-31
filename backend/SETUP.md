# Migo Sniper Pro — Level 2 Cloud Backend Setup

## What This Does

```
TradingView Pine Script
    │  trade closes (WIN/LOSS)
    │  POST /webhook/trade-outcome  (JSON with features)
    ▼
FastAPI Backend (Railway/Render — free)
    │
    ├── Updates KNN weights in Supabase (persistent cross-session learning)
    ├── Stores trade history in Supabase
    ├── Every 15 min: fetches news → scores sentiment with Claude
    └── Sends signals to your Telegram channel
```

---

## Step 1 — Supabase Setup

1. Go to **supabase.com** → New Project
2. Open **SQL Editor** → New Query
3. Paste the full contents of `supabase_schema.sql` and click **Run**
4. Go to **Settings → API** and copy:
   - `Project URL` → `SUPABASE_URL`
   - `service_role` key (not anon) → `SUPABASE_SERVICE_KEY`

---

## Step 2 — Get API Keys

| Service | URL | Free Tier |
|---------|-----|-----------|
| NewsAPI | newsapi.org/register | 100 req/day |
| Anthropic | console.anthropic.com | pay per use (~$0.72/month) |
| Telegram | Create bot via @BotFather | Free |

### Create Telegram Bot
1. Message **@BotFather** on Telegram → `/newbot`
2. Copy the token → `TELEGRAM_BOT_TOKEN`
3. Create a channel/group, add your bot as admin
4. Get chat ID: send a message then visit `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Copy the `chat.id` field → `TELEGRAM_CHAT_ID`

---

## Step 3 — Deploy Backend

### Option A: Railway (recommended, free tier)
1. Push this repo to GitHub
2. Go to railway.app → New Project → Deploy from GitHub
3. Add environment variables from `.env.example`
4. Railway gives you a public URL like `https://your-app.up.railway.app`

### Option B: Run Locally (for testing)
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# fill in .env with your keys
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

For public access while testing: use `ngrok http 8000` → copy the HTTPS URL

---

## Step 4 — Configure Pine Script

1. Open `migo_sniper_ml_webhook.pine` in TradingView Pine Editor
2. Add to chart on XAUUSD 5m
3. In the **☁️ Cloud Backend** settings group, set:
   - **Webhook Secret**: same as your `WEBHOOK_SECRET` env var

---

## Step 5 — Set Up TradingView Alert

1. In TradingView, click the **Alerts** clock icon → **Create Alert**
2. Condition: **Migo Sniper Pro [ML + Adaptive + Cloud]** → Any alert() function call
3. **Alert actions**: enable **Webhook URL**
4. Paste your backend URL: `https://your-app.up.railway.app/webhook/trade-outcome`
5. Message field: leave as is (Pine's `alert()` call sends the JSON payload)
6. Click **Create**

---

## Step 6 — Verify It Works

Test the webhook manually:
```bash
curl -X POST https://your-app.up.railway.app/webhook/trade-outcome \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "your_secret",
    "trade_id": "XAUUSD_test_123",
    "direction": "LONG",
    "outcome": "WIN",
    "tp_stage": "TP3",
    "entry_price": 2350.00,
    "exit_price": 2366.00,
    "ml_score": 0.72,
    "f1": 0.4, "f2": 0.6, "f3": 0.2, "f4": -0.1,
    "f5": 0.3, "f6": 0.5, "f7": 0.1, "f8": 0.4
  }'
```

Expected response:
```json
{
  "status": "ok",
  "outcome": "WIN",
  "new_weights": {"w1": 1.006, "w2": 1.006, ...},
  "win_rate": 100.0
}
```

Check the dashboard:
```
GET https://your-app.up.railway.app/dashboard?secret=your_secret
```

---

## How Learning Works (Level 2)

| Level 1 (Pine only) | Level 2 (Cloud) |
|--------------------|-----------------|
| Weights reset on chart reload | Weights persist forever in Supabase |
| No news awareness | News sentiment from NewsAPI + Claude |
| 8 features only | 8 features + news bias combined |
| Signal on chart only | Signal pushed to Telegram every 15 min |
| No trade history | Full audit trail in Supabase |

---

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/webhook/trade-outcome` | POST | Receive trade result from TradingView |
| `/weights?secret=...` | GET | View current adaptive weights |
| `/signal/now?secret=...` | GET | Trigger immediate signal cycle |
| `/dashboard?secret=...` | GET | Full system status |
