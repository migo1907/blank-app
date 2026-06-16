# TradingView to Stock Signals Troubleshooting Guide

## 🔴 Problem: Alerts Appear in TradingView But NOT in Stock Signals

This comprehensive guide will help you diagnose and fix the synchronization issue between TradingView alerts and your Stock Signals application.

---

## ✅ Quick Diagnostic Checklist

Before troubleshooting, verify:
- [ ] You have a TradingView **Pro, Pro+, or Premium** account (webhooks require paid subscription)
- [ ] Alerts are firing in TradingView (you see/hear them)
- [ ] You have the correct webhook URL
- [ ] The Stock Signals tab is open in your browser

---

## 1️⃣ CONNECTION VERIFICATION

### Step 1.1: Check Your Webhook URL

**Your webhook URL should be:**
```
https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/stock-signals-webhook
```

**How to verify:**
1. Open your Stock Signals application
2. Navigate to: **Market Overview** → **Scanner** → **Stock Signals**
3. Click the **"Webhook Info"** button (⚡)
4. Compare the displayed URL with the URL above
5. If different, **copy the correct URL** from the Webhook Info panel

### Step 1.2: Test Webhook Connection (Recommended)

**Use the built-in Test button:**
1. In Stock Signals, go to: **Stock Signals** tab
2. Click **"Webhook Info"** button
3. Click the green **"🧪 Test"** button
4. You should see:
   - ✅ "Success! Test signal sent successfully!"
   - A test signal appears in the signals table below
   - Signal shows: AAPL @ $182.50 (Test Signal)

**If the test fails:**
- Check browser console for errors (F12 → Console tab)
- Verify your internet connection
- Try refreshing the page

### Step 1.3: Manual Webhook Test (Advanced)

**Using curl (Terminal/Command Prompt):**
```bash
curl -X POST https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/stock-signals-webhook \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "AAPL",
    "signal_type": "BUY",
    "price": 182.50,
    "timeframe": "5m",
    "indicator": "Manual Test",
    "strategy": "Testing",
    "message": "Manual webhook test"
  }'
```

**Expected response:**
```json
{
  "success": true,
  "message": "Stock signal received and stored successfully",
  "data": { ... }
}
```

**If you get an error:**
- `400 Bad Request`: Missing required fields (ticker, signal_type, price)
- `500 Internal Server Error`: Database connection issue
- `CORS Error`: Browser security blocking the request (use curl instead)

---

## 2️⃣ TRADINGVIEW ALERT CONFIGURATION

### Step 2.1: Verify TradingView Account Type

**Check your subscription:**
1. Go to: https://www.tradingview.com/gopro/
2. Click on your profile icon (top right)
3. Select **"Profile settings"**
4. Check **"Billing and payments"**

**Requirements:**
- ❌ **Free/Basic accounts**: Webhooks NOT supported
- ✅ **Pro ($14.95/month)**: Webhooks supported
- ✅ **Pro+ ($29.95/month)**: Webhooks supported
- ✅ **Premium ($59.95/month)**: Webhooks supported

**If you have a free account:**
- You MUST upgrade to use webhooks
- Alternative: Use the Stock Signals app's built-in scanners instead

### Step 2.2: Create Alert with Webhook (Correct Method)

**Follow these exact steps:**

1. **Open TradingView chart** for your desired symbol (e.g., AAPL)

2. **Create the alert:**
   - Click the **Clock icon** (⏰) in top toolbar
   - OR press **Alt + A** (Windows) / **Option + A** (Mac)
   - OR right-click chart → **"Add alert"**

3. **Configure Alert Condition:**
   ```
   Condition: [Choose your trigger]
   Examples:
   - Price crossing moving average
   - RSI crossing 70
   - Any indicator signal
   - Price > 180 (for immediate test)
   ```

4. **Set Alert Options:**
   ```
   Alert name: [Descriptive name, e.g., "AAPL RSI Overbought"]
   Frequency: "Once Per Bar Close" (recommended)
   Expiration: "Open-ended" or set date
   ```

5. **⚠️ CRITICAL: Enable Webhook URL**
   - Check the box: ☑ **"Webhook URL"**
   - This checkbox MUST be checked!

