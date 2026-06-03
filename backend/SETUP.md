# Migo Sniper Pro — Level 2 Cloud Backend Setup
## Storage: GitHub (no database needed, 100% free)

```
TradingView Pine Script
    │  trade closes (WIN/LOSS)
    │  POST /webhook/trade-outcome
    ▼
FastAPI Backend (Railway/Render — free)
    │
    ├── Reads/writes weights.json in your GitHub repo  ← persistent learning
    ├── Appends trade to trade_history.json
    ├── Every 15 min: fetches news → scores with Claude → updates news_cache.json
    └── Sends BUY/SELL signals to your Telegram channel
```

### Data files auto-created in your repo (branch: `data`)
```
data/weights.json        ← adaptive KNN weights (survives forever)
data/trade_history.json  ← every trade outcome ever recorded
data/news_cache.json     ← recent news sentiment scores
data/signals.json        ← generated signal log
```

---

## Step 1 — Create GitHub Personal Access Token

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
2. Click **Generate new token (classic)**
3. Name: `migo-sniper-backend`
4. Expiration: No expiration (or 1 year)
5. Scopes: check only **`repo`** (full repo access)
6. Click **Generate token** → copy it → `GITHUB_TOKEN`

---

## Step 2 — Create the `data` Branch

In your repo (migo1907/blank-app), create a branch called `data`:
```bash
git checkout -b data
git push origin data
```
Or on GitHub.com: click the branch dropdown → type `data` → Create branch.

---

## Step 3 — Get API Keys

| Service | URL | Free Tier |
|---------|-----|-----------|
| NewsAPI | newsapi.org/register | 100 req/day |
| Anthropic | console.anthropic.com | ~$0.72/month (haiku) |
| Telegram | @BotFather on Telegram | Free |

### Create Telegram Bot
1. Message **@BotFather** → `/newbot` → follow steps
2. Copy token → `TELEGRAM_BOT_TOKEN`
3. Create a Telegram channel, add your bot as admin
4. Get chat ID: visit `https://api.telegram.org/bot<TOKEN>/getUpdates` after sending one message
5. Copy `chat.id` → `TELEGRAM_CHAT_ID`

---

## Step 4 — Deploy Backend

### Option A: Railway (recommended)
1. Go to **railway.app** → New Project → Deploy from GitHub repo
2. Set root directory to `backend/`
3. Add all environment variables from `.env.example`
4. Railway gives you: `https://your-app.up.railway.app`

### Option B: Local + ngrok (for testing)
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# edit .env with your real keys
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# in another terminal:
ngrok http 8000
```

---

## Step 5 — Pine Script Setup

1. Open `migo_sniper_ml_webhook.pine` in TradingView Pine Editor
2. Add to chart on **XAUUSD 5m**
3. In the **☁️ Cloud Backend** input group, set **Webhook Secret** to your `WEBHOOK_SECRET`

---

## Step 6 — TradingView Alert

1. TradingView → **Alerts** → **Create Alert**
2. Condition: **Migo Sniper Pro [ML + Adaptive + Cloud]** → *Any alert() function call*
3. Enable **Webhook URL** → paste: `https://your-app.up.railway.app/webhook/trade-outcome`
4. Click **Create**

That's it. Every trade close fires the webhook → Python updates `weights.json` in GitHub → weights persist across all sessions forever.

---

## Step 7 — Verify It Works

```bash
curl -X POST https://your-app.up.railway.app/webhook/trade-outcome \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "your_secret",
    "trade_id": "XAUUSD_test_1",
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

Then check your repo — `data/weights.json` should appear with updated weights.

Check dashboard:
```
GET https://your-app.up.railway.app/dashboard?secret=your_secret
```

---

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/webhook/trade-outcome` | POST | Receive trade result from TradingView |
| `/weights?secret=...` | GET | View current adaptive weights |
| `/signal/now?secret=...` | GET | Trigger immediate signal cycle |
| `/dashboard?secret=...` | GET | Full system status |

---

## Cost Summary

| Service | Cost |
|---------|------|
| GitHub storage | **Free** |
| Railway hosting | **Free** (500h/month) |
| NewsAPI | **Free** (100 req/day) |
| Claude haiku sentiment | ~**$0.72/month** |
| Telegram | **Free** |
| **Total** | **~$0.72/month** |
