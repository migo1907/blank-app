# 🎯 TradingView Signals Integration - Complete Guide

**Feature:** Real-time Buy/Sell Signals Screener
**Integration:** TradingView Alerts → Webhook → Database → Live Display
**Status:** ✅ **FULLY OPERATIONAL**

---

## 📊 OVERVIEW

The TradingView Signals Screener displays real-time buy and sell signals from your TradingView indicators. Signals are sent via webhook and displayed in a professional table with entry price, targets, stop-loss, and risk-reward ratios.

### **Key Features:**

✅ **Real-Time Signal Reception** - Webhook receives TradingView alerts instantly
✅ **Professional Display** - Clean table with all signal details
✅ **Target Tracking** - Two profit targets (T1, T2) with potential gain %
✅ **Stop-Loss Management** - Risk management with stop-loss levels
✅ **Risk-Reward Analysis** - Automatic R:R ratio calculation
✅ **Signal Strength** - Weak, Moderate, Strong classification
✅ **Auto-Refresh** - Optional 30-second auto-refresh
✅ **Live Updates** - Real-time updates via Supabase subscriptions
✅ **Export to CSV** - Download signals for analysis
✅ **Filter Options** - View all, buy only, or sell only signals

---

## 🗄️ DATABASE SCHEMA

### **Table: `tradingview_signals`**

```sql
CREATE TABLE tradingview_signals (
  id UUID PRIMARY KEY,
  symbol TEXT NOT NULL,                    -- Stock symbol (AAPL, MSFT, etc.)
  action signal_action NOT NULL,           -- BUY or SELL
  price NUMERIC NOT NULL,                  -- Entry price
  target1 NUMERIC NOT NULL,                -- First profit target
  target2 NUMERIC NOT NULL,                -- Second profit target
  stop_loss NUMERIC NOT NULL,              -- Stop loss level
  indicator_name TEXT,                     -- Name of your indicator
  timeframe TEXT,                          -- Chart timeframe (1h, 4h, 1D)
  strength signal_strength,                -- weak, moderate, strong
  status signal_status,                    -- active, target1_hit, etc.
  triggered_at TIMESTAMPTZ,                -- When signal was generated
  closed_at TIMESTAMPTZ,                   -- When signal was closed
  pnl_percent NUMERIC,                     -- Profit/Loss %
  notes TEXT,                              -- Additional notes
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### **View: `active_signals`**

Displays only active signals with calculated metrics:
- `potential_gain_t1` - % gain to reach Target 1
- `potential_gain_t2` - % gain to reach Target 2
- `risk_percent` - % risk to stop-loss
- Auto-calculated based on entry price and action (BUY/SELL)

### **View: `signal_performance`**

Aggregates performance metrics per symbol:
- Total signals
- Winning vs losing signals
- Average P&L percentage
- Total profit/loss
- Last signal timestamp

---

## 🔌 WEBHOOK ENDPOINT

### **URL:**
```
https://[your-project].supabase.co/functions/v1/tradingview-webhook
```

### **Method:** `POST`

### **Headers:**
```
Content-Type: application/json
```

### **Request Body:**
```json
{
  "symbol": "AAPL",              // Required: Stock symbol
  "action": "BUY",               // Required: BUY or SELL
  "price": 178.50,               // Required: Entry price
  "target1": 185.00,             // Required: First target
  "target2": 192.00,             // Required: Second target
  "stop_loss": 172.00,           // Required: Stop loss
  "indicator_name": "RSI+MACD",  // Optional: Your indicator name
  "timeframe": "1D",             // Optional: Chart timeframe
  "strength": "strong",          // Optional: weak, moderate, strong
  "notes": "Bullish divergence"  // Optional: Additional notes
}
```

### **Response:**
```json
{
  "success": true,
  "message": "Signal received and stored successfully",
  "data": {
    "id": "uuid",
    "symbol": "AAPL",
    "action": "BUY",
    // ... full signal data
  }
}
```

---

## 🎨 TRADINGVIEW SETUP - STEP BY STEP

### **Step 1: Create Your Indicator Alert**

1. Open TradingView chart
2. Add your indicator to the chart
3. Click the **Alert** button (🔔) or press `Alt + A`
4. Configure alert conditions based on your indicator

### **Step 2: Configure Alert Settings**

**Condition:**
- Set to trigger on your indicator's signal
- Example: "RSI crosses above 30" or "MACD histogram > 0"

**Options:**
- **Once Per Bar Close** ← RECOMMENDED (avoids false signals)
- OR "Once Per Bar" if you want faster alerts

**Expiration:**
- Set to "Open-ended" for continuous monitoring

### **Step 3: Set Webhook URL**

In the **Notifications** tab:

**Webhook URL:**
```
https://[your-project].supabase.co/functions/v1/tradingview-webhook
```

Replace `[your-project]` with your actual Supabase project URL.

### **Step 4: Configure Alert Message**

**For BUY Signals:**
```json
{
  "symbol": "{{ticker}}",
  "action": "BUY",
  "price": {{close}},
  "target1": {{close}} * 1.05,
  "target2": {{close}} * 1.10,
  "stop_loss": {{close}} * 0.97,
  "indicator_name": "Your Indicator Name",
  "timeframe": "{{interval}}",
  "strength": "strong",
  "notes": "BUY signal from {{ticker}} on {{interval}} chart"
}
```

**For SELL Signals:**
```json
{
  "symbol": "{{ticker}}",
  "action": "SELL",
  "price": {{close}},
  "target1": {{close}} * 0.95,
  "target2": {{close}} * 0.90,
  "stop_loss": {{close}} * 1.03,
  "indicator_name": "Your Indicator Name",
  "timeframe": "{{interval}}",
  "strength": "strong",
  "notes": "SELL signal from {{ticker}} on {{interval}} chart"
}
```

### **TradingView Placeholders:**

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{ticker}}` | Stock symbol | AAPL |
| `{{close}}` | Current close price | 178.50 |
| `{{open}}` | Current open price | 177.80 |
| `{{high}}` | Current high price | 179.20 |
| `{{low}}` | Current low price | 177.30 |
| `{{volume}}` | Current volume | 52341234 |
| `{{interval}}` | Chart timeframe | 1D, 4H, 1H |
| `{{time}}` | Bar timestamp | 2025-10-29T08:00:00Z |

