# TradingView AI Svip 1.7.0.4 - Webhook Setup Guide

This guide explains how to connect your TradingView AI Svip 1.7.0.4 indicator to automatically send signals to your application.

---

## 📋 Overview

The AI Svip indicator in TradingView can send real-time signals via webhooks whenever it generates a BUY or SELL signal. These signals are stored in your Supabase database and displayed in the "AI Svip Signals" tab.

---

## 🔗 Your Webhook URL

```
https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/tradingview-webhook
```

**Important:** This webhook is already deployed and ready to receive signals!

---

## ⚙️ Step-by-Step Setup

### Step 1: Open TradingView Alert

1. Open your TradingView chart with the **AI Svip 1.7.0.4** indicator loaded
2. Click the **Alert** button (bell icon) in the top toolbar
3. Or right-click on the chart → **Add Alert**

### Step 2: Configure Alert Conditions

**Condition Settings:**
- **Select:** AI Svip 1.7.0.4 (your indicator)
- **Trigger:** Choose your signal condition
  - Example: "Signal: Long" for BUY signals
  - Example: "Signal: Short" for SELL signals
- **Options:**
  - ✅ Once Per Bar Close (recommended)
  - Or: Once Per Bar (for more frequent signals)

### Step 3: Configure Webhook

In the **Alert Actions** section:

1. Check **"Webhook URL"**
2. Paste your webhook URL:
   ```
   https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/tradingview-webhook
   ```

### Step 4: Set Alert Message (JSON Payload)

In the **Message** field, paste this JSON template:

```json
{
  "symbol": "{{ticker}}",
  "action": "BUY",
  "price": {{close}},
  "target1": {{close}} * 1.03,
  "target2": {{close}} * 1.05,
  "stop_loss": {{close}} * 0.98,
  "indicator_name": "AI Svip 1.7.0.4",
  "timeframe": "{{interval}}",
  "strength": "moderate",
  "notes": "Signal from TradingView at {{time}}"
}
```

**For SELL Signals, use:**
```json
{
  "symbol": "{{ticker}}",
  "action": "SELL",
  "price": {{close}},
  "target1": {{close}} * 0.97,
  "target2": {{close}} * 0.95,
  "stop_loss": {{close}} * 1.02,
  "indicator_name": "AI Svip 1.7.0.4",
  "timeframe": "{{interval}}",
  "strength": "moderate",
  "notes": "Signal from TradingView at {{time}}"
}
```

### Step 5: Customize Your Signal Parameters

**Adjust these values based on your AI Svip indicator's actual calculations:**

**For BUY Signals:**
```json
{
  "symbol": "{{ticker}}",
  "action": "BUY",
  "price": {{close}},
  "target1": [YOUR_TARGET1_FORMULA],
  "target2": [YOUR_TARGET2_FORMULA],
  "stop_loss": [YOUR_STOPLOSS_FORMULA],
  "indicator_name": "AI Svip 1.7.0.4",
  "timeframe": "{{interval}}",
  "strength": "strong",
  "notes": "AI Svip signal"
}
```

**Common TradingView Variables:**
- `{{ticker}}` - Symbol (e.g., AAPL, SPY)
- `{{close}}` - Close price
- `{{open}}` - Open price
- `{{high}}` - High price
- `{{low}}` - Low price
- `{{volume}}` - Volume
- `{{time}}` - Timestamp
- `{{interval}}` - Timeframe (5, 15, 30, 60)

**Example with Custom Calculations:**
If your AI Svip indicator provides specific entry/exit levels, you can reference them:
```json
{
  "symbol": "{{ticker}}",
  "action": "BUY",
  "price": [YOUR_ENTRY_VALUE],
  "target1": [YOUR_TARGET1_VALUE],
  "target2": [YOUR_TARGET2_VALUE],
  "stop_loss": [YOUR_STOP_VALUE],
  "indicator_name": "AI Svip 1.7.0.4",
  "timeframe": "{{interval}}",
  "strength": "strong"
}
```

