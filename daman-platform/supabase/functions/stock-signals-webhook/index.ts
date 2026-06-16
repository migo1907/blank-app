import 'jsr:@supabase/functions-js/edge-runtime.d.ts';
import { createClient } from 'npm:@supabase/supabase-js@2.39.0';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Client-Info, Apikey',
};

interface StockSignalWebhook {
  ticker: string;
  signal_type: string;
  price: number;
  timeframe?: string;
  indicator?: string;
  strategy?: string;
  stop_loss?: number;
  take_profit?: number;
  message?: string;
  timestamp?: string;
}

Deno.serve(async (req: Request) => {
  console.log('=== WEBHOOK REQUEST RECEIVED ===');
  console.log('Method:', req.method);
  console.log('URL:', req.url);
  console.log('Headers:', Object.fromEntries(req.headers.entries()));
  console.log('Time:', new Date().toISOString());

  if (req.method === 'OPTIONS') {
    return new Response(null, {
      status: 200,
      headers: corsHeaders,
    });
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;

    console.log('Supabase URL:', supabaseUrl);

    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    const rawBody = await req.text();
    console.log('Raw body received:', rawBody);
    console.log('Body length:', rawBody.length);

    // Check if body is empty
    if (!rawBody || rawBody.trim().length === 0) {
      console.error('❌ EMPTY BODY - TradingView sent no data');
      return new Response(
        JSON.stringify({
          success: false,
          error: 'Empty request body. TradingView alert message is missing or empty.',
          solution: 'In TradingView alert settings, add a JSON message in the "Message" field',
          example: {
            ticker: '{{ticker}}',
            signal_type: 'BUY',
            price: '{{close}}',
            timeframe: '{{interval}}'
          },
          received: rawBody,
        }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      );
    }

    let payload: StockSignalWebhook;
    try {
      payload = JSON.parse(rawBody);
      console.log('✅ Parsed payload:', payload);
    } catch (parseError) {
      console.error('❌ JSON parse error:', parseError);
      console.error('Received body:', rawBody);

      return new Response(
        JSON.stringify({
          success: false,
          error: 'Invalid JSON format in TradingView alert message',
          details: parseError instanceof Error ? parseError.message : 'Unknown parse error',
          received: rawBody,
          solution: 'Check your TradingView alert "Message" field. It must be valid JSON.',
          correct_format: '{\n  "ticker": "{{ticker}}",\n  "signal_type": "BUY",\n  "price": {{close}},\n  "timeframe": "{{interval}}"\n}',
          common_mistakes: [
            'Missing quotes around keys or string values',
            'Using quotes around number variables like {{close}}',
            'Trailing commas',
            'Missing closing braces'
          ]
        }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      );
    }

    if (!payload.ticker || !payload.signal_type || !payload.price) {
      console.error('Missing required fields:', {
        has_ticker: !!payload.ticker,
        has_signal_type: !!payload.signal_type,
        has_price: !!payload.price,
      });
      return new Response(
        JSON.stringify({
          success: false,
          error: 'Missing required fields: ticker, signal_type, price',
          received: payload,
        }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      );
    }

    const signalData = {
      ticker: payload.ticker.toUpperCase(),
      signal_type: payload.signal_type.toUpperCase(),
      price: payload.price,
      timeframe: payload.timeframe || '5m',
      indicator: payload.indicator || 'TradingView',
      strategy: payload.strategy || 'Custom Strategy',
      stop_loss: payload.stop_loss || null,
      take_profit: payload.take_profit || null,
      message: payload.message || `${payload.signal_type} signal for ${payload.ticker} at ${payload.price}`,
      timestamp: payload.timestamp || new Date().toISOString(),
      webhook_data: payload,
      is_active: true,
      created_at: new Date().toISOString(),
    };

    console.log('Prepared signal data:', signalData);
    console.log('Inserting into stock_signals table...');

    const { data, error } = await supabase
      .from('stock_signals')
      .insert([signalData])
      .select();

    if (error) {
      console.error('❌ DATABASE ERROR:', error);
      console.error('Error details:', JSON.stringify(error, null, 2));
      return new Response(
        JSON.stringify({
          success: false,
          error: error.message,
          details: error,
        }),
        {
          status: 500,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      );
    }

    console.log('✅ Stock signal inserted successfully:', data);

    return new Response(
      JSON.stringify({
        success: true,
        message: 'Stock signal received and stored successfully',
        data: data[0],
        webhook_url: `${supabaseUrl}/functions/v1/stock-signals-webhook`
      }),
      {
        status: 200,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );

  } catch (error) {
    console.error('❌ WEBHOOK ERROR:', error);
    return new Response(
      JSON.stringify({
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      }),
      {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );
  }
});