### **Advanced Target Calculation:**

**Dynamic Targets Based on ATR:**
```json
{
  "symbol": "{{ticker}}",
  "action": "BUY",
  "price": {{close}},
  "target1": {{close}} + ({{atr}} * 1.5),
  "target2": {{close}} + ({{atr}} * 3.0),
  "stop_loss": {{close}} - ({{atr}} * 1.0),
  "indicator_name": "ATR-Based Strategy",
  "timeframe": "{{interval}}",
  "strength": "moderate"
}
```

**Percentage-Based Targets:**
```json
{
  "symbol": "{{ticker}}",
  "action": "BUY",
  "price": {{close}},
  "target1": {{close}} * 1.03,     // +3% target
  "target2": {{close}} * 1.06,     // +6% target
  "stop_loss": {{close}} * 0.98,   // -2% stop
  "indicator_name": "3% / 6% Targets",
  "timeframe": "{{interval}}",
  "strength": "moderate"
}
```

### **Step 5: Save and Activate**

1. Name your alert (e.g., "AAPL RSI Buy Signal")
2. Click **Create**
3. Verify alert appears in your Alerts panel
4. Test by triggering a manual signal

---

## 📱 USING THE SIGNALS SCREENER

### **Accessing the Screener**

**Desktop:**
- Click "TradingView Signals" in the main navigation

**Mobile:**
- Tap the ⚡ **Signals** icon in the bottom navigation bar

### **Interface Overview**

#### **1. Stats Cards (Top)**
- **Active Signals** - Total number of current signals
- **Buy Signals** - Number of BUY signals
- **Sell Signals** - Number of SELL signals
- **Avg R:R Ratio** - Average Risk:Reward across all signals

#### **2. Filter Buttons**
- **All Signals** - Show both BUY and SELL
- **Buy Only** - Filter to show only BUY signals
- **Sell Only** - Filter to show only SELL signals

#### **3. Controls (Top Right)**
- **Auto-Refresh ON/OFF** - Toggle 30-second auto-refresh
- **Refresh** - Manual refresh button
- **Export CSV** - Download signals to CSV file

#### **4. Signals Table**