### Step 6: Set Alert Properties

**Alert Name:** Give it a descriptive name
- Example: "AI Svip - SPY - 5min - BUY"
- Example: "AI Svip - AAPL - 15min - SELL"

**Expiration:** Choose how long the alert should remain active
- Recommended: Open-ended (until manually cancelled)

**Additional Options:**
- ✅ Show popup
- ✅ Send email (optional)
- ✅ Play sound (optional)
- ✅ Send webhook (REQUIRED)

### Step 7: Create the Alert

1. Click **"Create"** button
2. Alert is now active!
3. Every time AI Svip generates a signal, it will be sent to your app

---

## 🎯 Multiple Timeframes Setup

To receive signals from all timeframes (5m, 15m, 30m, 1h), create **separate alerts** for each:

### 5-Minute Chart Alert
1. Switch to 5-minute timeframe
2. Create alert with `"timeframe": "5m"`
3. Name: "AI Svip - 5min"

### 15-Minute Chart Alert
1. Switch to 15-minute timeframe
2. Create alert with `"timeframe": "15m"`
3. Name: "AI Svip - 15min"

### 30-Minute Chart Alert
1. Switch to 30-minute timeframe
2. Create alert with `"timeframe": "30m"`
3. Name: "AI Svip - 30min"

### 1-Hour Chart Alert
1. Switch to 1-hour timeframe
2. Create alert with `"timeframe": "1h"`
3. Name: "AI Svip - 1h"

---

## 📊 JSON Payload Reference

### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `symbol` | string | Stock ticker | "AAPL" |
| `action` | string | BUY or SELL | "BUY" |
| `price` | number | Entry price | 178.50 |
| `target1` | number | First target | 183.80 |
| `target2` | number | Second target | 187.40 |
| `stop_loss` | number | Stop loss price | 174.90 |

### Optional Fields

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `indicator_name` | string | Indicator name | "TradingView Custom Indicator" |
| `timeframe` | string | Chart timeframe | "1D" |
| `strength` | string | weak/moderate/strong | "moderate" |
| `notes` | string | Additional notes | "" |

---

## ✅ Testing Your Webhook

### Method 1: TradingView Test
1. After creating the alert, click **"Test"** button
2. Check your AI Svip Signals tab for the test signal

### Method 2: Manual cURL Test
```bash
curl -X POST https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/tradingview-webhook \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "SPY",
    "action": "BUY",
    "price": 450.25,
    "target1": 464.00,
    "target2": 472.63,
    "stop_loss": 441.25,
    "indicator_name": "AI Svip 1.7.0.4",
    "timeframe": "5m",
    "strength": "strong"
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "message": "Signal received and stored successfully",
  "data": {
    "id": "...",
    "symbol": "SPY",
    "action": "BUY",
    ...
  }
}
```

---

## 🔍 Verifying Signals

After setting up webhooks:

1. Go to your app's **"AI Svip Signals"** tab
2. Enter the symbols you're tracking
3. Click **"Fetch Signals"**
4. You should see signals from TradingView appear in the tables

**Signal Flow:**
```
TradingView AI Svip Indicator
    ↓ (generates signal)
Alert Triggered
    ↓ (sends webhook)
Supabase Edge Function
    ↓ (processes & stores)
Database (tradingview_signals table)
    ↓ (fetches data)
AI Svip Signals Tab
    ↓ (displays in tables)
Your Screen (organized by timeframe)
```

---

## 🛠️ Advanced Configuration

### Dynamic Stop Loss & Targets

If your AI Svip indicator outputs specific values, reference them in the alert message:

**Example with Indicator Outputs:**
```json
{
  "symbol": "{{ticker}}",
  "action": "BUY",
  "price": {{close}},
  "target1": [plot_value("target1")],
  "target2": [plot_value("target2")],
  "stop_loss": [plot_value("stop")],
  "indicator_name": "AI Svip 1.7.0.4",
  "timeframe": "{{interval}}",
  "strength": "strong"
}
```