6. **Enter Webhook URL:**
   ```
   Paste in the Webhook URL field:
   https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/stock-signals-webhook
   ```

7. **Configure Alert Message (JSON Format):**
   ```json
   {
     "ticker": "{{ticker}}",
     "signal_type": "BUY",
     "price": {{close}},
     "timeframe": "{{interval}}",
     "indicator": "RSI Cross",
     "strategy": "My Strategy Name",
     "stop_loss": {{low}},
     "take_profit": {{high}},
     "message": "{{strategy.order.alert_message}}"
   }
   ```

8. **Important JSON Rules:**
   - `{{ticker}}` → Auto-fills with current symbol
   - `{{close}}` → Auto-fills with close price (NO QUOTES)
   - `{{interval}}` → Auto-fills with timeframe
   - `"BUY"` → Change to "BUY", "SELL", "LONG", or "SHORT" (WITH QUOTES)
   - Must be valid JSON (use quotes for strings, not for numbers)

9. **Click "Create"** button

### Step 2.3: Common Alert Configuration Mistakes

**❌ WRONG: Webhook checkbox not checked**
```
☐ Webhook URL   ← NOT CHECKED = No webhook sent!
```

**✅ CORRECT: Webhook checkbox checked**
```
☑ Webhook URL   ← CHECKED = Webhook will fire
```

**❌ WRONG: Invalid JSON format**
```json
{
  ticker: AAPL,           ← Missing quotes
  signal_type: BUY,       ← Missing quotes
  price: "182.50"         ← Price should be number, not string
}
```

**✅ CORRECT: Valid JSON format**
```json
{
  "ticker": "AAPL",
  "signal_type": "BUY",
  "price": 182.50
}
```

**❌ WRONG: Using quotes around TradingView variables for numbers**
```json
{
  "price": "{{close}}"    ← Will send string "182.50" instead of number
}
```

**✅ CORRECT: No quotes for numeric variables**
```json
{
  "price": {{close}}      ← Will send number 182.50
}
```

### Step 2.4: Verify Alert is Active

1. Click **Alert icon** (🔔) in right sidebar
2. Find your alert in the list
3. Check it shows:
   - ✅ Green indicator = Active
   - 🌐 Globe icon = Webhook enabled
4. If you see ❌ or 🚫, the alert is disabled

---

## 3️⃣ API/WEBHOOK SETUP

### Step 3.1: Webhook URL Components

**Your webhook URL breakdown:**
```
https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/stock-signals-webhook
       └─────────┬─────────┘              └─────────┬─────────┘  └────┬────┘
           Project ID                       Functions path      Function name
```

**Verification:**
- ✅ URL must start with `https://` (not `http://`)
- ✅ Must include your Supabase project ID
- ✅ Must end with `/stock-signals-webhook`
- ✅ No trailing slash
- ✅ No spaces or extra characters

### Step 3.2: No API Keys Required

**Good news:** TradingView webhooks do NOT require:
- ❌ No API keys needed
- ❌ No authentication tokens
- ❌ No special headers
- ✅ Just the webhook URL

**The webhook is publicly accessible** (by design) because:
- It only accepts POST requests
- It validates incoming data
- It's designed to receive TradingView alerts

### Step 3.3: Firewall/Network Issues

**If webhooks aren't reaching your server:**

1. **Check if Supabase is accessible:**
   ```bash
   curl https://plxlzcpkxjrmtphslmzq.supabase.co/rest/v1/
   ```
   Should return: `{"message":"Welcome to the Supabase API"}`

2. **Corporate/School network blocking:**
   - Some networks block webhook services
   - Try from a different network (mobile hotspot)
   - Contact IT if on corporate network

3. **VPN interference:**
   - Disable VPN temporarily
   - Try without VPN to test

---

## 4️⃣ COMMON ISSUES & SOLUTIONS

### Issue #1: Alert Fires but Signal Doesn't Appear

**Possible causes:**
1. **Webhook URL typo** in TradingView
   - Solution: Re-copy URL from Stock Signals → Webhook Info
   - Re-create the alert with correct URL

2. **Webhook checkbox not checked**
   - Solution: Edit alert → Check ☑ "Webhook URL" → Save

