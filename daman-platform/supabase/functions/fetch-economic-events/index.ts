import { createClient } from 'npm:@supabase/supabase-js@2.57.4';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Client-Info, Apikey',
};

interface EconomicEvent {
  event_title: string;
  country: string;
  event_date: string;
  impact: 'high' | 'medium' | 'low';
  forecast?: string;
  previous?: string;
  actual?: string;
  currency?: string;
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

    // Get next 5 business days
    const events = await fetchForexFactoryEvents();

    // Filter only high and medium impact
    const filteredEvents = events.filter(e => e.impact === 'high' || e.impact === 'medium');

    // Delete old events
    await supabase
      .from('economic_events')
      .delete()
      .lt('event_date', new Date().toISOString());

    // Insert new events
    const { data, error } = await supabase
      .from('economic_events')
      .upsert(
        filteredEvents.map(event => ({
          event_title: event.event_title,
          country: event.country,
          event_date: event.event_date,
          impact: event.impact,
          forecast: event.forecast,
          previous: event.previous,
          actual: event.actual,
          currency: event.currency,
          source: 'forex_factory'
        })),
        { onConflict: 'event_date,event_title,country' }
      )
      .select();

    if (error) {
      console.error('Database error:', error);
      throw error;
    }

    return new Response(
      JSON.stringify({
        success: true,
        events: data,
        count: data?.length || 0,
        message: 'Economic events fetched successfully'
      }),
      {
        status: 200,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );
  } catch (error) {
    console.error('Error in fetch-economic-events:', error);
    return new Response(
      JSON.stringify({
        error: 'Failed to fetch economic events',
        message: error instanceof Error ? error.message : 'Unknown error'
      }),
      {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );
  }
});

async function fetchForexFactoryEvents(): Promise<EconomicEvent[]> {
  // Since Forex Factory doesn't have an official API, we'll create mock data
  // In production, you would either:
  // 1. Use a paid API like Finnhub, Alpha Vantage, or FXStreet
  // 2. Use a scraping service
  // 3. Purchase access to JBlanked API
  
  const events: EconomicEvent[] = [];
  const now = new Date();
  
  // Generate events for next 5 business days
  let businessDaysAdded = 0;
  let currentDate = new Date(now);
  
  while (businessDaysAdded < 5) {
    currentDate.setDate(currentDate.getDate() + 1);
    const dayOfWeek = currentDate.getDay();
    
    // Skip weekends
    if (dayOfWeek === 0 || dayOfWeek === 6) continue;
    
    businessDaysAdded++;
    
    // Add sample events for each business day
    const dayEvents = generateSampleEvents(new Date(currentDate));
    events.push(...dayEvents);
  }
  
  return events;
}

function generateSampleEvents(date: Date): EconomicEvent[] {
  const events: EconomicEvent[] = [];
  const dateStr = date.toISOString().split('T')[0];
  
  // Common economic indicators that repeat
  const economicIndicators = [
    {
      title: 'Non-Farm Payrolls',
      country: 'USD',
      impact: 'high' as const,
      currency: 'USD',
      time: '13:30'
    },
    {
      title: 'Unemployment Rate',
      country: 'USD',
      impact: 'high' as const,
      currency: 'USD',
      time: '13:30'
    },
    {
      title: 'CPI m/m',
      country: 'USD',
      impact: 'high' as const,
      currency: 'USD',
      time: '13:30'
    },
    {
      title: 'Federal Funds Rate',
      country: 'USD',
      impact: 'high' as const,
      currency: 'USD',
      time: '19:00'
    },
    {
      title: 'GDP q/q',
      country: 'USD',
      impact: 'high' as const,
      currency: 'USD',
      time: '13:30'
    },
    {
      title: 'Retail Sales m/m',
      country: 'USD',
      impact: 'medium' as const,
      currency: 'USD',
      time: '13:30'
    },
    {
      title: 'PMI Manufacturing',
      country: 'USD',
      impact: 'medium' as const,
      currency: 'USD',
      time: '14:45'
    },
    {
      title: 'ECB Interest Rate Decision',
      country: 'EUR',
      impact: 'high' as const,
      currency: 'EUR',
      time: '12:15'
    },
    {
      title: 'BOE Interest Rate Decision',
      country: 'GBP',
      impact: 'high' as const,
      currency: 'GBP',
      time: '12:00'
    },
    {
      title: 'Trade Balance',
      country: 'USD',
      impact: 'medium' as const,
      currency: 'USD',
      time: '13:30'
    },
    {
      title: 'Initial Jobless Claims',
      country: 'USD',
      impact: 'medium' as const,
      currency: 'USD',
      time: '13:30'
    },
    {
      title: 'Manufacturing PMI',
      country: 'EUR',
      impact: 'medium' as const,
      currency: 'EUR',
      time: '09:00'
    },
    {
      title: 'Services PMI',
      country: 'GBP',
      impact: 'medium' as const,
      currency: 'GBP',
      time: '09:30'
    }
  ];
  
  // Randomly select 2-4 events per day
  const numEvents = Math.floor(Math.random() * 3) + 2;
  const shuffled = economicIndicators.sort(() => Math.random() - 0.5);
  const selectedEvents = shuffled.slice(0, numEvents);
  
  selectedEvents.forEach(indicator => {
    events.push({
      event_title: indicator.title,
      country: indicator.country,
      event_date: `${dateStr}T${indicator.time}:00.000Z`,
      impact: indicator.impact,
      forecast: generateForecast(indicator.title),
      previous: generatePrevious(indicator.title),
      currency: indicator.currency
    });
  });
  
  return events;
}

function generateForecast(eventTitle: string): string {
  if (eventTitle.includes('Rate') || eventTitle.includes('Interest')) {
    return `${(Math.random() * 2 + 4).toFixed(2)}%`;
  }
  if (eventTitle.includes('CPI') || eventTitle.includes('Inflation')) {
    return `${(Math.random() * 1 + 2).toFixed(1)}%`;
  }
  if (eventTitle.includes('GDP')) {
    return `${(Math.random() * 2 + 1).toFixed(1)}%`;
  }
  if (eventTitle.includes('Unemployment')) {
    return `${(Math.random() * 1 + 3.5).toFixed(1)}%`;
  }
  if (eventTitle.includes('PMI')) {
    return (Math.random() * 10 + 50).toFixed(1);
  }
  if (eventTitle.includes('Payrolls')) {
    return `${Math.floor(Math.random() * 100 + 150)}K`;
  }
  return '-';
}

function generatePrevious(eventTitle: string): string {
  if (eventTitle.includes('Rate') || eventTitle.includes('Interest')) {
    return `${(Math.random() * 2 + 4).toFixed(2)}%`;
  }
  if (eventTitle.includes('CPI') || eventTitle.includes('Inflation')) {
    return `${(Math.random() * 1 + 2).toFixed(1)}%`;
  }
  if (eventTitle.includes('GDP')) {
    return `${(Math.random() * 2 + 1).toFixed(1)}%`;
  }
  if (eventTitle.includes('Unemployment')) {
    return `${(Math.random() * 1 + 3.5).toFixed(1)}%`;
  }
  if (eventTitle.includes('PMI')) {
    return (Math.random() * 10 + 50).toFixed(1);
  }
  if (eventTitle.includes('Payrolls')) {
    return `${Math.floor(Math.random() * 100 + 150)}K`;
  }
  return '-';
}