### Signal Strength Based on Conditions

Use conditional logic in your alert:
```
If condition A: strength = "strong"
If condition B: strength = "moderate"
If condition C: strength = "weak"
```

---

## 📱 Real-Time Updates

Once webhooks are configured:

✅ **Automatic:** Signals appear immediately when triggered
✅ **No Polling:** Direct push from TradingView
✅ **Multi-Timeframe:** Each timeframe updates independently
✅ **60-Second Refresh:** UI auto-updates every minute

---

## 🔒 Security Notes

1. **Webhook URL is Public:** The webhook endpoint is designed to accept public calls
2. **Rate Limiting:** Built-in protection against spam
3. **Validation:** All signals are validated before storage
4. **Database RLS:** Row Level Security protects your data

---

## 🐛 Troubleshooting

### Signals Not Appearing?

**Check 1: Alert Status**
- Go to TradingView → Alerts panel
- Verify alert is active (not paused)
- Check if alert has fired (history)

**Check 2: Webhook URL**
- Verify URL is exactly: `https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/tradingview-webhook`
- No extra spaces or characters

**Check 3: JSON Format**
- Ensure JSON is valid
- All required fields present
- Correct quotation marks
- No trailing commas

**Check 4: Symbol Match**
- Symbol in webhook matches symbol in filter
- Use uppercase (AAPL not aapl)

**Check 5: Test Manually**
```bash
# Test webhook directly
curl -X POST https://plxlzcpkxjrmtphslmzq.supabase.co/functions/v1/tradingview-webhook \
  -H "Content-Type: application/json" \
  -d '{"symbol":"TEST","action":"BUY","price":100,"target1":103,"target2":105,"stop_loss":98,"timeframe":"5m"}'
```

### Common Errors

**Error: "Missing required fields"**
- Solution: Check all required fields are in JSON

**Error: "Action must be either BUY or SELL"**
- Solution: Use exactly "BUY" or "SELL" (uppercase)

**Error: "Invalid JSON"**
- Solution: Validate JSON at jsonlint.com

---

## 📈 Best Practices

1. **One Alert Per Timeframe:** Create separate alerts for 5m, 15m, 30m, 1h
2. **Descriptive Names:** Use clear alert names for easy management
3. **Test First:** Always test with a single symbol before scaling up
4. **Monitor Initially:** Watch for first few signals to ensure correct data
5. **Update Regularly:** If you modify AI Svip, update alert messages accordingly

---

## 🎯 Example: Complete Setup for SPY

**5-Minute Chart:**
```json
{
  "symbol": "SPY",
  "action": "BUY",
  "price": {{close}},
  "target1": {{close}} * 1.015,
  "target2": {{close}} * 1.025,
  "stop_loss": {{close}} * 0.995,
  "indicator_name": "AI Svip 1.7.0.4",
  "timeframe": "5m",
  "strength": "strong",
  "notes": "SPY 5min signal at {{time}}"
}
```

**Alert Name:** "AI Svip - SPY - 5m - BUY"
**Condition:** AI Svip 1.7.0.4 generates long signal
**Trigger:** Once Per Bar Close

Repeat for 15m, 30m, and 1h timeframes!

---

## 📞 Support

If signals still don't appear after following this guide:

1. Check browser console for errors
2. Verify Supabase connection
3. Test webhook with cURL command
4. Review TradingView alert history

---

## ✅ Quick Checklist

- [ ] Webhook URL copied correctly
- [ ] Alert created in TradingView
- [ ] JSON message format is valid
- [ ] All required fields present
- [ ] Action is "BUY" or "SELL" (uppercase)
- [ ] Webhook checkbox is enabled
- [ ] Alert is active (not expired)
- [ ] Tested and verified signal received
- [ ] Symbol matches filter in app
- [ ] Auto-refresh enabled in app

---

**🎉 Once configured, your AI Svip signals will automatically flow from TradingView to your application in real-time!**
