const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Info, Apikey",
};

interface OptionPrice {
  strike: number;
  bid: number;
  ask: number;
  last: number;
  mid: number;
  volume: number;
  openInterest: number;
  impliedVolatility: number;
  delta?: number;
  gamma?: number;
  theta?: number;
  vega?: number;
}

interface OptionsChainResponse {
  underlying: string;
  underlyingPrice: number;
  timestamp: string;
  calls: OptionPrice[];
  puts: OptionPrice[];
}

async function fetchAlpacaOptionsChain(symbol: string): Promise<OptionsChainResponse | null> {
  const alpacaKey = Deno.env.get('ALPACA_API_KEY');
  const alpacaSecret = Deno.env.get('ALPACA_SECRET_KEY');

  if (!alpacaKey || !alpacaSecret) {
    console.log('⚠️ Alpaca not configured');
    return null;
  }

  try {
    const snapshotUrl = `https://data.alpaca.markets/v1beta1/options/snapshots/${symbol}?feed=indicative&limit=500`;

    const response = await fetch(snapshotUrl, {
      headers: {
        'APCA-API-KEY-ID': alpacaKey,
        'APCA-API-SECRET-KEY': alpacaSecret,
      },
    });

    if (!response.ok) {
      console.error(`Alpaca options API error: ${response.status}`);
      return null;
    }

    const data = await response.json();
    const snapshots = data.snapshots;

    if (!snapshots || Object.keys(snapshots).length === 0) {
      console.log(`No Alpaca options data for ${symbol}`);
      return null;
    }

    const latestQuoteUrl = `https://data.alpaca.markets/v2/stocks/${symbol}/snapshot`;
    const quoteResponse = await fetch(latestQuoteUrl, {
      headers: {
        'APCA-API-KEY-ID': alpacaKey,
        'APCA-API-SECRET-KEY': alpacaSecret,
      },
    });

    let underlyingPrice = 0;
    if (quoteResponse.ok) {
      const quoteData = await quoteResponse.json();
      underlyingPrice = quoteData.latestTrade?.p || quoteData.prevDailyBar?.c || 0;
    }

    const calls: OptionPrice[] = [];
    const puts: OptionPrice[] = [];

    for (const [contractSymbol, snapshot] of Object.entries(snapshots)) {
      const snap: any = snapshot;
      const latestQuote = snap.latestQuote;

      if (!latestQuote) continue;

      const parts = contractSymbol.match(/([A-Z]+)(\d{6})([CP])(\d{8})/);
      if (!parts) continue;

      const [, , , optionType, strikeStr] = parts;
      const strike = parseInt(strikeStr) / 1000;

      const bid = latestQuote.bp || 0;
      const ask = latestQuote.ap || 0;
      const last = snap.latestTrade?.p || 0;
      const mid = bid > 0 && ask > 0 ? (bid + ask) / 2 : last;

      const optionData: OptionPrice = {
        strike,
        bid,
        ask,
        last,
        mid,
        volume: snap.dailyBar?.v || 0,
        openInterest: 0,
        impliedVolatility: snap.impliedVolatility || 0,
      };

      if (optionType === 'C') {
        calls.push(optionData);
      } else {
        puts.push(optionData);
      }
    }

    calls.sort((a, b) => a.strike - b.strike);
    puts.sort((a, b) => a.strike - b.strike);

    console.log(`✅ Alpaca: Fetched ${calls.length} calls, ${puts.length} puts for ${symbol}`);

    return {
      underlying: symbol,
      underlyingPrice,
      timestamp: new Date().toISOString(),
      calls,
      puts
    };
  } catch (error) {
    console.error('Error fetching Alpaca options chain:', error);
    return null;
  }
}