**Columns:**
- **Symbol** - Stock ticker and timeframe
- **Action** - BUY (green) or SELL (red) badge
- **Entry Price** - Price when signal triggered
- **Target 1** - First profit target with % gain
- **Target 2** - Second profit target with % gain
- **Stop Loss** - Stop loss level with % risk
- **R:R Ratio** - Risk:Reward ratio (color-coded)
  - Green: ≥ 2:1 (excellent)
  - Yellow: ≥ 1:1 (acceptable)
  - Red: < 1:1 (poor)
- **Strength** - Signal strength badge
- **Time** - When signal was triggered

---

## 🎯 EXAMPLE SCENARIOS

### **Scenario 1: RSI Oversold + MACD Cross**

**TradingView Alert Message:**
```json
{
  "symbol": "{{ticker}}",
  "action": "BUY",
  "price": {{close}},
  "target1": {{close}} * 1.05,
  "target2": {{close}} * 1.10,
  "stop_loss": {{close}} * 0.97,
  "indicator_name": "RSI Divergence + MACD Cross",
  "timeframe": "{{interval}}",
  "strength": "strong",
  "notes": "RSI oversold ({{rsi}}) with bullish MACD crossover"
}
```

**Result in Screener:**
```
Symbol: AAPL (1D)
Action: BUY (green badge)
Entry: $178.50
Target 1: $187.43 (+5.00%)
Target 2: $196.35 (+10.00%)
Stop Loss: $173.15 (-3.00%)
R:R Ratio: 3.33:1 (green - excellent)
Strength: STRONG
```

---

### **Scenario 2: Breakout Above Resistance**

**TradingView Alert Message:**
```json
{
  "symbol": "{{ticker}}",
  "action": "BUY",
  "price": {{close}},
  "target1": {{high}},
  "target2": {{high}} * 1.08,
  "stop_loss": {{low}},
  "indicator_name": "Resistance Breakout",
  "timeframe": "{{interval}}",
  "strength": "moderate",
  "notes": "Breaking out above {{high}} resistance with volume {{volume}}"
}
```

---

### **Scenario 3: Overbought Reversal**

**TradingView Alert Message:**
```json
{
  "symbol": "{{ticker}}",
  "action": "SELL",
  "price": {{close}},
  "target1": {{close}} * 0.95,
  "target2": {{close}} * 0.90,
  "stop_loss": {{close}} * 1.03,
  "indicator_name": "Overbought RSI + Bearish Engulfing",
  "timeframe": "{{interval}}",
  "strength": "strong",
  "notes": "RSI above 70 ({{rsi}}) with bearish reversal candle"
}
```

**Result in Screener:**
```
Symbol: NVDA (4H)
Action: SELL (red badge)
Entry: $495.30
Target 1: $470.54 (+5.00%)
Target 2: $445.77 (+10.00%)
Stop Loss: $510.16 (-3.00%)
R:R Ratio: 3.33:1 (green)
Strength: STRONG
```

---

## 🔄 REAL-TIME UPDATES

### **Automatic Updates:**

The screener updates automatically when:
1. ✅ New signal arrives via webhook
2. ✅ Signal status changes
3. ✅ Signal is closed or expires

**Update Mechanisms:**
- **WebSocket Subscription** - Real-time updates via Supabase Realtime
- **Auto-Refresh (Optional)** - 30-second polling when enabled
- **Manual Refresh** - Click refresh button anytime

### **Signal Lifecycle:**

```
1. ACTIVE → Signal just triggered, displayed in screener
2. TARGET1_HIT → First target reached (manual update)
3. TARGET2_HIT → Second target reached (manual update)
4. STOPPED_OUT → Stop loss hit (manual update)
5. EXPIRED → Signal older than 7 days (auto)
6. CLOSED → Manually closed
```

---

## 📊 PERFORMANCE TRACKING

### **Signal Performance View**

Query to see performance per symbol:
```sql
SELECT * FROM signal_performance;
```

**Returns:**
- Total signals per symbol
- Win rate (% of profitable signals)
- Average P&L percentage
- Total profit/loss
- Last signal timestamp

### **Custom Performance Queries**

**Win Rate by Timeframe:**
```sql
SELECT
  timeframe,
  COUNT(*) as total,
  COUNT(*) FILTER (WHERE status IN ('target1_hit', 'target2_hit')) as wins,
  ROUND(COUNT(*) FILTER (WHERE status IN ('target1_hit', 'target2_hit'))::numeric / COUNT(*) * 100, 2) as win_rate
FROM tradingview_signals
WHERE status != 'active'
GROUP BY timeframe;
```

