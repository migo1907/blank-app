# 🔧 FIX: Empty JSON Error from TradingView

## Your Error:
```
Webhook error: SyntaxError: Unexpected end of JSON input
```

## What This Means:
TradingView is sending **EMPTY data** to your webhook. The alert is configured with webhook URL, but the **"Message" field is empty or missing**.

---

## ✅ SOLUTION: Add JSON Message to Your TradingView Alert

### Step-by-Step Fix:

1. **Open TradingView**

2. **Find Your Alert:**
   - Click the Bell icon (🔔) in the right sidebar
   - Locate your alert in the list
   - Right-click → **"Edit"**

3. **Scroll Down to "Message" Field**
   - Look for the large text box labeled **"Message"**
   - This field is probably **EMPTY** right now

4. **Add This Exact JSON:**
   ```json
   {
     "ticker": "{{ticker}}",
     "signal_type": "BUY",
     "price": {{close}},
     "timeframe": "{{interval}}",
     "indicator": "My Indicator",
     "strategy": "My Strategy"
   }
   ```

5. **Customize the Signal Type:**
   - Change `"BUY"` to whatever fits your alert:
     - `"BUY"` - For buy signals
     - `"SELL"` - For sell signals
     - `"LONG"` - For long positions
     - `"SHORT"` - For short positions

6. **Verify Webhook Settings:**
   - Make sure ☑ **"Webhook URL"** checkbox is CHECKED
   - Webhook URL should be: `https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/stock-signals-webhook`

7. **Click "Save"**

8. **Test It:**
   - Wait for alert to fire (or trigger it manually)
   - Check Stock Signals app
   - Signal should now appear!

---

## 📋 Full Alert Configuration Example

Here's what your TradingView alert should look like:

```
┌─────────────────────────────────────────────┐
│ Alert Name: AAPL RSI Overbought            │
│                                             │
│ Condition: RSI(14) crossing above 70       │
│                                             │
│ Options:                                    │
│ Frequency: Once Per Bar Close              │
│ Expiration: Open-ended                     │
│                                             │
│ Alert actions:                              │
│ ☑ Show popup                                │
│ ☑ Webhook URL ← MUST BE CHECKED!          │
│                                             │
│ Webhook URL:                                │
│ https://plxlzcpkxjrmtphslmzq.supabase...  │
│                                             │
│ Message: ← THIS WAS EMPTY, NOW ADD JSON:   │
│ ┌─────────────────────────────────────────┐ │
│ │ {                                       │ │
│ │   "ticker": "{{ticker}}",               │ │
│ │   "signal_type": "SELL",                │ │
│ │   "price": {{close}},                   │ │
│ │   "timeframe": "{{interval}}",          │ │
│ │   "indicator": "RSI",                   │ │
│ │   "strategy": "RSI Overbought"          │ │
│ │ }                                       │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│         [Cancel]  [Save]                    │
└─────────────────────────────────────────────┘
```

---

## 🎯 Common Message Templates

### For Buy Signals (RSI Oversold, MACD Bullish, etc.):
```json
{
  "ticker": "{{ticker}}",
  "signal_type": "BUY",
  "price": {{close}},
  "timeframe": "{{interval}}",
  "indicator": "RSI Oversold",
  "strategy": "RSI Strategy",
  "stop_loss": {{low}},
  "take_profit": {{high}}
}
```

### For Sell Signals (RSI Overbought, MACD Bearish, etc.):
```json
{
  "ticker": "{{ticker}}",
  "signal_type": "SELL",
  "price": {{close}},
  "timeframe": "{{interval}}",
  "indicator": "RSI Overbought",
  "strategy": "RSI Strategy",
  "stop_loss": {{high}},
  "take_profit": {{low}}
}
```

### For Moving Average Cross:
```json
{
  "ticker": "{{ticker}}",
  "signal_type": "LONG",
  "price": {{close}},
  "timeframe": "{{interval}}",
  "indicator": "MA Cross",
  "strategy": "Golden Cross",
  "message": "50 MA crossed above 200 MA"
}
```

