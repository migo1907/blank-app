const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Info, Apikey",
};

interface MarketQuote {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  high: number;
  low: number;
  open: number;
  timestamp: number;
}

async function fetchYahooQuotes(symbols: string[]): Promise<MarketQuote[]> {
  const quotes: MarketQuote[] = [];

  for (const symbol of symbols) {
    try {
      let yahooSymbol = symbol;
      if (symbol === 'SPX') yahooSymbol = '^GSPC';
      if (symbol === 'DJI') yahooSymbol = '^DJI';
      if (symbol === 'IXIC') yahooSymbol = '^IXIC';
      if (symbol === 'RUT') yahooSymbol = '^RUT';

      const response = await fetch(
        `https://query1.finance.yahoo.com/v8/finance/chart/${yahooSymbol}?interval=1d&range=1d`,
        {
          headers: {
            'User-Agent': 'Mozilla/5.0',
          },
        }
      );

      if (!response.ok) continue;

      const data = await response.json();
      const result = data.chart?.result?.[0];
      const meta = result?.meta;
      const quote = result?.indicators?.quote?.[0];

      if (!meta || !quote) continue;

      const currentPrice = meta.regularMarketPrice || quote.close?.[quote.close.length - 1] || 0;
      const previousClose = meta.previousClose || meta.chartPreviousClose || 0;
      const change = currentPrice - previousClose;
      const changePercent = previousClose > 0 ? (change / previousClose) * 100 : 0;

      const volume = quote.volume?.[quote.volume.length - 1] || meta.regularMarketVolume || 0;
      const high = quote.high?.[quote.high.length - 1] || meta.regularMarketDayHigh || currentPrice;
      const low = quote.low?.[quote.low.length - 1] || meta.regularMarketDayLow || currentPrice;
      const open = quote.open?.[0] || meta.regularMarketOpen || currentPrice;

      quotes.push({
        symbol: symbol,
        name: meta.longName || meta.symbol || symbol,
        price: currentPrice,
        change: change,
        changePercent: changePercent,
        volume: volume,
        high: high,
        low: low,
        open: open,
        timestamp: Date.now(),
      });
    } catch (error) {
      console.error(`Error fetching Yahoo quote for ${symbol}:`, error);
    }
  }

  console.log(`✅ Yahoo Finance: Fetched ${quotes.length} market quotes`);
  return quotes;
}

async function fetchTradierQuotes(symbols: string[]): Promise<MarketQuote[]> {
  const tradierToken = Deno.env.get('TRADIER_API_TOKEN');
  const tradierUrl = Deno.env.get('TRADIER_API_URL') || 'https://sandbox.tradier.com';

  if (!tradierToken || tradierToken === 'YOUR_TRADIER_API_TOKEN_HERE') {
    console.log('TRADIER_API_TOKEN not configured, falling back to Yahoo Finance');
    return fetchYahooQuotes(symbols);
  }

  const quotes: MarketQuote[] = [];
  const symbolsParam = symbols.map(s => {
    if (s === 'SPX') return '$SPX.X';
    if (s === 'DJI' || s === '^DJI') return '$DJI.X';
    if (s === 'IXIC' || s === '^IXIC') return '$COMP.X';
    if (s === 'RUT' || s === '^RUT') return '$RUT.X';
    return s;
  }).join(',');

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
      console.error(`Tradier API error: ${response.status}`);
      return fetchYahooQuotes(symbols);
    }

    const data = await response.json();
    const tradierQuotes = Array.isArray(data.quotes?.quote)
      ? data.quotes.quote
      : data.quotes?.quote
        ? [data.quotes.quote]
        : [];

    for (const tq of tradierQuotes) {
      let symbol = tq.symbol;
      if (symbol === '$SPX.X') symbol = 'SPX';
      if (symbol === '$DJI.X') symbol = 'DJI';
      if (symbol === '$COMP.X') symbol = 'IXIC';
      if (symbol === '$RUT.X') symbol = 'RUT';

      const price = tq.last || tq.close || 0;
      const previousClose = tq.prevclose || tq.close || 0;
      const change = tq.change || (price - previousClose);
      const changePercent = tq.change_percentage || (previousClose > 0 ? (change / previousClose) * 100 : 0);

      quotes.push({
        symbol: symbol,
        name: tq.description || symbol,
        price: price,
        change: change,
        changePercent: changePercent,
        volume: tq.volume || 0,
        high: tq.high || price,
        low: tq.low || price,
        open: tq.open || price,
        timestamp: Date.now(),
      });
    }
  } catch (error) {
    console.error('Tradier API error:', error);
    return fetchYahooQuotes(symbols);
  }

  console.log(`✅ Tradier: Fetched ${quotes.length} market quotes`);
  return quotes;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, {
      status: 200,
      headers: corsHeaders,
    });
  }

  try {
    let symbols: string[] = [];

    if (req.method === "POST") {
      const body = await req.json();
      symbols = body.symbols || [];
    } else {
      const url = new URL(req.url);
      const symbolsParam = url.searchParams.get('symbols');
      if (symbolsParam) {
        symbols = symbolsParam.split(',').map(s => s.trim()).filter(Boolean);
      }
    }

    if (!symbols || symbols.length === 0) {
      return new Response(
        JSON.stringify({ error: 'Missing symbols parameter' }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      );
    }

    console.log(`🔄 Fetching market quotes for: ${symbols.join(', ')}`);
    const quotes = await fetchTradierQuotes(symbols);

    const tradierToken = Deno.env.get('TRADIER_API_TOKEN');
    const source = (!tradierToken || tradierToken === 'YOUR_TRADIER_API_TOKEN_HERE')
      ? 'yahoo_finance'
      : 'tradier';

    return new Response(
      JSON.stringify({
        success: quotes.length > 0,
        quotes: quotes,
        source: source,
        timestamp: new Date().toISOString(),
        count: quotes.length,
        message: quotes.length === 0 ? 'No quotes found for the requested symbols. Please verify the symbols are valid.' : undefined,
      }),
      {
        status: quotes.length > 0 ? 200 : 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );
  } catch (error) {
    console.error('Error in fetch-market-data:', error);
    return new Response(
      JSON.stringify({ error: 'Internal server error', details: error.message }),
      {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );
  }
});