**Best Performing Symbols:**
```sql
SELECT
  symbol,
  COUNT(*) as signals,
  AVG(pnl_percent) as avg_pnl,
  SUM(pnl_percent) as total_pnl
FROM tradingview_signals
WHERE status NOT IN ('active', 'expired')
GROUP BY symbol
ORDER BY total_pnl DESC
LIMIT 10;
```

---

## 🛠️ ADVANCED FEATURES

### **1. Signal Expiration**

Signals automatically expire after 7 days:
```sql
-- Run this as a scheduled job (daily)
SELECT expire_old_signals();
```

### **2. Multiple Indicators**

Run multiple TradingView alerts with different indicators:
- RSI Indicator → Set `indicator_name: "RSI Strategy"`
- MACD Indicator → Set `indicator_name: "MACD Strategy"`
- Volume Indicator → Set `indicator_name: "Volume Breakout"`

Filter in SQL:
```sql
SELECT * FROM active_signals WHERE indicator_name = 'RSI Strategy';
```

### **3. Custom Strength Logic**

In your TradingView alert, dynamically set strength:
```json
{
  "symbol": "{{ticker}}",
  "action": "BUY",
  "price": {{close}},
  "target1": {{close}} * 1.05,
  "target2": {{close}} * 1.10,
  "stop_loss": {{close}} * 0.97,
  "indicator_name": "Dynamic Strength",
  "timeframe": "{{interval}}",
  "strength": "{{rsi}} > 60 ? 'strong' : {{rsi}} > 50 ? 'moderate' : 'weak'",
  "notes": "RSI: {{rsi}}"
}
```

### **4. Signal Notifications**

Set up email/SMS notifications when signals arrive:
```typescript
// Add to webhook function
if (payload.strength === 'strong') {
  await sendNotification({
    to: 'your-email@example.com',
    subject: `Strong ${payload.action} Signal: ${payload.symbol}`,
    body: `Entry: $${payload.price}, Target: $${payload.target1}`
  });
}
```

---

## 🎓 BEST PRACTICES

### **1. Risk-Reward Ratio**

**Minimum Recommended:** 2:1 (risk $1 to make $2)

**Example:**
- Entry: $100
- Stop Loss: $97 (risk: $3 or 3%)
- Target 1: $106 (reward: $6 or 6%)
- R:R Ratio: 6/3 = 2:1 ✅

### **2. Position Sizing**

Calculate position size based on risk:
```javascript
const accountSize = 10000;  // $10,000 account
const riskPercent = 1;      // Risk 1% per trade
const riskAmount = accountSize * (riskPercent / 100);  // $100 risk

const entryPrice = 178.50;
const stopLoss = 172.00;
const riskPerShare = entryPrice - stopLoss;  // $6.50

const shares = Math.floor(riskAmount / riskPerShare);  // 15 shares
```

### **3. Signal Validation**

Before taking a trade, validate:
- ✅ R:R ratio ≥ 2:1
- ✅ Signal strength is moderate or strong
- ✅ Timeframe matches your trading style
- ✅ Entry price is still valid (not too far from current)
- ✅ Volume confirms the move

### **4. Multiple Timeframe Confirmation**

Use alerts on multiple timeframes:
- **1D chart** - Primary trend direction
- **4H chart** - Entry timing
- **1H chart** - Precise entry point

Only take trades when higher timeframes confirm!

---

## 🔒 SECURITY & ACCESS

### **Webhook Security:**

The webhook is **public** (no JWT verification) to allow TradingView access.

