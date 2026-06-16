# TradingView Webhook Quick Start Guide

## ⚡ 5-Minute Setup

### Step 1: Check Requirements
- ✅ TradingView **Pro/Premium** account ($14.95+/month)
- ✅ Stock Signals app open in browser

### Step 2: Get Webhook URL
1. Open **Stock Signals** tab
2. Click **"Webhook Info"** button
3. Click **"Copy"** to copy webhook URL

### Step 3: Test Connection
1. Click green **"🧪 Test"** button
2. Verify test signal appears in table below
3. If test fails, check browser console (F12)

### Step 4: Create TradingView Alert
1. Open TradingView chart
2. Press **Alt+A** (or click ⏰ icon)
3. Set your alert condition
4. **CRITICAL:** Check ☑ **"Webhook URL"** checkbox
5. Paste webhook URL in field
6. Copy this JSON into "Message" field:

```json
{
  "ticker": "{{ticker}}",
  "signal_type": "BUY",
  "price": {{close}},
  "timeframe": "{{interval}}",
  "indicator": "Your Indicator Name",
  "strategy": "Your Strategy Name"
}
```

7. Click **"Create"**

### Step 5: Verify Working
- Alert fires in TradingView (you see/hear it)
- Within 2-3 seconds, signal appears in Stock Signals
- Done! 🎉

---

## 🚨 Troubleshooting

### Problem: Test button works, but TradingView alerts don't appear

**Solution:** Webhook checkbox not enabled
1. Edit your TradingView alert
2. Verify ☑ **"Webhook URL"** is CHECKED
3. Save alert

### Problem: Getting "Missing required fields" error

**Solution:** JSON format incorrect
- Copy exact JSON from Webhook Info panel
- Don't modify the structure
- Keep quotes around strings
- Remove quotes from {{variables}}

### Problem: Signal shows wrong/missing data

**Solution:** Variable syntax incorrect
- String variables: `"ticker": "{{ticker}}"` (WITH quotes)
- Number variables: `"price": {{close}}` (NO quotes)

### Problem: No signals at all

**Check these:**
1. Do you have TradingView Pro/Premium? (Required!)
2. Is webhook checkbox checked in alert?
3. Is webhook URL correct? (no typos)
4. Is JSON valid? (test at jsonlint.com)
5. Did alert actually fire? (check TradingView alerts list)

---

## 📋 Common Alert Types

### Price Cross Alert
```json
{
  "ticker": "{{ticker}}",
  "signal_type": "BUY",
  "price": {{close}},
  "timeframe": "{{interval}}",
  "indicator": "Price Cross",
  "strategy": "Moving Average Cross"
}
```

### RSI Overbought/Oversold
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

### MACD Signal
```json
{
  "ticker": "{{ticker}}",
  "signal_type": "LONG",
  "price": {{close}},
  "timeframe": "{{interval}}",
  "indicator": "MACD Cross",
  "strategy": "MACD Strategy"
}
```

---

## ✅ Success Checklist

Before asking for help, verify:

- [ ] TradingView Pro/Premium account
- [ ] Test button sends signal successfully
- [ ] Webhook URL copied correctly (no spaces/typos)
- [ ] Webhook checkbox ☑ is CHECKED in TradingView
- [ ] JSON format is valid
- [ ] Alert has fired at least once
- [ ] Stock Signals browser tab is open
- [ ] No errors in browser console (F12)

**Still not working?**
See: `TRADINGVIEW_ALERT_TROUBLESHOOTING_GUIDE.md` for comprehensive solutions.

---

## 🎯 Pro Tips

1. **Use "Once Per Bar Close"** frequency to avoid duplicate signals
2. **Test with immediate-fire alert** (Price > current-1) to verify setup
3. **Keep Stock Signals tab open** for real-time updates
4. **Use descriptive strategy names** to identify signals later
5. **Set stop_loss and take_profit** for better risk management

---

**Need Help?** Open browser console (F12) and check for error messages before requesting support.
