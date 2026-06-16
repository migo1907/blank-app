# 🔧 Fix Price Updates - Complete Guide

**Issue:** Prices not updating in scanners
**Solution:** Deploy edge functions + verify data sources

---

## ⚡ Quick Fix (5 Minutes)

### Step 1: Deploy Updated Edge Functions

**Option A: Use the deploy script**
```bash
cd /path/to/your/project
./DEPLOY_FUNCTIONS.sh
```

**Option B: Deploy manually**
```bash
supabase functions deploy fetch-stock-data
supabase functions deploy fetch-options-prices
supabase functions deploy fetch-intraday-data
```

### Step 2: Verify Deployment

**Test stock quotes:**
```bash
curl "https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/fetch-stock-data?symbols=AAPL&mode=return" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBseGx6Y3BreGpybXRwaHNsbXpxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1NjI1MjAsImV4cCI6MjA3NzEzODUyMH0.P048N6dg6VZqvHRcXYt_vntteKqj_ifhsahE5LsLV_I"
```

**Expected response:**
```json
{
  "success": true,
  "source": "alpaca",
  "data": [
    {
      "symbol": "AAPL",
      "price": 277.595,
      "change": 0.695,
      "volume": 45234567
    }
  ]
}
```

**Check source is "alpaca"!** ✅

---

## 🔍 Troubleshooting

### Issue 1: Supabase CLI Not Installed

**Error:** `supabase: command not found`

**Fix:**
```bash
# Install Supabase CLI
npm install -g supabase

# Or with Homebrew (Mac)
brew install supabase/tap/supabase

# Verify installation
supabase --version
```

---

### Issue 2: Not Logged In to Supabase

**Error:** `Failed to get access token`

**Fix:**
```bash
# Login to Supabase
supabase login

# Follow the browser authentication flow
# Copy and paste your access token when prompted
```

---

### Issue 3: Wrong Project Linked

**Error:** `Project not found`

**Fix:**
```bash
# Check current project
supabase projects list

# Link to your project
supabase link --project-ref plxlzcpkxjrmtphslmzq

# Verify link
supabase status
```

---

### Issue 4: Environment Variables Missing

**Error:** `ALPACA_API_KEY not set`

**Fix:**
Go to Supabase Dashboard:
1. Open https://supabase.com/dashboard/project/plxlzcpkxjrmtphslmzq
2. Go to Settings → Edge Functions → Environment Variables
3. Add these variables:

```
ALPACA_API_KEY=PKFZGFHNRYO3EX62J3XYHTVSHQ
ALPACA_SECRET_KEY=218uM7EzVqT3jB2uDQtYRimxsgrLkDML5Q3m5v7tJM6p
VITE_ALPACA_API_KEY=PKFZGFHNRYO3EX62J3XYHTVSHQ
VITE_ALPACA_SECRET_KEY=218uM7EzVqT3jB2uDQtYRimxsgrLkDML5Q3m5v7tJM6p
```

**Important:** Use the secrets manager in Supabase Dashboard, not the .env file for edge functions!

---

### Issue 5: Still Seeing Old Prices

**Error:** Prices not updating after deployment

**Possible causes:**

#### A. Edge Functions Not Deployed
```bash
# Check function logs
supabase functions logs fetch-stock-data --tail

# Look for: "✅ Alpaca: Fetched X stock quotes"
# If you see: "Yahoo: Fetched..." - deployment didn't work
```

#### B. Browser Cache
```javascript
// Open browser console
// Clear cache and hard reload
// Windows/Linux: Ctrl + Shift + R
// Mac: Cmd + Shift + R

// Or clear service worker cache
navigator.serviceWorker.getRegistrations().then(registrations => {
  registrations.forEach(r => r.unregister())
})
```

#### C. Markets Are Closed
```bash
# Check if US markets are open (9:30 AM - 4:00 PM ET)
# Use this test during market hours

# Or test with latest close prices
curl "https://data.alpaca.markets/v2/stocks/AAPL/snapshot" \
  -H "APCA-API-KEY-ID: PKFZGFHNRYO3EX62J3XYHTVSHQ" \
  -H "APCA-API-SECRET-KEY: 218uM7EzVqT3jB2uDQtYRimxsgrLkDML5Q3m5v7tJM6p"

# If this returns data, Alpaca is working!
```

#### D. Component Not Refetching
```javascript
// Open browser dev tools
// Check Network tab
// Filter: fetch-stock-data

// Verify requests are being made
// Check response shows "source": "alpaca"
```

---

## 🧪 Complete Verification Steps

### 1. Test Alpaca API Directly

```bash
# Test stock quote
curl -s "https://data.alpaca.markets/v2/stocks/AAPL/snapshot" \
  -H "APCA-API-KEY-ID: PKFZGFHNRYO3EX62J3XYHTVSHQ" \
  -H "APCA-API-SECRET-KEY: 218uM7EzVqT3jB2uDQtYRimxsgrLkDML5Q3m5v7tJM6p"
```