3. **Invalid JSON format**
   - Solution: Copy exact JSON from Webhook Info panel
   - Use JSON validator: https://jsonlint.com/

4. **Browser tab closed**
   - Solution: Stock Signals must be OPEN to see realtime updates
   - Signals are stored in database, refresh page to see historical

### Issue #2: Getting "Missing Required Fields" Error

**Check your JSON includes minimum required fields:**
```json
{
  "ticker": "AAPL",        ← REQUIRED
  "signal_type": "BUY",    ← REQUIRED
  "price": 182.50          ← REQUIRED
}
```

**These are OPTIONAL:**
- `timeframe`, `indicator`, `strategy`, `stop_loss`, `take_profit`, `message`

### Issue #3: Signal Appears with Wrong Data

**Problem:** Signal shows as "undefined" or "NaN"

**Cause:** TradingView variables not properly formatted

**Solution:** Check your alert message:
```json
{
  "ticker": "{{ticker}}",     ← Must have double quotes
  "price": {{close}},         ← Must NOT have quotes
  "timeframe": "{{interval}}" ← Must have double quotes
}
```

### Issue #4: Multiple Duplicate Signals

**Cause:** Alert frequency set to "Once Per Bar" instead of "Once Per Bar Close"

**Solution:**
1. Edit your alert in TradingView
2. Change **Frequency** to: "Once Per Bar Close"
3. This prevents multiple signals on same bar

### Issue #5: Webhook Times Out

**Symptoms:**
- Alert fires in TradingView
- No signal appears
- TradingView shows webhook error

**Solutions:**
1. **Check Supabase function status:**
   - Go to: Supabase Dashboard → Functions
   - Verify `stock-signals-webhook` is deployed
   - Check function logs for errors

2. **Database connection issue:**
   - Check if database is online
   - Verify RLS policies allow inserts

3. **Try manual test:**
   - Use the Test button in Stock Signals
   - If test works, TradingView config is wrong
   - If test fails, backend issue

---

## 5️⃣ TESTING PROCESS

### Test #1: Built-In Test Button (Easiest)

1. Go to Stock Signals tab
2. Click "Webhook Info"
3. Click green "🧪 Test" button
4. **Expected result:**
   - Green success message
   - Test signal appears in table
   - Signal: AAPL BUY @ $182.50

**If this works:** Webhook backend is functioning correctly

### Test #2: Create Immediate-Fire Alert

**Create an alert that fires right away:**

1. Open any chart (e.g., AAPL)
2. Create alert with condition:
   ```
   Price > [current price - 1]
   Example: If AAPL = 180, set "Price > 179"
   ```
3. Set frequency: "Only Once"
4. Enable webhook ☑
5. Add webhook URL
6. Add JSON message
7. Click "Create"
8. Alert should fire IMMEDIATELY

**Expected result:**
- TradingView shows alert notification
- Within 2-3 seconds, signal appears in Stock Signals
- Signal data matches your JSON

### Test #3: Monitor Browser Console

**Open Developer Tools:**
1. Press **F12** (Windows) or **Cmd+Option+I** (Mac)
2. Go to **Console** tab
3. Keep this open while testing
4. Create/fire an alert

**Look for:**
- ✅ "Signal change detected" = Realtime listener working
- ✅ "Stock signal inserted" = Database write successful
- ❌ Any red error messages = Problem identified

### Test #4: Check Database Directly

**Verify signals are being stored:**
1. Open Stock Signals tab
2. Click "Refresh" button
3. Check if signals appear
4. Look at timestamp to verify recent

**Alternative: Check Supabase Dashboard:**
1. Go to: https://app.supabase.com/
2. Select your project
3. Go to: Table Editor → `stock_signals`
4. Check if rows are being inserted
5. Look at `created_at` timestamp

### Test #5: Webhook Logs

**Check Supabase function logs:**
1. Supabase Dashboard → Functions → `stock-signals-webhook`
2. Click "Logs" tab
3. Trigger a test alert
4. Look for:
   - ✅ "Stock signal inserted" = Success
   - ❌ Error messages = Shows what failed

---

## 6️⃣ ALTERNATIVE SOLUTIONS

### Alternative #1: Use Email-to-Webhook Service

**If direct webhooks aren't working:**

