import { createClient } from 'npm:@supabase/supabase-js@2.57.4';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Client-Info, Apikey',
};

interface StockData {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  open: number;
  high: number;
  low: number;
}

const POPULAR_SYMBOLS = [
  'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK.B', 'JPM', 'V',
  'JNJ', 'WMT', 'PG', 'UNH', 'MA', 'HD', 'BAC', 'DIS', 'ADBE', 'CRM',
  'NFLX', 'CSCO', 'INTC', 'AMD', 'QCOM', 'PYPL', 'PFE', 'NKE', 'KO', 'PEP'
];

async function fetchYahooQuotes(symbols: string[]): Promise<StockData[]> {
  const stockData: StockData[] = [];

  try {
    for (const symbol of symbols) {
      try {
        await new Promise(resolve => setTimeout(resolve, 100));

        const response = await fetch(
          `https://query2.finance.yahoo.com/v8/finance/chart/${symbol}?interval=1m&range=1d`,
          {
            headers: {
              'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
          }
        );

        if (!response.ok) continue;

        const data = await response.json();
        const result = data.chart?.result?.[0];

        if (!result) continue;

        const meta = result.meta;
        const quote = result.indicators?.quote?.[0];

        if (!meta || !quote) continue;

        const currentPrice = meta.regularMarketPrice || quote.close?.[quote.close.length - 1] || 0;
        const previousClose = meta.chartPreviousClose || meta.previousClose || currentPrice;
        const change = currentPrice - previousClose;
        const changePercent = previousClose > 0 ? (change / previousClose) * 100 : 0;

        stockData.push({
          symbol: symbol,
          name: symbol,
          price: currentPrice,
          change,
          change_percent: changePercent,
          volume: meta.regularMarketVolume || 0,
          open: quote.open?.[0] || currentPrice,
          high: quote.high?.[quote.high.length - 1] || currentPrice,
          low: quote.low?.[quote.low.length - 1] || currentPrice
        });
      } catch (error) {
        console.error(`Error fetching Yahoo quote for ${symbol}:`, error);
      }
    }

    console.log(`✅ Yahoo: Fetched ${stockData.length} stock quotes`);
    return stockData;
  } catch (error) {
    console.error('Error fetching Yahoo quotes:', error);
    return [];
  }
}

async function fetchAlpacaQuotes(symbols: string[]): Promise<StockData[]> {
  const alpacaKey = Deno.env.get('ALPACA_API_KEY');
  const alpacaSecret = Deno.env.get('ALPACA_SECRET_KEY');

  if (!alpacaKey || !alpacaSecret) {
    console.error('ALPACA_API_KEY or ALPACA_SECRET_KEY not configured');
    return [];
  }

  const stockData: StockData[] = [];

  try {
    const symbolsParam = symbols.join(',');
    const url = `https://data.alpaca.markets/v2/stocks/snapshots?symbols=${symbolsParam}`;

    const response = await fetch(url, {
      headers: {
        'APCA-API-KEY-ID': alpacaKey,
        'APCA-API-SECRET-KEY': alpacaSecret,
        'Accept': 'application/json'
      }
    });

    if (!response.ok) {
      console.error(`Alpaca API error: ${response.status}`);
      return [];
    }

    const data = await response.json();

    for (const [symbol, snapshot] of Object.entries(data)) {
      const snap = snapshot as any;
      const currentPrice = snap.latestTrade?.p || snap.minuteBar?.c || 0;
      const previousClose = snap.prevDailyBar?.c || snap.dailyBar?.o || currentPrice;
      const change = currentPrice - previousClose;
      const changePercent = previousClose > 0 ? (change / previousClose) * 100 : 0;

      stockData.push({
        symbol: symbol,
        name: symbol,
        price: currentPrice,
        change,
        change_percent: changePercent,
        volume: snap.dailyBar?.v || 0,
        open: snap.dailyBar?.o || currentPrice,
        high: snap.dailyBar?.h || currentPrice,
        low: snap.dailyBar?.l || currentPrice
      });
    }

    console.log(`✅ Alpaca: Fetched ${stockData.length} stock quotes`);
    return stockData;
  } catch (error) {
    console.error('Error fetching Alpaca quotes:', error);
    return [];
  }
}

async function fetchTradierQuotes(symbols: string[]): Promise<StockData[]> {
  const tradierToken = Deno.env.get('TRADIER_API_TOKEN');
  const tradierUrl = Deno.env.get('TRADIER_API_URL') || 'https://sandbox.tradier.com';

  if (!tradierToken) {
    console.error('TRADIER_API_TOKEN not configured');
    return [];
  }

  const stockData: StockData[] = [];
  const batchSize = 50;

  for (let i = 0; i < symbols.length; i += batchSize) {
    const batch = symbols.slice(i, i + batchSize);
    const symbolsParam = batch.join(',');

    try {
      const response = await fetch(
        `${tradierUrl}/v1/markets/quotes?symbols=${symbolsParam}&greeks=false`,
        {
          headers: {
            'Authorization': `Bearer ${tradierToken}`,
            'Accept': 'application/json',
          },
        }
      );

      if (!response.ok) {
        console.error(`Tradier API error for batch: ${response.status}`);
        continue;
      }

      const data = await response.json();
      const quotes = data.quotes?.quote;

      if (!quotes) {
        console.error('No quotes data available');
        continue;
      }

      const quotesArray = Array.isArray(quotes) ? quotes : [quotes];

      for (const quote of quotesArray) {
        if (!quote.symbol || quote.type === 'index') continue;

        const currentPrice = quote.last || quote.close || 0;
        const previousClose = quote.prevclose || 0;
        const change = currentPrice - previousClose;
        const changePercent = previousClose > 0 ? (change / previousClose) * 100 : 0;

        stockData.push({
          symbol: quote.symbol.toUpperCase(),
          name: quote.description || quote.symbol,
          price: currentPrice,
          change: change,
          change_percent: changePercent,
          volume: quote.volume || 0,
          open: quote.open || currentPrice,
          high: quote.high || currentPrice,
          low: quote.low || currentPrice,
        });
      }
    } catch (error) {
      console.error(`Error fetching batch:`, error);
    }
  }

  console.log(`✅ Tradier: Fetched ${stockData.length} stock quotes`);
  return stockData;
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 200, headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    const url = new URL(req.url);
    const symbolsParam = url.searchParams.get('symbols');
    const mode = url.searchParams.get('mode') || 'fetch';

    let symbols: string[] = [];

    if (mode === 'movers') {
      symbols = POPULAR_SYMBOLS;
    } else if (symbolsParam) {
      symbols = symbolsParam.split(',').map(s => s.trim()).filter(Boolean);
    }

    if (symbols.length === 0) {
      return new Response(
        JSON.stringify({ error: 'No symbols provided' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    console.log(`🔄 Fetching quotes for ${symbols.length} symbols`);
    let stockData = await fetchAlpacaQuotes(symbols);
    let source = 'alpaca';

    if (stockData.length === 0) {
      console.log('⚠️ Alpaca failed, trying Yahoo');
      stockData = await fetchYahooQuotes(symbols);
      source = 'yahoo';
    }

    if (stockData.length === 0) {
      console.log('⚠️ Yahoo failed, falling back to Tradier');
      stockData = await fetchTradierQuotes(symbols);
      source = 'tradier';
    }

    if (mode === 'update' && stockData.length > 0) {
      const { error } = await supabase
        .from('stock_prices')
        .upsert(
          stockData.map(stock => ({
            symbol: stock.symbol,
            price: stock.price,
            change_percent: stock.change_percent,
            volume: stock.volume,
            updated_at: new Date().toISOString(),
          })),
          { onConflict: 'symbol' }
        );

      if (error) {
        console.error('Error updating stock prices:', error);
      } else {
        console.log(`✅ Updated ${stockData.length} stock prices in database`);
      }
    }

    // Format response for movers mode
    if (mode === 'movers') {
      const gainers = [...stockData]
        .filter(s => s.change_percent > 0)
        .sort((a, b) => b.change_percent - a.change_percent)
        .slice(0, 10)
        .map(s => ({
          symbol: s.symbol,
          name: s.name,
          price: s.price,
          change_percent: s.change_percent,
          volume: s.volume
        }));

      const losers = [...stockData]
        .filter(s => s.change_percent < 0)
        .sort((a, b) => a.change_percent - b.change_percent)
        .slice(0, 10)
        .map(s => ({
          symbol: s.symbol,
          name: s.name,
          price: s.price,
          change_percent: s.change_percent,
          volume: s.volume
        }));

      const active = [...stockData]
        .sort((a, b) => b.volume - a.volume)
        .slice(0, 10)
        .map(s => ({
          symbol: s.symbol,
          name: s.name,
          price: s.price,
          change_percent: s.change_percent,
          volume: s.volume
        }));

      return new Response(
        JSON.stringify({
          success: true,
          gainers,
          losers,
          active,
          source,
          timestamp: Date.now(),
        }),
        {
          status: 200,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      );
    }

    return new Response(
      JSON.stringify({
        success: true,
        data: stockData,
        source,
        count: stockData.length,
        timestamp: Date.now(),
      }),
      {
        status: 200,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );
  } catch (error) {
    console.error('Edge function error:', error);

    return new Response(
      JSON.stringify({
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      }),
      {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );
  }
});
