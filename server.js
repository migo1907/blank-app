import 'dotenv/config';
import express from 'express';
import Anthropic from '@anthropic-ai/sdk';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = process.env.PORT || 3001;

app.use(express.json());

const PROMPT = `You are a professional gold (XAUUSD) trading analyst for IC Markets. \
Generate comprehensive real-time analysis. Use web search for current price and news.

Return ONLY valid JSON (no markdown, no backticks) in this exact structure:
{
  "timestamp": "2026-05-20T16:30:00Z",
  "currentPrice": 4485.50,
  "priceChange": -12.30,
  "trend": "BEARISH",
  "timeframes": {
    "daily": "Strong bearish, below all MAs",
    "h4": "Downtrend intact, testing support",
    "h1": "Consolidating near lows",
    "m15": "Short-term bounce possible"
  },
  "keyLevels": {
    "resistance": [4510, 4530, 4566, 4600],
    "support": [4476, 4464, 4450, 4423]
  },
  "fvg": [
    {"zone": "4520-4530", "type": "bearish", "priority": 1},
    {"zone": "4642-4667", "type": "bearish", "priority": 2}
  ],
  "supplyDemand": {
    "supply": [
      {"zone": "4520-4566", "strength": "strong"},
      {"zone": "4600-4650", "strength": "medium"}
    ],
    "demand": [
      {"zone": "4464-4480", "strength": "medium"},
      {"zone": "4420-4450", "strength": "strong"}
    ]
  },
  "smartMoney": {
    "liquidityZones": [
      "BSL at 4600 (buy-side liquidity grab expected)",
      "SSL at 4450 swept"
    ],
    "orderBlocks": [
      "Bearish OB: 4520-4566 (fresh supply)",
      "Bullish OB: 4420-4450 (extreme demand)"
    ]
  },
  "news": [
    {
      "event": "FOMC Minutes",
      "time": "22:00 Dubai",
      "impact": "high",
      "expected": "Hawkish tone likely, USD strength"
    }
  ],
  "entrySetups": [
    {
      "type": "SHORT",
      "confidence": 85,
      "entry": "4520-4530",
      "stop": 4545,
      "targets": [4476, 4464, 4450],
      "reason": "Bounce into resistance + FVG + supply OB confluence",
      "timeframe": "2-4 hours"
    }
  ],
  "movementExpectation": {
    "direction": "DOWN",
    "targetRange": "4450-4464",
    "timeframe": "4-6 hours",
    "probability": 75
  }
}

Return ONLY the JSON, nothing else.`;

app.post('/api/analysis', async (req, res) => {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: 'ANTHROPIC_API_KEY environment variable is not set' });
  }

  try {
    const client = new Anthropic({ apiKey });
    const response = await client.messages.create({
      model: 'claude-sonnet-4-6',
      max_tokens: 4000,
      tools: [{ type: 'web_search_20250305', name: 'web_search' }],
      messages: [{ role: 'user', content: PROMPT }],
    });

    const text = response.content
      .filter(b => b.type === 'text')
      .map(b => b.text)
      .join('');

    const match = text.match(/\{[\s\S]*\}/);
    if (!match) throw new Error('No JSON found in Claude response');

    res.json(JSON.parse(match[0]));
  } catch (err) {
    console.error('Analysis error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

// Serve built frontend in production
if (process.env.NODE_ENV === 'production') {
  app.use(express.static(join(__dirname, 'dist')));
  app.get('*', (_req, res) => {
    res.sendFile(join(__dirname, 'dist', 'index.html'));
  });
}

app.listen(PORT, () => {
  console.log(`API server → http://localhost:${PORT}`);
});
