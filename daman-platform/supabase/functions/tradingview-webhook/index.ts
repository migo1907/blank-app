import 'jsr:@supabase/functions-js/edge-runtime.d.ts';
import { createClient } from 'npm:@supabase/supabase-js@2.39.0';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Client-Info, Apikey',
};

interface TradingViewWebhook {
  symbol: string;
  action: 'BUY' | 'SELL';
  price: number;
  target1: number;
  target2: number;
  stop_loss: number;
  indicator_name?: string;
  timeframe?: string;
  strength?: 'weak' | 'moderate' | 'strong';
  notes?: string;
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, {
      status: 200,
      headers: corsHeaders,
    });
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    
    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    const payload: TradingViewWebhook = await req.json();

    // Validate required fields
    if (!payload.symbol || !payload.action || !payload.price || 
        !payload.target1 || !payload.target2 || !payload.stop_loss) {
      return new Response(
        JSON.stringify({ 
          success: false, 
          error: 'Missing required fields: symbol, action, price, target1, target2, stop_loss' 
        }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      );
    }

    // Validate action is BUY or SELL
    if (payload.action !== 'BUY' && payload.action !== 'SELL') {
      return new Response(
        JSON.stringify({ 
          success: false, 
          error: 'Action must be either BUY or SELL' 
        }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      );
    }

    // Insert signal into database
    const { data, error } = await supabase
      .from('tradingview_signals')
      .insert([{
        symbol: payload.symbol.toUpperCase(),
        action: payload.action,
        price: payload.price,
        target1: payload.target1,
        target2: payload.target2,
        stop_loss: payload.stop_loss,
        indicator_name: payload.indicator_name || 'TradingView Custom Indicator',
        timeframe: payload.timeframe || '1D',
        strength: payload.strength || 'moderate',
        status: 'active',
        notes: payload.notes || '',
        triggered_at: new Date().toISOString(),
      }])
      .select();

    if (error) {
      console.error('Database error:', error);
      return new Response(
        JSON.stringify({ success: false, error: error.message }),
        {
          status: 500,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      );
    }

    console.log('Signal inserted:', data);

    return new Response(
      JSON.stringify({ 
        success: true, 
        message: 'Signal received and stored successfully',
        data: data[0]
      }),
      {
        status: 200,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );

  } catch (error) {
    console.error('Webhook error:', error);
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