**Protection Mechanisms:**
1. ✅ Input validation (required fields)
2. ✅ Action validation (only BUY/SELL allowed)
3. ✅ Symbol sanitization (uppercase conversion)
4. ✅ Service role database access (users can't directly insert)

**RLS Policies:**
```sql
-- Anyone can READ signals (public data)
-- Only SERVICE ROLE can INSERT/UPDATE signals (via webhook)
```

### **Additional Security (Optional):**

Add API key validation:
```typescript
const webhookSecret = Deno.env.get('WEBHOOK_SECRET');
const providedSecret = req.headers.get('X-Webhook-Secret');

if (providedSecret !== webhookSecret) {
  return new Response('Unauthorized', { status: 401 });
}
```

Then in TradingView, add custom header:
```
X-Webhook-Secret: your-secret-key-here
```

---

## 📈 MONITORING & MAINTENANCE

### **Daily Checks:**

1. **Check Signal Count:**
```sql
SELECT COUNT(*) FROM tradingview_signals WHERE status = 'active';
```

2. **Check Recent Signals:**
```sql
SELECT * FROM active_signals ORDER BY triggered_at DESC LIMIT 10;
```

3. **Expire Old Signals:**
```sql
SELECT expire_old_signals();
```

### **Weekly Reviews:**

1. **Performance by Symbol:**
```sql
SELECT * FROM signal_performance ORDER BY total_signals DESC;
```

2. **Win Rate Analysis:**
```sql
SELECT
  ROUND(COUNT(*) FILTER (WHERE status IN ('target1_hit', 'target2_hit'))::numeric /
        COUNT(*)::numeric * 100, 2) as win_rate
FROM tradingview_signals
WHERE status != 'active';
```

3. **Average R:R Achieved:**
```sql
SELECT
  AVG(potential_gain_t2 / ABS(risk_percent)) as avg_rr
FROM active_signals;
```

---

## 🐛 TROUBLESHOOTING

### **Problem: Signals not appearing**

**Check 1:** Verify webhook received signal
```bash
# Check Supabase edge function logs
```

**Check 2:** Verify database insert
```sql
SELECT * FROM tradingview_signals ORDER BY created_at DESC LIMIT 5;
```

**Check 3:** Verify TradingView alert is firing
- Check TradingView Alerts panel
- Verify "Webhook sent" in alert history

---

### **Problem: Wrong target calculations**

**BUY Signal:**
- Target 1 should be > Entry Price
- Target 2 should be > Target 1
- Stop Loss should be < Entry Price

**SELL Signal:**
- Target 1 should be < Entry Price
- Target 2 should be < Target 1
- Stop Loss should be > Entry Price

**Fix in TradingView alert:**
```json
// BUY
"target1": {{close}} * 1.05,  // 5% above entry
"stop_loss": {{close}} * 0.97,  // 3% below entry

// SELL
"target1": {{close}} * 0.95,  // 5% below entry
"stop_loss": {{close}} * 1.03,  // 3% above entry
```

---

### **Problem: Webhook returns error**

**Error 400 - Missing fields:**
- Verify all required fields are in JSON
- Check for typos in field names
- Ensure valid JSON format (no trailing commas)

**Error 500 - Database error:**
- Check Supabase project is active
- Verify database connection
- Check RLS policies allow insert

---

## 📚 SAMPLE DATA

The database includes 8 sample signals for testing:

1. **AAPL** - BUY - Strong signal, RSI divergence
2. **MSFT** - BUY - Moderate signal, breakout
3. **NVDA** - SELL - Strong signal, overbought
4. **TSLA** - BUY - Moderate signal, golden cross
5. **GOOGL** - BUY - Strong signal, volume spike
6. **META** - SELL - Moderate signal, double top
7. **AMD** - BUY - Strong signal, cup and handle
8. **AMZN** - BUY - Moderate signal, pennant breakout

Test the screener with these signals before connecting TradingView!

---

## 🎯 SUCCESS METRICS

**What to Track:**
- ✅ Win Rate (target 60%+)
- ✅ Average R:R Ratio (target 2:1+)
- ✅ Average P&L per trade (target +2%+)
- ✅ Maximum drawdown (target <10%)
- ✅ Signals per week (track consistency)

**Review Period:**
- Daily: Check active signals
- Weekly: Review closed signals, calculate win rate
- Monthly: Performance analysis, strategy adjustment

---

## 🚀 CONCLUSION

The TradingView Signals Screener is now **fully operational** and ready to receive your trading signals!

**Next Steps:**
1. ✅ Set up your TradingView alerts
2. ✅ Test with sample signals
3. ✅ Configure your webhook URL
4. ✅ Start receiving real-time signals
5. ✅ Track performance and refine strategy

**Status:** 🟢 **PRODUCTION READY**

---

**Need Help?**
- Check Supabase function logs for webhook errors
- Verify database permissions and RLS policies
- Test webhook with cURL or Postman first
- Review TradingView alert message syntax

**Happy Trading! 📈**