async function fetchYahooOptionsChain(symbol: string): Promise<OptionsChainResponse | null> {
  try {
    const yahooSymbol = symbol === 'SPX' ? '^SPX' : symbol;

    const quoteResponse = await fetch(
      `https://query2.finance.yahoo.com/v8/finance/chart/${yahooSymbol}?interval=1m&range=1d`,
      {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
      }
    );

    if (!quoteResponse.ok) {
      console.error(`Yahoo quote API error: ${quoteResponse.status}`);
      return null;
    }

    const quoteData = await quoteResponse.json();
    const meta = quoteData.chart?.result?.[0]?.meta;
    const underlyingPrice = meta?.regularMarketPrice || 0;

    if (!underlyingPrice) {
      console.error('No underlying price available');
      return null;
    }

    const optionsResponse = await fetch(
      `https://query2.finance.yahoo.com/v7/finance/options/${yahooSymbol}`,
      {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
      }
    );

    if (!optionsResponse.ok) {
      console.error(`Yahoo options API error: ${optionsResponse.status}`);
      return null;
    }

    const optionsData = await optionsResponse.json();
    const result = optionsData.optionChain?.result?.[0];

    if (!result) {
      console.error('No options data available');
      return null;
    }

    const options = result.options?.[0];
    if (!options) {
      console.error('No options contracts available');
      return null;
    }

    const calls: OptionPrice[] = (options.calls || []).map((call: any) => {
      const bid = call.bid || 0;
      const ask = call.ask || 0;
      const mid = bid > 0 && ask > 0 ? (bid + ask) / 2 : call.lastPrice || 0;

      return {
        strike: call.strike,
        bid,
        ask,
        last: call.lastPrice || 0,
        mid,
        volume: call.volume || 0,
        openInterest: call.openInterest || 0,
        impliedVolatility: call.impliedVolatility || 0
      };
    }).sort((a: OptionPrice, b: OptionPrice) => a.strike - b.strike);

    const puts: OptionPrice[] = (options.puts || []).map((put: any) => {
      const bid = put.bid || 0;
      const ask = put.ask || 0;
      const mid = bid > 0 && ask > 0 ? (bid + ask) / 2 : put.lastPrice || 0;

      return {
        strike: put.strike,
        bid,
        ask,
        last: put.lastPrice || 0,
        mid,
        volume: put.volume || 0,
        openInterest: put.openInterest || 0,
        impliedVolatility: put.impliedVolatility || 0
      };
    }).sort((a: OptionPrice, b: OptionPrice) => a.strike - b.strike);

    console.log(`✅ Yahoo: Fetched ${calls.length} calls, ${puts.length} puts for ${symbol}`);

    return {
      underlying: symbol,
      underlyingPrice,
      timestamp: new Date().toISOString(),
      calls,
      puts
    };
  } catch (error) {
    console.error('Error fetching Yahoo options chain:', error);
    return null;
  }
}