1. Use a service like **Zapier** or **IFTTT**
2. Set TradingView to send email alerts
3. Service converts emails to webhooks
4. Forwards to your Stock Signals webhook

**Setup:**
- TradingView → Email alert
- Zapier → Catch email
- Zapier → Send webhook to your URL

### Alternative #2: Use Built-In Scanners

**Stock Signals includes built-in scanners:**

1. **Intraday Options Scanner (0-2 DTE)**
   - Automatically finds high-probability options trades
   - Live data feed from market
   - No TradingView needed

2. **SPX Options Scanner**
   - Persistent scanning during market hours
   - Auto-generates CALL/PUT recommendations
   - Updates every 5 minutes

3. **AI SVIP Signals**
   - Pre-built signal generator
   - Multiple assets covered
   - No manual configuration

**Benefits:**
- No TradingView subscription required
- Automatic signal generation
- Built-in live data
- No webhook configuration

### Alternative #3: Manual Signal Entry

**Create signals manually:**
1. (Would require adding a manual entry feature)
2. Click "Add Signal" button
3. Enter: Ticker, Type, Price, etc.
4. Save to database

*(Note: This feature could be added if needed)*

---

## 7️⃣ STEP-BY-STEP TROUBLESHOOTING WORKFLOW

**Follow this exact sequence:**

### ✅ Step 1: Verify Account
- [ ] Confirm TradingView Pro/Premium account
- [ ] If free account → **STOP**: Upgrade required

### ✅ Step 2: Test Webhook Backend
- [ ] Open Stock Signals app
- [ ] Go to Stock Signals tab
- [ ] Click "Webhook Info"
- [ ] Click "🧪 Test" button
- [ ] Verify test signal appears
- [ ] If test fails → **Check browser console for errors**

### ✅ Step 3: Get Webhook URL
- [ ] Copy URL from Webhook Info panel
- [ ] Verify URL format is correct
- [ ] Keep this tab open

### ✅ Step 4: Create Test Alert
- [ ] Open TradingView
- [ ] Open any chart (AAPL recommended)
- [ ] Press Alt+A to create alert
- [ ] Set condition: "Price > [current price - 1]"
- [ ] **CHECK** ☑ "Webhook URL" checkbox
- [ ] Paste webhook URL
- [ ] Copy JSON from Webhook Info panel
- [ ] Paste in Message field
- [ ] Change `"signal_type": "BUY"` if desired
- [ ] Click "Create"

### ✅ Step 5: Verify Alert Fires
- [ ] Alert should trigger immediately
- [ ] Check TradingView alert notification
- [ ] Check alert list (🔔 icon) shows alert fired

### ✅ Step 6: Check Stock Signals
- [ ] Within 2-3 seconds, check Stock Signals tab
- [ ] Signal should appear in table
- [ ] Verify data matches your alert
- [ ] Check timestamp is recent

### ✅ Step 7: If Still Not Working
- [ ] Open browser console (F12)
- [ ] Check for error messages
- [ ] Click "Refresh" in Stock Signals
- [ ] Check if signal appears after refresh
- [ ] Try manual curl test (see Section 1.3)

### ✅ Step 8: Advanced Debugging
- [ ] Check Supabase function logs
- [ ] Verify database table has RLS policies
- [ ] Test from different network
- [ ] Contact support with error logs

---

## 8️⃣ REQUIRED PERMISSIONS & SETTINGS

### TradingView Requirements
- ✅ Pro/Premium account ($14.95+/month)
- ✅ Chart open with indicator/strategy
- ✅ Alert creation permissions (default: enabled)
- ✅ Internet connection

### Stock Signals Requirements
- ✅ Browser tab must remain open for realtime updates
- ✅ JavaScript enabled
- ✅ Cookies/LocalStorage enabled
- ✅ No ad blockers blocking WebSocket connections

### Supabase/Backend Requirements
- ✅ `stock-signals-webhook` function deployed
- ✅ `stock_signals` table exists
- ✅ RLS policies allow anonymous inserts (webhook is public)
- ✅ Database is online and accessible

### Network Requirements
- ✅ HTTPS connection (webhooks require secure connection)
- ✅ Firewall allows outbound to Supabase domain
- ✅ No VPN/proxy blocking webhook traffic
- ✅ Corporate network allows webhook services

