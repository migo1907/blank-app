# 🔑 Add Alpaca Keys to Supabase - Quick Guide

## ⚡ Status Check

**Test Result:** `"source":"yahoo"` ❌
**Expected:** `"source":"alpaca"` ✅

**Problem:** Alpaca keys are in local `.env` but NOT in Supabase

---

## ✅ Solution (2 Minutes)

### Step 1: Open Supabase Dashboard

**Direct Link:**
https://supabase.com/dashboard/project/plxlzcpkxjrmtphslmzq/settings/functions

Or navigate manually:
1. Go to https://supabase.com/dashboard
2. Select project: `plxlzcpkxjrmtphslmzq`
3. Click **Settings** (left sidebar)
4. Click **Edge Functions**
5. Scroll to **Function Secrets** section

---

### Step 2: Add Alpaca API Keys

Click **"Add new secret"** button and add these TWO secrets:

#### Secret 1:
```
Name:  ALPACA_API_KEY
Value: PKFZGFHNRYO3EX62J3XYHTVSHQ
```

#### Secret 2:
```
Name:  ALPACA_SECRET_KEY
Value: 218uM7EzVqT3jB2uDQtYRimxsgrLkDML5Q3m5v7tJM6p
```

**Important:**
- Copy the values exactly (no spaces before/after)
- Names must match exactly (case-sensitive)
- Click **Save** after adding each secret

---

### Step 3: Wait for Propagation

Wait **30 seconds** for the changes to take effect across all edge functions.

---

### Step 4: Verify It's Working

Run this command to test:

```bash
curl "https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/fetch-stock-data?symbols=AAPL&mode=return" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBseGx6Y3BreGpybXRwaHNsbXpxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1NjI1MjAsImV4cCI6MjA3NzEzODUyMH0.P048N6dg6VZqvHRcXYt_vntteKqj_ifhsahE5LsLV_I"
```

**Look for:** `"source":"alpaca"` ✅

---

## 🎯 What This Fixes

Once you add these keys, ALL your scanners will use Alpaca:

✅ **QuantFlow Scanner** - Real-time stock quotes from Alpaca
✅ **SPX Options Scanner** - Real-time SPX options from Alpaca (after deploying)
✅ **SPX Options Flow** - Live flow detection with Alpaca data
✅ **Intraday Options Scanner** - Multi-symbol options from Alpaca (after deploying)

---

## 🔍 Why This Happened

**Local Development (.env file):**
```env
ALPACA_API_KEY=PKFZGFHNRYO3EX62J3XYHTVSHQ
ALPACA_SECRET_KEY=218uM7EzVqT3jB2uDQtYRimxsgrLkDML5Q3m5v7tJM6p
```
These work when running locally ✅

**Production (Supabase Edge Functions):**
- Edge functions run on Supabase servers
- They DON'T have access to your local `.env` file
- They need secrets configured in Supabase Dashboard
- Currently: Keys NOT set ❌

---

## 📊 Testing Progress

### Before Adding Keys:
```bash
$ curl "...fetch-stock-data?symbols=AAPL&mode=return"
{"source":"yahoo", ...}  # ❌ Using Yahoo fallback
```

### After Adding Keys:
```bash
$ curl "...fetch-stock-data?symbols=AAPL&mode=return"
{"source":"alpaca", ...}  # ✅ Using Alpaca primary!
```

---

## 🚀 Next Steps After Adding Keys

1. **Test stock quotes** (already deployed):
   ```bash
   curl "https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/fetch-stock-data?symbols=AAPL,MSFT&mode=return" \
     -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBseGx6Y3BreGpybXRwaHNsbXpxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1NjI1MjAsImV4cCI6MjA3NzEzODUyMH0.P048N6dg6VZqvHRcXYt_vntteKqj_ifhsahE5LsLV_I"
   ```
   Expected: `"source":"alpaca"` ✅

2. **Deploy remaining functions** (I can do this):
   - `fetch-options-prices` - SPX & stock options
   - `fetch-intraday-data` - 5-minute bars for QuantFlow

3. **Test in your app**:
   - Open QuantFlow Scanner
   - Watch prices update every 2 seconds
   - Open browser console
   - See: `source: alpaca` in network responses

---

## 💡 Pro Tip: Verify Keys Are Set

After adding keys, you can test if they're available:

```bash
# Test that the function can access the keys
# If Alpaca works, you'll see "source":"alpaca"
# If Alpaca fails, you'll see "source":"yahoo" (fallback)

curl -s "https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/fetch-stock-data?symbols=AAPL&mode=return" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBseGx6Y3BreGpybXRwaHNsbXpxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1NjI1MjAsImV4cCI6MjA3NzEzODUyMH0.P048N6dg6VZqvHRcXYt_vntteKqj_ifhsahE5LsLV_I" \
  | grep -o '"source":"[^"]*"'
```

---

## 🔐 Security Note

These secrets are stored securely in Supabase and are:
- Encrypted at rest
- Only accessible to your edge functions
- Never exposed in client-side code
- Not visible in function logs

---

## ✅ Checklist

- [ ] Open Supabase Dashboard → Settings → Edge Functions
- [ ] Add `ALPACA_API_KEY` secret
- [ ] Add `ALPACA_SECRET_KEY` secret
- [ ] Click Save on both
- [ ] Wait 30 seconds
- [ ] Run test command
- [ ] Verify shows `"source":"alpaca"`
- [ ] Test in your app (scanners should update)

---

## 🎉 Once Complete

**You'll have:**
- ✅ Real-time stock quotes from Alpaca (FREE)
- ✅ Real-time options data from Alpaca (FREE)
- ✅ Intraday bars for technical analysis (FREE)
- ✅ All scanners updating every 2 seconds
- ✅ $0/month cost

**Total setup time:** 2 minutes! 🚀

---

**Status:** Waiting for you to add keys to Supabase Dashboard 🔑

Direct link: https://supabase.com/dashboard/project/plxlzcpkxjrmtphslmzq/settings/functions