### Minimal (Only Required Fields):
```json
{
  "ticker": "{{ticker}}",
  "signal_type": "BUY",
  "price": {{close}}
}
```

---

## ⚠️ CRITICAL JSON RULES

### ✅ CORRECT Format:

```json
{
  "ticker": "{{ticker}}",      ← String variable: USE quotes
  "signal_type": "BUY",        ← String value: USE quotes
  "price": {{close}},          ← Number variable: NO quotes
  "timeframe": "{{interval}}"  ← String variable: USE quotes
}
```

### ❌ WRONG Formats:

**Missing Quotes Around Keys:**
```json
{
  ticker: "{{ticker}}",    ← WRONG: Keys must have quotes
  signal_type: "BUY"
}
```

**Missing Quotes Around String Values:**
```json
{
  "ticker": "{{ticker}}",
  "signal_type": BUY       ← WRONG: String values need quotes
}
```

**Quotes Around Number Variables:**
```json
{
  "ticker": "{{ticker}}",
  "price": "{{close}}"     ← WRONG: Numbers should NOT have quotes
}
```

**Trailing Comma:**
```json
{
  "ticker": "{{ticker}}",
  "price": {{close}},      ← WRONG: Last item can't have comma
}
```

---

## 🧪 Test Your Fix

After adding the JSON message and saving:

1. **Trigger a Test Alert:**
   - Create a new alert with condition: `Price > [current - 1]`
   - This will fire immediately
   - Use the same JSON message format

2. **Check Stock Signals:**
   - Within 2-3 seconds, signal should appear
   - Verify the data is correct

3. **Check Supabase Logs:**
   - Go to: https://app.supabase.com/
   - Edge Functions → stock-signals-webhook → Logs
   - You should see: `✅ Stock signal inserted successfully`
   - NOT: `❌ EMPTY BODY`

---

## 💡 Why This Happens

TradingView has TWO separate fields:

1. **Webhook URL** - Where to send data
2. **Message** - What data to send

You had:
- ✅ Webhook URL configured (checkbox checked)
- ❌ Message field EMPTY

Result: TradingView sent a request to your webhook, but with NO body/data.

Now you need:
- ✅ Webhook URL configured
- ✅ Message field with JSON data

---

## ✅ Success Criteria

You'll know it's working when:

1. ✅ No more "Unexpected end of JSON input" errors
2. ✅ Signals appear in Stock Signals app
3. ✅ Supabase logs show successful inserts
4. ✅ Signal data matches your alert configuration

---

## 🆘 Still Having Issues?

### Error: "Invalid JSON format"
**Cause:** Syntax error in your JSON
**Fix:**
1. Copy your JSON
2. Go to https://jsonlint.com/
3. Paste and validate
4. Fix any errors shown
5. Copy corrected JSON back to TradingView

### Error: "Missing required fields"
**Cause:** JSON doesn't include ticker, signal_type, or price
**Fix:** Make sure your message includes ALL three:
```json
{
  "ticker": "{{ticker}}",
  "signal_type": "BUY",
  "price": {{close}}
}
```

### Signals Still Not Appearing
**Check:**
1. Is alert actually firing? (check TradingView alert list)
2. Is webhook checkbox checked?
3. Is message field filled with JSON?
4. Check Supabase logs for new errors

---

## 📱 Need More Help?

Check the comprehensive guides:
- `TRADINGVIEW_ALERT_TROUBLESHOOTING_GUIDE.md` - Full troubleshooting
- `WEBHOOK_QUICK_START.md` - Quick setup guide
- `ALERT_NOT_SHOWING_DIAGNOSTICS.md` - Step-by-step diagnosis

---

**TL;DR:** Add JSON message to your TradingView alert "Message" field. That's what's missing!
