-- ═══════════════════════════════════════════════════════════════
-- MIGO SNIPER PRO — Level 2 Supabase Schema
-- Run this in Supabase SQL Editor → New Query
-- ═══════════════════════════════════════════════════════════════

-- 1. Persistent adaptive weights per symbol
CREATE TABLE IF NOT EXISTS model_weights (
    id           SERIAL PRIMARY KEY,
    symbol       TEXT    NOT NULL DEFAULT 'XAUUSD',
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    w1           FLOAT   NOT NULL DEFAULT 1.0,  -- RSI weight
    w2           FLOAT   NOT NULL DEFAULT 1.0,  -- ADX weight
    w3           FLOAT   NOT NULL DEFAULT 1.0,  -- ATR weight
    w4           FLOAT   NOT NULL DEFAULT 1.0,  -- BB% weight
    w5           FLOAT   NOT NULL DEFAULT 1.0,  -- MACD weight
    w6           FLOAT   NOT NULL DEFAULT 1.0,  -- Williams %R weight
    w7           FLOAT   NOT NULL DEFAULT 1.0,  -- CMO weight
    w8           FLOAT   NOT NULL DEFAULT 1.0,  -- EMA-dist weight
    total_wins   INT     NOT NULL DEFAULT 0,
    total_losses INT     NOT NULL DEFAULT 0,
    UNIQUE(symbol)
);

-- Seed initial weights
INSERT INTO model_weights (symbol) VALUES ('XAUUSD')
ON CONFLICT (symbol) DO NOTHING;

-- 2. Trade outcome history — every closed trade
CREATE TABLE IF NOT EXISTS trade_outcomes (
    id             SERIAL PRIMARY KEY,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol         TEXT    NOT NULL DEFAULT 'XAUUSD',
    direction      TEXT    NOT NULL,   -- 'LONG' | 'SHORT'
    entry_price    FLOAT   NOT NULL,
    exit_price     FLOAT   NOT NULL,
    outcome        TEXT    NOT NULL,   -- 'WIN' | 'LOSS' | 'PARTIAL'
    pnl_pct        FLOAT,
    -- Feature snapshot at entry (normalized -1..+1)
    f1_rsi         FLOAT,
    f2_adx         FLOAT,
    f3_atr         FLOAT,
    f4_bb          FLOAT,
    f5_macd        FLOAT,
    f6_willr       FLOAT,
    f7_cmo         FLOAT,
    f8_ema_dist    FLOAT,
    ml_bull_score  FLOAT,
    ml_bear_score  FLOAT,
    news_sentiment FLOAT,   -- -1..+1 at time of entry
    timeframe      TEXT    DEFAULT '5m'
);

CREATE INDEX IF NOT EXISTS trade_outcomes_symbol_idx ON trade_outcomes(symbol);
CREATE INDEX IF NOT EXISTS trade_outcomes_created_idx ON trade_outcomes(created_at DESC);

-- 3. News sentiment cache
CREATE TABLE IF NOT EXISTS news_sentiment (
    id              SERIAL PRIMARY KEY,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source          TEXT,
    headline        TEXT    NOT NULL,
    url             TEXT,
    sentiment_score FLOAT   NOT NULL,  -- -1 (very bearish) .. +1 (very bullish) for XAU
    impact          TEXT    NOT NULL,  -- 'HIGH' | 'MEDIUM' | 'LOW'
    keywords        TEXT[],
    raw_response    TEXT
);

CREATE INDEX IF NOT EXISTS news_sentiment_fetched_idx ON news_sentiment(fetched_at DESC);

-- 4. Generated signals log
CREATE TABLE IF NOT EXISTS signals (
    id            SERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol        TEXT    NOT NULL DEFAULT 'XAUUSD',
    direction     TEXT    NOT NULL,   -- 'LONG' | 'SHORT' | 'NEUTRAL'
    confidence    FLOAT   NOT NULL,  -- 0..1
    ml_score      FLOAT   NOT NULL,
    news_score    FLOAT   NOT NULL,
    combined_score FLOAT  NOT NULL,
    reasoning     TEXT,
    status        TEXT    NOT NULL DEFAULT 'ACTIVE',  -- 'ACTIVE' | 'EXPIRED' | 'TRIGGERED'
    expires_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS signals_created_idx ON signals(created_at DESC);

-- 5. Row-Level Security — enable but allow service role full access
ALTER TABLE model_weights   ENABLE ROW LEVEL SECURITY;
ALTER TABLE trade_outcomes  ENABLE ROW LEVEL SECURITY;
ALTER TABLE news_sentiment  ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals         ENABLE ROW LEVEL SECURITY;

-- Allow service role (backend) full access
CREATE POLICY "service_role_all" ON model_weights   FOR ALL USING (true);
CREATE POLICY "service_role_all" ON trade_outcomes  FOR ALL USING (true);
CREATE POLICY "service_role_all" ON news_sentiment  FOR ALL USING (true);
CREATE POLICY "service_role_all" ON signals         FOR ALL USING (true);
