# 🚀 Tradier Quick Start - 3 Minutes Setup

All your scanners are now configured to use **Tradier API** for professional-grade real-time market data. Follow these 3 simple steps to activate.

---

## Step 1: Get Free API Key (1 minute)

1. Go to: **https://developer.tradier.com/user/sign_up**
2. Sign up (email + password)
3. Verify email
4. Go to: **https://developer.tradier.com/user/settings/api**
5. Click **"Create Access Token"**
6. Copy the token (looks like: `eyJhbGc...`)

---

## Step 2: Update Environment Variables (30 seconds)

Open your `.env` file and update:

```bash
# Replace with your actual token from Step 1
TRADIER_API_TOKEN=paste_your_token_here
TRADIER_API_URL=https://sandbox.tradier.com
```

**For Production** (after testing):
```bash
TRADIER_API_URL=https://api.tradier.com
```

---

## Step 3: Deploy Edge Functions (1 minute)

### Option A: Using Supabase Dashboard (Easiest)

1. Go to **Supabase Dashboard** → **Edge Functions**
2. Click **"Deploy new function"**
3. Upload these 4 files:
   - `supabase/functions/fetch-options-prices/index.ts`
   - `supabase/functions/fetch-stock-data/index.ts`
   - `supabase/functions/fetch-market-data/index.ts`
   - `supabase/functions/fetch-intraday-data/index.ts`

4. Go to **Project Settings → Edge Functions → Environment Variables**
5. Add:
   - `TRADIER_API_TOKEN` = your token from Step 1
   - `TRADIER_API_URL` = `https://sandbox.tradier.com`

### Option B: Using Supabase CLI

```bash
# Deploy all functions
supabase functions deploy fetch-options-prices
supabase functions deploy fetch-stock-data
supabase functions deploy fetch-market-data
supabase functions deploy fetch-intraday-data

# Set environment variables
supabase secrets set TRADIER_API_TOKEN=your_token_here
supabase secrets set TRADIER_API_URL=https://sandbox.tradier.com
```

---

## ✅ Verify It Works

1. Open your app
2. Go to **SPX Options Scanner**
3. Wait 5 seconds
4. Check badges at top:
   - Should show: 🟢 **"Live Prices"** (green)
   - Should show: 🟢 **"Live Feed"** (green with pulse)

5. Open browser console (F12):
   - Should see: `✅ Tradier: Fetched 85 calls, 82 puts for SPX`
   - Should NOT see: Yahoo Finance errors

---

## 🎉 Done!

Your scanners are now using:
- ✅ Real-time market data from Tradier
- ✅ Professional-grade options chains
- ✅ Accurate bid/ask spreads
- ✅ Greeks included (IV, Delta, Gamma, etc.)
- ✅ 99.9% uptime reliability

---

## 📊 What Changed?

### Before (Yahoo Finance)
- Unofficial, can break anytime
- Sometimes delayed data
- No Greeks
- Unreliable uptime

### After (Tradier)
- Official, documented API
- Real-time data (< 1 second)
- Full Greeks included
- 99.9% uptime SLA
- Used by professional traders

---

## 💰 Pricing

**Free Tier (Sandbox):**
- 500 API calls per day
- Perfect for development & testing
- Real-time data (some delays on sandbox)

**Paid Tier ($10/month):**
- Unlimited API calls
- 100% real-time data
- All US markets
- Professional support

**Your Usage:** ~500-1000 calls/day
**Recommendation:** Start with free tier, upgrade if needed

---

## 🐛 Troubleshooting

### Scanner shows "Simulated Prices"

**Fix:**
1. Check `.env` has `TRADIER_API_TOKEN=...`
2. Verify token is valid at https://developer.tradier.com/user/settings/api
3. Redeploy edge functions
4. Add environment variables in Supabase Dashboard

### Console shows "401 Unauthorized"

**Fix:**
- Token is invalid or expired
- Generate new token
- Update `.env` and Supabase environment variables

### No data loading

**Fix:**
- Edge functions not deployed
- Check Supabase Edge Functions logs for errors
- Verify environment variables set in Supabase Dashboard

---

## 📚 Full Documentation

For detailed setup, troubleshooting, and API reference:
→ See **`TRADIER_INTEGRATION_COMPLETE.md`**

---

## 🆘 Need Help?

1. **Tradier Support:** support@tradier.com
2. **API Docs:** https://documentation.tradier.com
3. **Status Page:** https://status.tradier.com

---

**Total Setup Time:** 3 minutes
**Difficulty:** Easy
**Result:** Professional-grade market data ✅

Happy Trading! 🚀📈
