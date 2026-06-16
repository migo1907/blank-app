import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Info, Apikey",
};

interface OHLCVData {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

async function fetchAlpacaIntradayData(symbol: string, interval: string, days: number = 1): Promise<OHLCVData[]> {
  const alpacaKey = Deno.env.get('ALPACA_API_KEY');
  const alpacaSecret = Deno.env.get('ALPACA_SECRET_KEY');

  if (!alpacaKey || !alpacaSecret) {
    console.log('⚠️ Alpaca not configured, skipping');
    return [];
  }

  try {
    const timeframeMap: { [key: string]: string } = {
      '1m': '1Min',
      '5m': '5Min',
      '15m': '15Min',
      '1h': '1Hour',
      '1d': '1Day'
    };

    const timeframe = timeframeMap[interval] || '5Min';
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - (days + 7));

    const start = startDate.toISOString().split('T')[0];
    const end = new Date().toISOString().split('T')[0];

    const url = `https://data.alpaca.markets/v2/stocks/${symbol}/bars?timeframe=${timeframe}&start=${start}&end=${end}&limit=10000&feed=iex`;

    const response = await fetch(url, {
      headers: {
        'APCA-API-KEY-ID': alpacaKey,
        'APCA-API-SECRET-KEY': alpacaSecret,
      },
    });

    if (!response.ok) {
      console.error(`Alpaca bars API error: ${response.status}`);
      return [];
    }

    const data = await response.json();
    const bars = data.bars;

    if (!bars || !Array.isArray(bars) || bars.length === 0) {
      console.log(`No Alpaca bars data for ${symbol}`);
      return [];
    }

    const ohlcvData: OHLCVData[] = bars.map((bar: any) => ({
      timestamp: new Date(bar.t).getTime(),
      open: bar.o || 0,
      high: bar.h || 0,
      low: bar.l || 0,
      close: bar.c || 0,
      volume: bar.v || 0,
    }));

    console.log(`✅ Alpaca: Fetched ${ohlcvData.length} intraday bars for ${symbol}`);
    return ohlcvData;
  } catch (error) {
    console.error('Error fetching Alpaca bars:', error);
    return [];
  }
}

async function fetchTradierIntradayData(symbol: string, interval: string): Promise<OHLCVData[]> {
  const tradierToken = Deno.env.get('TRADIER_API_TOKEN');
  const tradierUrl = Deno.env.get('TRADIER_API_URL') || 'https://sandbox.tradier.com';

  if (!tradierToken) {
    console.error('TRADIER_API_TOKEN not configured');
    return [];
  }

  const tradierSymbol = symbol === 'SPX' ? '$SPX.X' : symbol;
  const intervalMap: { [key: string]: string } = {
    '1m': '1min',
    '5m': '5min',
    '15m': '15min',
    '1h': '1hour',
    '1d': 'daily'
  };

  const tradierInterval = intervalMap[interval] || '5min';
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - 30);
  const endDate = new Date();

  try {
    const response = await fetch(
      `${tradierUrl}/v1/markets/timesales?symbol=${tradierSymbol}&interval=${tradierInterval}&start=${startDate.toISOString().split('T')[0]}&end=${endDate.toISOString().split('T')[0]}`,
      {
        headers: {
          'Authorization': `Bearer ${tradierToken}`,
          'Accept': 'application/json',
        },
      }
    );

    if (!response.ok) {
      console.error(`Tradier timesales API error: ${response.status}`);
      return [];
    }

    const data = await response.json();
    const series = data.series?.data;

    if (!series || !Array.isArray(series)) {
      console.error('No timesales data available');
      return [];
    }

    const ohlcvData: OHLCVData[] = series.map((item: any) => ({
      timestamp: new Date(item.time).getTime(),
      open: item.open || item.price || 0,
      high: item.high || item.price || 0,
      low: item.low || item.price || 0,
      close: item.close || item.price || 0,
      volume: item.volume || 0,
    }));

    console.log(`✅ Tradier: Fetched ${ohlcvData.length} intraday bars for ${symbol}`);
    return ohlcvData;
  } catch (error) {
    console.error('Error fetching Tradier timesales:', error);
    return [];
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
    const symbol = url.searchParams.get('symbol');
    const interval = url.searchParams.get('interval') || '5m';

    if (!symbol) {
      return new Response(
        JSON.stringify({
          success: false,
          error: 'Missing required parameter: symbol',
        }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      );
    }

    const days = parseInt(url.searchParams.get('days') || '1');

    console.log(`🔄 Fetching intraday data for ${symbol} (${interval})`);

    let data = await fetchAlpacaIntradayData(symbol, interval, days);
    let source = 'alpaca';

    if (data.length === 0) {
      console.log('⚠️ Alpaca failed, trying Tradier');
      data = await fetchTradierIntradayData(symbol, interval);
      source = 'tradier';
    }

    if (data.length === 0) {
      return new Response(
        JSON.stringify({
          success: false,
          error: 'No intraday data available from any source',
        }),
        {
          status: 500,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      );
    }

    return new Response(
      JSON.stringify({
        success: true,
        data: data,
        dataPoints: data.length,
        source: source,
        symbol: symbol,
        interval: interval,
        count: data.length,
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
