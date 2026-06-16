import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from 'npm:@supabase/supabase-js@2.57.4';

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Info, Apikey",
};

interface FundamentalData {
  symbol: string;
  marketCap: number;
  enterpriseValue: number;
  revenue: number;
  totalDebt: number;
  totalCash: number;
  sharesOutstanding: number;
  peRatio: number;
  pbRatio: number;
  evToRevenue: number;
  evToEbitda: number;
  debtToEquity: number;
  currentRatio: number;
  quickRatio: number;
  returnOnEquity: number;
  returnOnAssets: number;
  profitMargin: number;
  operatingMargin: number;
  revenueGrowth: number;
  earningsGrowth: number;
  bookValuePerShare: number;
  priceToBook: number;
  forwardPE: number;
  pegRatio: number;
  dividendYield: number;
  payoutRatio: number;
  beta: number;
  fiftyTwoWeekHigh: number;
  fiftyTwoWeekLow: number;
  industry: string;
  sector: string;
  updated_at?: string;
}

async function fetchYahooFundamentals(symbol: string): Promise<FundamentalData | null> {
  try {
    const modules = [
      'financialData',
      'defaultKeyStatistics',
      'summaryDetail',
      'price',
      'assetProfile',
      'incomeStatementHistory',
      'balanceSheetHistory'
    ].join(',');

    const url = `https://query2.finance.yahoo.com/v10/finance/quoteSummary/${symbol}?modules=${modules}`;

    const response = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });

    if (!response.ok) {
      console.error(`Yahoo API error for ${symbol}: ${response.status}`);
      return null;
    }

    const data = await response.json();
    const result = data.quoteSummary?.result?.[0];

    if (!result) {
      console.error(`No fundamental data found for ${symbol}`);
      return null;
    }

    const financialData = result.financialData || {};
    const keyStats = result.defaultKeyStatistics || {};
    const summaryDetail = result.summaryDetail || {};
    const price = result.price || {};
    const assetProfile = result.assetProfile || {};

    const getValue = (obj: any) => obj?.raw ?? obj?.fmt ?? 0;

    const fundamentalData: FundamentalData = {
      symbol: symbol.toUpperCase(),
      marketCap: getValue(price.marketCap) || getValue(summaryDetail.marketCap) || 0,
      enterpriseValue: getValue(keyStats.enterpriseValue) || getValue(financialData.enterpriseValue) || 0,
      revenue: getValue(financialData.totalRevenue) || 0,
      totalDebt: getValue(financialData.totalDebt) || 0,
      totalCash: getValue(financialData.totalCash) || 0,
      sharesOutstanding: getValue(keyStats.sharesOutstanding) || getValue(price.sharesOutstanding) || 0,
      peRatio: getValue(summaryDetail.trailingPE) || getValue(keyStats.trailingPE) || 0,
      pbRatio: getValue(keyStats.priceToBook) || 0,
      evToRevenue: getValue(keyStats.enterpriseToRevenue) || 0,
      evToEbitda: getValue(keyStats.enterpriseToEbitda) || 0,
      debtToEquity: getValue(financialData.debtToEquity) || 0,
      currentRatio: getValue(financialData.currentRatio) || 0,
      quickRatio: getValue(financialData.quickRatio) || 0,
      returnOnEquity: getValue(financialData.returnOnEquity) || 0,
      returnOnAssets: getValue(financialData.returnOnAssets) || 0,
      profitMargin: getValue(financialData.profitMargins) || 0,
      operatingMargin: getValue(financialData.operatingMargins) || 0,
      revenueGrowth: getValue(financialData.revenueGrowth) || 0,
      earningsGrowth: getValue(financialData.earningsGrowth) || 0,
      bookValuePerShare: getValue(keyStats.bookValue) || 0,
      priceToBook: getValue(keyStats.priceToBook) || 0,
      forwardPE: getValue(summaryDetail.forwardPE) || getValue(keyStats.forwardPE) || 0,
      pegRatio: getValue(keyStats.pegRatio) || 0,
      dividendYield: getValue(summaryDetail.dividendYield) || getValue(keyStats.dividendYield) || 0,
      payoutRatio: getValue(summaryDetail.payoutRatio) || getValue(keyStats.payoutRatio) || 0,
      beta: getValue(summaryDetail.beta) || getValue(keyStats.beta) || 0,
      fiftyTwoWeekHigh: getValue(summaryDetail.fiftyTwoWeekHigh) || 0,
      fiftyTwoWeekLow: getValue(summaryDetail.fiftyTwoWeekLow) || 0,
      industry: assetProfile.industry || 'Unknown',
      sector: assetProfile.sector || 'Unknown'
    };

    console.log(`✅ Fetched fundamentals for ${symbol}: Revenue=$${(fundamentalData.revenue/1e9).toFixed(2)}B, EV/S=${fundamentalData.evToRevenue.toFixed(2)}`);
    return fundamentalData;

  } catch (error) {
    console.error(`Error fetching fundamentals for ${symbol}:`, error);
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
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    const url = new URL(req.url);
    const symbolsParam = url.searchParams.get('symbols');

    if (!symbolsParam) {
      return new Response(
        JSON.stringify({
          success: false,
          error: 'No symbols provided. Use ?symbols=AAPL,MSFT'
        }),
        {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        }
      );
    }

    const symbols = symbolsParam.split(',').map(s => s.trim().toUpperCase()).filter(Boolean);

    if (symbols.length === 0) {
      return new Response(
        JSON.stringify({ success: false, error: 'No valid symbols provided' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    console.log(`📊 Fetching fundamentals for ${symbols.length} symbols: ${symbols.join(', ')}`);

    const fundamentalDataArray: FundamentalData[] = [];

    for (const symbol of symbols) {
      const data = await fetchYahooFundamentals(symbol);
      if (data) {
        fundamentalDataArray.push(data);
      }
      await new Promise(resolve => setTimeout(resolve, 200));
    }

    if (fundamentalDataArray.length === 0) {
      return new Response(
        JSON.stringify({
          success: false,
          error: 'No fundamental data could be retrieved',
          attempted: symbols.length
        }),
        { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const timestamp = new Date().toISOString();
    const dataWithTimestamp = fundamentalDataArray.map(d => ({
      ...d,
      updated_at: timestamp
    }));

    const { error: upsertError } = await supabase
      .from('fundamental_data')
      .upsert(dataWithTimestamp, { onConflict: 'symbol' });

    if (upsertError) {
      console.error('Error storing fundamentals in database:', upsertError);
    } else {
      console.log(`✅ Stored ${fundamentalDataArray.length} fundamental records in database`);
    }

    return new Response(
      JSON.stringify({
        success: true,
        data: fundamentalDataArray,
        count: fundamentalDataArray.length,
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