**Expected:** JSON with `latestTrade.p` showing current price

**If this fails:** Your Alpaca keys are invalid or rate limited

---

### 2. Test Edge Function (Stock Data)

```bash
curl -s "https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/fetch-stock-data?symbols=AAPL&mode=return" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBseGx6Y3BreGpybXRwaHNsbXpxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1NjI1MjAsImV4cCI6MjA3NzEzODUyMH0.P048N6dg6VZqvHRcXYt_vntteKqj_ifhsahE5LsLV_I"
```

**Check response:**
```json
{
  "success": true,
  "source": "alpaca",  // ← Must be "alpaca" not "yahoo"
  "data": [...]
}
```

**If source is "yahoo":** Edge function not deployed or Alpaca failed

---

### 3. Test Edge Function (Options Data)

```bash
curl -s "https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/fetch-options-prices?symbol=SPX" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBseGx6Y3BreGpybXRwaHNsbXpxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1NjI1MjAsImV4cCI6MjA3NzEzODUyMH0.P048N6dg6VZqvHRcXYt_vntteKqj_ifhsahE5LsLV_I"
```

**Check response:**
```json
{
  "success": true,
  "source": "alpaca",  // ← Must be "alpaca"
  "data": {
    "underlying": "SPX",
    "underlyingPrice": 5967.82,
    "calls": [...],
    "puts": [...]
  }
}
```

---

### 4. Test Edge Function (Intraday Bars)

```bash
curl -s "https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/fetch-intraday-data?symbol=AAPL&interval=5m&days=1" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBseGx6Y3BreGpybXRwaHNsbXpxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1NjI1MjAsImV4cCI6MjA3NzEzODUyMH0.P048N6dg6VZqvHRcXYt_vntteKqj_ifhsahE5LsLV_I"
```

**Check response:**
```json
{
  "success": true,
  "source": "alpaca",  // ← Must be "alpaca"
  "dataPoints": 78,
  "data": [
    {
      "timestamp": 1732713600000,
      "open": 277.5,
      "high": 278.0,
      "low": 277.2,
      "close": 277.8,
      "volume": 45678
    }
  ]
}
```

---

### 5. Test in Browser Console

Open your app, then open browser console (F12) and run:

```javascript
// Test stock quotes
const testStock = async () => {
  const url = 'https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/fetch-stock-data?symbols=AAPL,MSFT&mode=return';
  const response = await fetch(url, {
    headers: {
      'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBseGx6Y3BreGpybXRwaHNsbXpxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1NjI1MjAsImV4cCI6MjA3NzEzODUyMH0.P048N6dg6VZqvHRcXYt_vntteKqj_ifhsahE5LsLV_I'
    }
  });
  const data = await response.json();
  console.log('Source:', data.source);  // Should be "alpaca"
  console.log('Data:', data);
  return data;
};

testStock();
```

**Expected output:**
```
Source: alpaca
Data: { success: true, source: "alpaca", count: 2, data: [...] }
```

---

## 📊 Scanner-Specific Checks

### QuantFlow Scanner

**What to verify:**
- [ ] Prices update every 2 seconds
- [ ] Source is Alpaca in console logs
- [ ] RSI values calculate correctly
- [ ] LONG/SHORT/WAIT signals appear

**Check in browser console:**
```javascript
// Look for network requests to:
// fetch-intraday-data?symbol=AAPL&interval=5m

// Response should show:
// { success: true, source: "alpaca", dataPoints: 78 }
```

---

### SPX Options Scanner

**What to verify:**
- [ ] SPX price displays correctly
- [ ] Options chains load (both calls and puts)
- [ ] Bid/Ask/Last prices show
- [ ] Volume and IV display

**Check in browser console:**
```javascript
// Look for network request to:
// fetch-options-prices?symbol=SPX

// Response should show:
// { success: true, source: "alpaca", data: { ... } }
```

---

### SPX Options Flow

**What to verify:**
- [ ] Live SPX price updates
- [ ] Large trades appear in flow table
- [ ] Premiums calculate correctly
- [ ] Bull/Bear classification works

**Uses same endpoint as SPX Options Scanner**

---

### Intraday Options Scanner

**What to verify:**
- [ ] Stock prices load for all symbols
- [ ] Options chains load per symbol
- [ ] Scan results appear
- [ ] Signals generate correctly

**Check in browser console:**
```javascript
// Look for multiple network requests:
// 1. fetch-stock-data?symbols=AAPL,TSLA,NVDA
// 2. fetch-options-prices?symbol=AAPL
// 3. fetch-options-prices?symbol=TSLA
// etc.

// All should show source: "alpaca"
```

---

## 🔄 Force Refresh Everything

If nothing else works, try this complete reset:

### 1. Clear All Caches
```bash
# In browser console:
localStorage.clear()
sessionStorage.clear()
caches.keys().then(names => names.forEach(name => caches.delete(name)))
navigator.serviceWorker.getRegistrations().then(r => r.forEach(reg => reg.unregister()))

# Then hard reload:
# Windows/Linux: Ctrl + Shift + R
# Mac: Cmd + Shift + R
```

### 2. Redeploy Functions
```bash
supabase functions delete fetch-stock-data
supabase functions delete fetch-options-prices
supabase functions delete fetch-intraday-data

# Wait 10 seconds

supabase functions deploy fetch-stock-data
supabase functions deploy fetch-options-prices
supabase functions deploy fetch-intraday-data
```

### 3. Check Function Logs
```bash
# Open 3 terminal windows and run:
supabase functions logs fetch-stock-data --tail
supabase functions logs fetch-options-prices --tail
supabase functions logs fetch-intraday-data --tail

# Then use your app and watch for:
# "✅ Alpaca: Fetched X stock quotes"
# "✅ Alpaca: Fetched X calls, X puts"
```

---

## 🎯 Priority Order Verification

After deployment, verify the priority order is correct:

### Stock Quotes Priority:
1. **Alpaca** (primary) ← Should see this
2. Yahoo (fallback)
3. Tradier (fallback)

### Options Prices Priority:
1. **Alpaca** (primary) ← Should see this
2. Yahoo (fallback)
3. Tradier (fallback)

### Intraday Bars Priority:
1. **Alpaca** (primary) ← Should see this
2. Tradier (fallback)

**Check logs for:**
```
🔄 Fetching quotes for 3 symbols
✅ Alpaca: Fetched 3 stock quotes
```

**Not this:**
```
🔄 Fetching quotes for 3 symbols
⚠️ Alpaca failed, trying Yahoo
✅ Yahoo: Fetched 3 stock quotes
```

---

## 📞 Still Not Working?

### Check These Common Issues:

1. **Alpaca API Keys in Supabase Dashboard**
   - Go to: https://supabase.com/dashboard/project/plxlzcpkxjrmtphslmzq/settings/functions
   - Verify environment variables are set

2. **Market Hours**
   - Test during US market hours (9:30 AM - 4:00 PM ET)
   - Or verify Alpaca returns data for closed markets

3. **Rate Limits**
   - Alpaca: 200 requests/minute
   - If exceeded, wait 60 seconds

4. **Function Deployment Status**
   - Go to: https://supabase.com/dashboard/project/plxlzcpkxjrmtphslmzq/functions
   - Verify functions show as "deployed"
   - Check last deployment time is recent

5. **Network Issues**
   - Check browser network tab for failed requests
   - Verify CORS headers in responses
   - Check for any 401/403 errors

---

## ✅ Success Checklist

After deployment, verify all these:

- [ ] `curl` test to Alpaca API works directly
- [ ] Edge function returns `"source": "alpaca"`
- [ ] Browser console shows Alpaca requests
- [ ] QuantFlow Scanner updates every 2 seconds
- [ ] SPX Options Scanner loads options chains
- [ ] SPX Options Flow shows large trades
- [ ] Intraday Options Scanner scans multiple symbols
- [ ] All prices match current market data
- [ ] Function logs show "✅ Alpaca: Fetched..."

---

## 📚 Reference Commands

**Quick test all 3 endpoints:**
```bash
# Set your auth token
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBseGx6Y3BreGpybXRwaHNsbXpxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1NjI1MjAsImV4cCI6MjA3NzEzODUyMH0.P048N6dg6VZqvHRcXYt_vntteKqj_ifhsahE5LsLV_I"

# Test stock quotes
curl -s "https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/fetch-stock-data?symbols=AAPL&mode=return" \
  -H "Authorization: Bearer $TOKEN" | grep -o '"source":"[^"]*"'

# Test options prices
curl -s "https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/fetch-options-prices?symbol=SPX" \
  -H "Authorization: Bearer $TOKEN" | grep -o '"source":"[^"]*"'

# Test intraday data
curl -s "https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/fetch-intraday-data?symbol=AAPL&interval=5m&days=1" \
  -H "Authorization: Bearer $TOKEN" | grep -o '"source":"[^"]*"'

# All 3 should output: "source":"alpaca"
```

---

## 🎉 Expected Results

Once everything is working:

**✅ Stock Quotes:**
- Source: Alpaca
- Update: Every 2 seconds
- Data: Real-time prices, volume, change%

**✅ Options Chains:**
- Source: Alpaca
- Coverage: SPX + all US stocks
- Data: Bid/Ask/Last, Volume, IV

**✅ Intraday Bars:**
- Source: Alpaca
- Intervals: 1m, 5m, 15m, 1h, 1d
- Data: OHLCV bars up to 30 days

**Total Cost: $0/month** 💰

---

**Status: Ready to Deploy!** 🚀

Run `./DEPLOY_FUNCTIONS.sh` now!
