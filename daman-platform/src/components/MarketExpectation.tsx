import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, RefreshCw, Target, DollarSign, Shield, Zap, BarChart3, Activity, AlertCircle, Brain, Sparkles } from 'lucide-react';
import { supabase } from '../lib/supabase';

interface MarketExpectationData {
  date: string;
  symbol: string;
  analysis: string;
  resistance_levels: number[];
  support_levels: number[];
  entry_long: number;
  exit_long: number;
  stop_loss_long: number;
  risk_reward_long: number;
  entry_fade: number;
  exit_fade: number;
  stop_loss_fade: number;
  risk_reward_fade: number;
  key_insights: string[];
  market_bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  confidence: number;
  generated_at: string;
}

export default function MarketExpectation() {
  const [expectation, setExpectation] = useState<MarketExpectationData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastGenerated, setLastGenerated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const generateExpectation = async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Try to fetch SPY price data
      const { data: priceData } = await supabase
        .from('stock_prices')
        .select('*')
        .eq('symbol', 'SPY')
        .order('timestamp', { ascending: false })
        .limit(100);

      // Use fallback data if no price data exists
      const latestPrice = priceData?.[0]?.price ? Number(priceData[0].price) : 580.00;
      const high52w = priceData && priceData.length > 0
        ? Math.max(...priceData.map(d => Number(d.high || d.price || 0)))
        : 600.00;
      const low52w = priceData && priceData.length > 0
        ? Math.min(...priceData.map(d => Number(d.low || d.price || 0)))
        : 450.00;

      const currentDate = new Date().toISOString().split('T')[0];

      const prompt = `You are an expert day trader analyzing SPY (S&P 500 ETF) for intraday trading.

Current SPY Data:
- Current Price: $${latestPrice}
- 52-Week High: $${high52w}
- 52-Week Low: $${low52w}
- Date: ${currentDate}

Provide a comprehensive intraday analysis with:

1. Market Expectation & Bias (Bullish/Bearish/Neutral)
2. Key Resistance Levels (3-4 levels above current price)
3. Key Support Levels (3-4 levels below current price)
4. Long Position Setup:
   - Entry Level (ideal buy price at market open)
   - Exit Level (profit target)
   - Stop Loss
   - Risk/Reward Ratio
5. Fade Movement Setup (counter-trend):
   - Entry Level (where to short or fade rallies)
   - Exit Level (where to cover)
   - Stop Loss
   - Risk/Reward Ratio
6. Key Insights (3-5 bullet points with actionable advice)

Format your response as JSON with this exact structure:
{
  "analysis": "Brief market overview and today's expectation",
  "resistance_levels": [level1, level2, level3, level4],
  "support_levels": [level1, level2, level3, level4],
  "entry_long": price,
  "exit_long": price,
  "stop_loss_long": price,
  "risk_reward_long": ratio,
  "entry_fade": price,
  "exit_fade": price,
  "stop_loss_fade": price,
  "risk_reward_fade": ratio,
  "key_insights": ["insight1", "insight2", "insight3", "insight4", "insight5"],
  "market_bias": "BULLISH" or "BEARISH" or "NEUTRAL",
  "confidence": 0.0 to 1.0
}

Be specific with price levels. Use technical analysis principles.`;

      const geminiApiKey = import.meta.env.VITE_GEMINI_API_KEY;

      if (!geminiApiKey) {
        throw new Error('Gemini API key not configured. Please add VITE_GEMINI_API_KEY to .env file');
      }

      const response = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key=${geminiApiKey}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            contents: [{
              parts: [{
                text: prompt
              }]
            }],
            generationConfig: {
              temperature: 0.7,
              topK: 40,
              topP: 0.95,
              maxOutputTokens: 2048,
            }
          })
        }
      );

      if (!response.ok) {
        throw new Error(`Gemini API error: ${response.status}`);
      }

      const result = await response.json();
      const aiText = result.candidates?.[0]?.content?.parts?.[0]?.text;

      if (!aiText) {
        throw new Error('No response from Gemini API');
      }

      const jsonMatch = aiText.match(/\{[\s\S]*\}/);
      if (!jsonMatch) {
        throw new Error('Invalid JSON response from AI');
      }

      const aiData = JSON.parse(jsonMatch[0]);

      const newExpectation: MarketExpectationData = {
        date: currentDate,
        symbol: 'SPY',
        analysis: aiData.analysis,
        resistance_levels: aiData.resistance_levels,
        support_levels: aiData.support_levels,
        entry_long: aiData.entry_long,
        exit_long: aiData.exit_long,
        stop_loss_long: aiData.stop_loss_long,
        risk_reward_long: aiData.risk_reward_long,
        entry_fade: aiData.entry_fade,
        exit_fade: aiData.exit_fade,
        stop_loss_fade: aiData.stop_loss_fade,
        risk_reward_fade: aiData.risk_reward_fade,
        key_insights: aiData.key_insights,
        market_bias: aiData.market_bias,
        confidence: aiData.confidence,
        generated_at: new Date().toISOString()
      };

      setExpectation(newExpectation);
      setLastGenerated(new Date());

      await supabase
        .from('market_expectations')
        .upsert({
          date: currentDate,
          symbol: 'SPY',
          data: newExpectation,
          created_at: new Date().toISOString()
        }, { onConflict: 'date,symbol' });

    } catch (err) {
      console.error('Error generating expectation:', err);
      setError(err instanceof Error ? err.message : 'Failed to generate market expectation');
    } finally {
      setIsLoading(false);
    }
  };

  const loadTodayExpectation = async () => {
    const today = new Date().toISOString().split('T')[0];

    const { data } = await supabase
      .from('market_expectations')
      .select('*')
      .eq('symbol', 'SPY')
      .eq('date', today)
      .maybeSingle();

    if (data) {
      setExpectation(data.data);
      setLastGenerated(new Date(data.created_at));
    } else {
      generateExpectation();
    }
  };

  useEffect(() => {
    loadTodayExpectation();
  }, []);

  const getBiasColor = (bias: string) => {
    switch (bias) {
      case 'BULLISH': return 'text-green-400 bg-green-900/30 border-green-700';
      case 'BEARISH': return 'text-red-400 bg-red-900/30 border-red-700';
      default: return 'text-yellow-400 bg-yellow-900/30 border-yellow-700';
    }
  };

  const getBiasIcon = (bias: string) => {
    switch (bias) {
      case 'BULLISH': return <TrendingUp className="h-5 w-5" />;
      case 'BEARISH': return <TrendingDown className="h-5 w-5" />;
      default: return <Activity className="h-5 w-5" />;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center space-x-2 mb-1">
            <Brain className="h-6 w-6 text-purple-400" />
            <h2 className="text-2xl font-bold text-white">AI Market Expectation - SPY</h2>
            <Sparkles className="h-5 w-5 text-yellow-400" />
          </div>
          <p className="text-slate-400 text-sm">Daily intraday analysis powered by Google Gemini AI</p>
        </div>
        <button
          onClick={generateExpectation}
          disabled={isLoading}
          className="flex items-center space-x-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-slate-700 text-white rounded-lg transition-colors"
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          <span>{isLoading ? 'Generating...' : 'Regenerate'}</span>
        </button>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4">
          <div className="flex items-center space-x-2 text-red-400">
            <AlertCircle className="h-5 w-5" />
            <span>{error}</span>
          </div>
        </div>
      )}

      {lastGenerated && (
        <div className="bg-slate-800 rounded-lg p-3 border border-slate-700">
          <div className="flex items-center justify-between text-sm text-slate-400">
            <span>Last Generated: {lastGenerated.toLocaleString()}</span>
            <span className="text-purple-400">Updates daily at market open</span>
          </div>
        </div>
      )}

      {isLoading && !expectation && (
        <div className="bg-slate-800 rounded-lg p-12 border border-slate-700 text-center">
          <Brain className="h-12 w-12 text-purple-400 mx-auto mb-4 animate-pulse" />
          <p className="text-white font-semibold mb-2">Analyzing Market Data...</p>
          <p className="text-slate-400 text-sm">Gemini AI is generating today's market expectation</p>
        </div>
      )}

      {expectation && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className={`rounded-lg p-4 border ${getBiasColor(expectation.market_bias)}`}>
              <div className="flex items-center space-x-2 mb-2">
                {getBiasIcon(expectation.market_bias)}
                <span className="font-semibold">Market Bias</span>
              </div>
              <div className="text-2xl font-bold">{expectation.market_bias}</div>
              <div className="text-sm mt-1 opacity-75">
                Confidence: {(expectation.confidence * 100).toFixed(0)}%
              </div>
            </div>

            <div className="bg-blue-900/30 border border-blue-700 rounded-lg p-4">
              <div className="flex items-center space-x-2 mb-2 text-blue-400">
                <BarChart3 className="h-5 w-5" />
                <span className="font-semibold">Long Setup</span>
              </div>
              <div className="text-2xl font-bold text-white">${expectation.entry_long.toFixed(2)}</div>
              <div className="text-sm text-blue-300 mt-1">
                R/R: {expectation.risk_reward_long.toFixed(2)}:1
              </div>
            </div>

            <div className="bg-orange-900/30 border border-orange-700 rounded-lg p-4">
              <div className="flex items-center space-x-2 mb-2 text-orange-400">
                <Zap className="h-5 w-5" />
                <span className="font-semibold">Fade Setup</span>
              </div>
              <div className="text-2xl font-bold text-white">${expectation.entry_fade.toFixed(2)}</div>
              <div className="text-sm text-orange-300 mt-1">
                R/R: {expectation.risk_reward_fade.toFixed(2)}:1
              </div>
            </div>
          </div>

          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <h3 className="text-lg font-semibold text-white mb-3">Market Analysis</h3>
            <p className="text-slate-300 leading-relaxed">{expectation.analysis}</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <div className="flex items-center space-x-2 mb-4">
                <Target className="h-5 w-5 text-green-400" />
                <h3 className="text-lg font-semibold text-white">Long Position (At Open)</h3>
              </div>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Entry Level:</span>
                  <span className="text-green-400 font-bold text-lg">${expectation.entry_long.toFixed(2)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Exit Target:</span>
                  <span className="text-green-400 font-bold">${expectation.exit_long.toFixed(2)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Stop Loss:</span>
                  <span className="text-red-400 font-bold">${expectation.stop_loss_long.toFixed(2)}</span>
                </div>
                <div className="flex justify-between items-center pt-2 border-t border-slate-700">
                  <span className="text-slate-400">Risk/Reward:</span>
                  <span className="text-blue-400 font-bold text-lg">{expectation.risk_reward_long.toFixed(2)}:1</span>
                </div>
              </div>
            </div>

            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <div className="flex items-center space-x-2 mb-4">
                <Zap className="h-5 w-5 text-orange-400" />
                <h3 className="text-lg font-semibold text-white">Fade Movement (Counter-Trend)</h3>
              </div>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Entry Level:</span>
                  <span className="text-orange-400 font-bold text-lg">${expectation.entry_fade.toFixed(2)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Exit Target:</span>
                  <span className="text-orange-400 font-bold">${expectation.exit_fade.toFixed(2)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Stop Loss:</span>
                  <span className="text-red-400 font-bold">${expectation.stop_loss_fade.toFixed(2)}</span>
                </div>
                <div className="flex justify-between items-center pt-2 border-t border-slate-700">
                  <span className="text-slate-400">Risk/Reward:</span>
                  <span className="text-blue-400 font-bold text-lg">{expectation.risk_reward_fade.toFixed(2)}:1</span>
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <div className="flex items-center space-x-2 mb-4">
                <TrendingUp className="h-5 w-5 text-red-400" />
                <h3 className="text-lg font-semibold text-white">Resistance Levels</h3>
              </div>
              <div className="space-y-2">
                {expectation.resistance_levels.map((level, idx) => (
                  <div key={idx} className="flex justify-between items-center p-2 bg-red-900/20 rounded">
                    <span className="text-slate-400">R{idx + 1}:</span>
                    <span className="text-red-400 font-bold">${level.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <div className="flex items-center space-x-2 mb-4">
                <TrendingDown className="h-5 w-5 text-green-400" />
                <h3 className="text-lg font-semibold text-white">Support Levels</h3>
              </div>
              <div className="space-y-2">
                {expectation.support_levels.map((level, idx) => (
                  <div key={idx} className="flex justify-between items-center p-2 bg-green-900/20 rounded">
                    <span className="text-slate-400">S{idx + 1}:</span>
                    <span className="text-green-400 font-bold">${level.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="bg-gradient-to-r from-purple-900/30 to-blue-900/30 border border-purple-700/50 rounded-lg p-6">
            <div className="flex items-center space-x-2 mb-4">
              <Shield className="h-5 w-5 text-purple-400" />
              <h3 className="text-lg font-semibold text-white">Key Insights & Actionable Advice</h3>
            </div>
            <ul className="space-y-2">
              {expectation.key_insights.map((insight, idx) => (
                <li key={idx} className="flex items-start space-x-2 text-slate-300">
                  <DollarSign className="h-5 w-5 text-purple-400 flex-shrink-0 mt-0.5" />
                  <span>{insight}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
            <div className="flex items-center space-x-2 text-sm text-slate-400">
              <AlertCircle className="h-4 w-4" />
              <span>
                This analysis is generated by AI and should be used as one input among many for your trading decisions.
                Always perform your own analysis and risk management.
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