async function fetchTradierOptionsChain(symbol: string): Promise<OptionsChainResponse | null> {
  try {
    const tradierToken = Deno.env.get('TRADIER_API_TOKEN');
    const tradierUrl = Deno.env.get('TRADIER_API_URL') || 'https://sandbox.tradier.com';

    if (!tradierToken) {
      console.error('TRADIER_API_TOKEN not configured');
      return null;
    }

    const tradierSymbol = symbol === 'SPX' ? '$SPX.X' : symbol;

    const quotesResponse = await fetch(
      `${tradierUrl}/v1/markets/quotes?symbols=${tradierSymbol}`,
      {
        headers: {
          'Authorization': `Bearer ${tradierToken}`,
          'Accept': 'application/json',
        },
      }
    );

    if (!quotesResponse.ok) {
      console.error(`Tradier quotes API error: ${quotesResponse.status}`);
      return null;
    }

    const quotesData = await quotesResponse.json();
    const quote = quotesData.quotes?.quote;
    const underlyingPrice = quote?.last || quote?.close || 0;

    if (!underlyingPrice) {
      console.error('No underlying price available');
      return null;
    }

    const expirationsResponse = await fetch(
      `${tradierUrl}/v1/markets/options/expirations?symbol=${tradierSymbol}`,
      {
        headers: {
          'Authorization': `Bearer ${tradierToken}`,
          'Accept': 'application/json',
        },
      }
    );

    if (!expirationsResponse.ok) {
      console.error(`Tradier expirations API error: ${expirationsResponse.status}`);
      return null;
    }

    const expirationsData = await expirationsResponse.json();
    const expirations = expirationsData.expirations?.date;

    if (!expirations || expirations.length === 0) {
      console.error('No expirations available');
      return null;
    }

    const nearestExpiration = Array.isArray(expirations) ? expirations[0] : expirations;

    const chainResponse = await fetch(
      `${tradierUrl}/v1/markets/options/chains?symbol=${tradierSymbol}&expiration=${nearestExpiration}&greeks=true`,
      {
        headers: {
          'Authorization': `Bearer ${tradierToken}`,
          'Accept': 'application/json',
        },
      }
    );

    if (!chainResponse.ok) {
      console.error(`Tradier chain API error: ${chainResponse.status}`);
      return null;
    }

    const chainData = await chainResponse.json();
    const options = chainData.options?.option;

    if (!options) {
      console.error('No options data available');
      return null;
    }

    const optionsArray = Array.isArray(options) ? options : [options];

    const calls: OptionPrice[] = optionsArray
      .filter((opt: any) => opt.option_type === 'call')
      .map((call: any) => {
        const bid = call.bid || 0;
        const ask = call.ask || 0;
        const mid = bid > 0 && ask > 0 ? (bid + ask) / 2 : call.last || 0;

        return {
          strike: call.strike,
          bid: bid,
          ask: ask,
          last: call.last || 0,
          mid: mid,
          volume: call.volume || 0,
          openInterest: call.open_interest || 0,
          impliedVolatility: call.greeks?.mid_iv || 0,
        };
      })
      .sort((a: OptionPrice, b: OptionPrice) => a.strike - b.strike);

    const puts: OptionPrice[] = optionsArray
      .filter((opt: any) => opt.option_type === 'put')
      .map((put: any) => {
        const bid = put.bid || 0;
        const ask = put.ask || 0;
        const mid = bid > 0 && ask > 0 ? (bid + ask) / 2 : put.last || 0;

        return {
          strike: put.strike,
          bid: bid,
          ask: ask,
          last: put.last || 0,
          mid: mid,
          volume: put.volume || 0,
          openInterest: put.open_interest || 0,
          impliedVolatility: put.greeks?.mid_iv || 0,
        };
      })
      .sort((a: OptionPrice, b: OptionPrice) => a.strike - b.strike);

    console.log(`✅ Tradier: Fetched ${calls.length} calls, ${puts.length} puts for ${symbol}`);

    return {
      underlying: symbol,
      underlyingPrice: underlyingPrice,
      timestamp: new Date().toISOString(),
      calls,
      puts,
    };
  } catch (error) {
    console.error('Error fetching Tradier options chain:', error);
    return null;
  }
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, {
      status: 200,
      headers: corsHeaders,
    });
  }

  try {
    const url = new URL(req.url);
    const symbol = url.searchParams.get('symbol') || 'SPX';

    console.log(`🔄 Fetching options chain for ${symbol}`);

    let optionsData = await fetchAlpacaOptionsChain(symbol);
    let source = 'alpaca';

    if (!optionsData) {
      console.log('⚠️ Alpaca failed, trying Yahoo');
      optionsData = await fetchYahooOptionsChain(symbol);
      source = 'yahoo';
    }

    if (!optionsData) {
      console.log('⚠️ Yahoo failed, falling back to Tradier');
      optionsData = await fetchTradierOptionsChain(symbol);
      source = 'tradier';
    }

    if (!optionsData) {
      return new Response(
        JSON.stringify({
          success: false,
          error: 'Failed to fetch options data from all providers',
        }),
        {
          status: 500,
          headers: {
            ...corsHeaders,
            'Content-Type': 'application/json',
          },
        }
      );
    }

    return new Response(
      JSON.stringify({
        success: true,
        data: optionsData,
        source,
        timestamp: Date.now(),
      }),
      {
        status: 200,
        headers: {
          ...corsHeaders,
          'Content-Type': 'application/json',
        },
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
        headers: {
          ...corsHeaders,
          'Content-Type': 'application/json',
        },
      }
    );
  }
});