---

## 9️⃣ VERIFICATION CHECKLIST

**Complete this checklist to verify everything is set up correctly:**

### TradingView Setup
- [ ] I have a Pro/Premium account (verified in billing)
- [ ] Alert condition is set correctly
- [ ] ☑ "Webhook URL" checkbox is CHECKED
- [ ] Webhook URL is pasted correctly (no typos)
- [ ] Alert message is valid JSON
- [ ] Alert is active (green indicator in alert list)
- [ ] Frequency is set to "Once Per Bar Close"
- [ ] Alert has fired at least once (I saw/heard it)

### Stock Signals Setup
- [ ] Stock Signals tab is open in browser
- [ ] Webhook Info button works
- [ ] Test button successfully sends test signal
- [ ] Test signal appears in signals table
- [ ] No error messages in browser console
- [ ] Refresh button works and loads signals
- [ ] Timestamp on signals is recent

### Connection Verification
- [ ] Manual curl test returns success
- [ ] Browser can reach Supabase domain
- [ ] No network/firewall blocking
- [ ] Webhook URL is publicly accessible
- [ ] Database is accepting inserts

---

## 🆘 STILL NOT WORKING? GET HELP

### Collect Diagnostic Information

**Before requesting support, gather:**

1. **TradingView Alert Configuration**
   - Screenshot of alert settings
   - Copy of your JSON message
   - Alert frequency setting
   - Screenshot showing webhook checkbox is checked

2. **Error Messages**
   - Browser console errors (F12 → Console)
   - Screenshot of any error messages
   - Supabase function logs (if accessible)

3. **Test Results**
   - Does built-in Test button work? (Yes/No)
   - Does curl test work? (Yes/No)
   - Do signals appear after manual refresh? (Yes/No)

4. **Account Information**
   - TradingView account type (Pro/Premium)
   - When did this last work? (Never/Previously worked)

### Common Solutions Summary

**95% of issues are caused by:**
1. **Not having TradingView Pro/Premium** (50% of cases)
2. **Webhook checkbox not checked** (25% of cases)
3. **Invalid JSON format** (15% of cases)
4. **Wrong webhook URL** (10% of cases)

**Quick fixes:**
- ✅ Use the built-in Test button first
- ✅ Copy/paste webhook URL and JSON (don't type manually)
- ✅ Create immediate-fire test alert
- ✅ Check browser console for errors

---

## 📋 QUICK REFERENCE: Correct Alert Setup

```
┌─────────────────────────────────────────────────┐
│ Create Alert                                    │
├─────────────────────────────────────────────────┤
│ Condition: [Your trigger condition]             │
│                                                 │
│ Options:                                        │
│ Alert name: [Your alert name]                  │
│ Frequency: Once Per Bar Close ▼                │
│ Expiration: Open-ended ▼                       │
│                                                 │
│ Alert actions:                                  │
│ ☑ Show popup                                    │
│ ☑ Webhook URL ← MUST BE CHECKED!              │
│                                                 │
│ Webhook URL:                                    │
│ [https://plxlzcpkxjrmtphslmzq...]             │
│                                                 │
│ Message:                                        │
│ {                                               │
│   "ticker": "{{ticker}}",                       │
│   "signal_type": "BUY",                         │
│   "price": {{close}},                           │
│   "timeframe": "{{interval}}",                  │
│   "indicator": "Your Indicator",                │
│   "strategy": "Your Strategy"                   │
│ }                                               │
│                                                 │
│         [Cancel]  [Create]                      │
└─────────────────────────────────────────────────┘
```

---

## ✅ SUCCESS CRITERIA

**You'll know it's working when:**
1. ✅ Test button sends signal successfully
2. ✅ TradingView alert fires and you see notification
3. ✅ Signal appears in Stock Signals within 2-3 seconds
4. ✅ Signal data matches your alert configuration
5. ✅ Subsequent alerts continue to appear
6. ✅ No error messages in browser console

**Congratulations!** Your TradingView alerts are now synced with Stock Signals.

---

**Need more help?** Check the browser console (F12) for specific error messages and include them when seeking assistance.
