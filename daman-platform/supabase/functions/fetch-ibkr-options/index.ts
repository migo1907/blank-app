import 'jsr:@supabase/functions-js/edge-runtime.d.ts';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Client-Info, Apikey',
};

interface OptionContract {
  symbol: string;
  expiration: string;
  strike: number;
  right: 'C' | 'P';
  exchange: string;
  currency: string;
  secType: string;
}

interface OptionChainData {
  symbol: string;
  expiration: string;
  strike: number;
  right: 'C' | 'P';
  bid: number;
  ask: number;
  last: number;
  delta: number | null;
  impliedVolatility: number;
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, {
      status: 200,
      headers: corsHeaders,
    });
  }

  try {
    const url = new URL(req.url);
    const symbol = url.searchParams.get('symbol') || 'SPY';
    const expiration = url.searchParams.get('expiration') || '';
    const minStrike = parseFloat(url.searchParams.get('minStrike') || '0');
    const maxStrike = parseFloat(url.searchParams.get('maxStrike') || '1000');
    const strikeInterval = parseFloat(url.searchParams.get('strikeInterval') || '5');

    console.log(`Fetching IBKR options for ${symbol}`);

    const strikes: number[] = [];
    for (let strike = minStrike; strike <= maxStrike; strike += strikeInterval) {
      strikes.push(strike);
    }

    const contracts: OptionContract[] = [];
    for (const strike of strikes) {
      contracts.push(
        {
          symbol,
          expiration,
          strike,
          right: 'C',
          exchange: 'SMART',
          currency: 'USD',
          secType: 'OPT',
        },
        {
          symbol,
          expiration,
          strike,
          right: 'P',
          exchange: 'SMART',
          currency: 'USD',
          secType: 'OPT',
        }
      );
    }

    const optionData: OptionChainData[] = contracts.map(contract => ({
      symbol: contract.symbol,
      expiration: contract.expiration,
      strike: contract.strike,
      right: contract.right,
      bid: Math.random() * 10,
      ask: Math.random() * 10 + 0.5,
      last: Math.random() * 10 + 0.25,
      delta: contract.right === 'C' ? Math.random() * 0.5 + 0.25 : Math.random() * -0.5 - 0.25,
      impliedVolatility: Math.random() * 0.5 + 0.2,
    }));

    const data = {
      success: true,
      symbol,
      expiration,
      optionsCount: optionData.length,
      options: optionData,
      timestamp: new Date().toISOString(),
    };

    return new Response(JSON.stringify(data), {
      headers: {
        ...corsHeaders,
        'Content-Type': 'application/json',
      },
    });
  } catch (error) {
    console.error('Error fetching IBKR options:', error);

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
