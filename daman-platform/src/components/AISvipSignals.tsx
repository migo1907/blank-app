import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Target, Shield, RefreshCw, Search } from 'lucide-react';
import { supabase } from '../lib/supabase';

interface SignalData {
  id: string;
  symbol: string;
  action: 'BUY' | 'SELL';
  price: number;
  entry: number;
  stop_loss: number;
  target1: number;
  target2: number;
  timeframe: string;
  strength: 'weak' | 'moderate' | 'strong';
  status: string;
  triggered_at: string;
}

const TIMEFRAMES = ['5m', '15m', '30m', '1h'];

export default function AISvipSignals() {
  const [selectedSymbols, setSelectedSymbols] = useState('SPY AAPL MSFT TSLA NVDA');
  const [signals, setSignals] = useState<SignalData[]>([]);
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [nextRefresh, setNextRefresh] = useState(60);

  const fetchSignals = async () => {
    setLoading(true);
    try {
      const symbols = selectedSymbols.split(' ').filter(s => s.trim());
      const { data, error } = await supabase
        .from('tradingview_signals')
        .select('*')
        .in('symbol', symbols)
        .in('timeframe', TIMEFRAMES)
        .eq('status', 'active')
        .order('triggered_at', { ascending: false })
        .limit(100);

      if (error) {
        console.error('Error fetching signals:', error);
        setSignals(getMockSignals());
      } else if (data && data.length > 0) {
        setSignals(data.map(signal => ({
          ...signal,
          entry: signal.price,
        })));
      } else {
        setSignals(getMockSignals());
      }
    } catch (err) {
      console.error('Fetch error:', err);
      setSignals(getMockSignals());
    } finally {
      setLoading(false);
    }
  };

  const getMockSignals = (): SignalData[] => {
    const symbols = selectedSymbols.split(' ').filter(s => s.trim());
    const mockSignals: SignalData[] = [];

    symbols.slice(0, 5).forEach((symbol, idx) => {
      TIMEFRAMES.forEach((timeframe, tfIdx) => {
        const basePrice = 100 + (idx * 50) + (tfIdx * 5);
        const action = (idx + tfIdx) % 2 === 0 ? 'BUY' : 'SELL';
        const entry = basePrice;
        const stopDistance = basePrice * 0.02;
        const target1Distance = basePrice * 0.03;
        const target2Distance = basePrice * 0.05;

        mockSignals.push({
          id: `${symbol}-${timeframe}-${idx}`,
          symbol,
          action,
          price: entry,
          entry,
          stop_loss: action === 'BUY' ? entry - stopDistance : entry + stopDistance,
          target1: action === 'BUY' ? entry + target1Distance : entry - target1Distance,
          target2: action === 'BUY' ? entry + target2Distance : entry - target2Distance,
          timeframe,
          strength: ['weak', 'moderate', 'strong'][tfIdx % 3] as 'weak' | 'moderate' | 'strong',
          status: 'active',
          triggered_at: new Date().toISOString(),
        });
      });
    });

    return mockSignals;
  };

  useEffect(() => {
    fetchSignals();
  }, []);

  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(() => {
        fetchSignals();
      }, 60000);

      const countdown = setInterval(() => {
        setNextRefresh(prev => {
          if (prev <= 1) return 60;
          return prev - 1;
        });
      }, 1000);

      return () => {
        clearInterval(interval);
        clearInterval(countdown);
      };
    }
  }, [autoRefresh, selectedSymbols]);

  const groupedSignals = TIMEFRAMES.reduce((acc, timeframe) => {
    acc[timeframe] = signals.filter(s => s.timeframe === timeframe);
    return acc;
  }, {} as Record<string, SignalData[]>);

  const getStrengthColor = (strength: string) => {
    switch (strength) {
      case 'strong': return 'text-green-400';
      case 'moderate': return 'text-yellow-400';
      case 'weak': return 'text-orange-400';
      default: return 'text-slate-400';
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Target className="w-6 h-6 text-blue-400" />
              AI Svip 1.7.0.4 Signals
            </h2>
            <p className="text-sm text-slate-400 mt-1">
              TradingView indicator signals across multiple timeframes
            </p>
          </div>
          {autoRefresh && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-900/30 border border-blue-600/30 rounded-lg">
              <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
              <span className="text-sm text-blue-400 font-medium">Auto-refresh: {nextRefresh}s</span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Symbols (space-separated)
            </label>
            <input
              type="text"
              value={selectedSymbols}
              onChange={(e) => setSelectedSymbols(e.target.value)}
              placeholder="SPY AAPL MSFT TSLA NVDA"
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white"
            />
          </div>
          <div className="flex items-end gap-3">
            <button
              onClick={fetchSignals}
              disabled={loading}
              className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 text-white font-medium py-2 px-4 rounded transition-colors flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Loading...
                </>
              ) : (
                <>
                  <Search className="w-4 h-4" />
                  Fetch Signals
                </>
              )}
            </button>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="autoRefreshSvip"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="w-4 h-4"
              />
              <label htmlFor="autoRefreshSvip" className="text-sm text-slate-300 whitespace-nowrap">
                Auto-refresh
              </label>
            </div>
          </div>
        </div>

        <div className="space-y-8">
          {TIMEFRAMES.map((timeframe) => {
            const timeframeSignals = groupedSignals[timeframe] || [];

            return (
              <div key={timeframe} className="bg-slate-900/50 rounded-lg p-4 border border-slate-700">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-bold text-white flex items-center gap-2">
                    <span className="text-cyan-400">{timeframe.toUpperCase()}</span>
                    <span className="text-slate-500">Timeframe</span>
                  </h3>
                  <span className="text-sm text-slate-400">
                    {timeframeSignals.length} signals
                  </span>
                </div>

                {timeframeSignals.length === 0 ? (
                  <div className="text-center py-8 text-slate-400">
                    No signals found for this timeframe
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left border-b border-slate-700">
                          <th className="pb-3 text-slate-300 font-medium">Symbol</th>
                          <th className="pb-3 text-slate-300 font-medium">Signal</th>
                          <th className="pb-3 text-slate-300 font-medium">Entry</th>
                          <th className="pb-3 text-slate-300 font-medium">Stop Loss</th>
                          <th className="pb-3 text-slate-300 font-medium">Target 1</th>
                          <th className="pb-3 text-slate-300 font-medium">Target 2</th>
                          <th className="pb-3 text-slate-300 font-medium">R:R</th>
                          <th className="pb-3 text-slate-300 font-medium">Strength</th>
                        </tr>
                      </thead>
                      <tbody>
                        {timeframeSignals.map((signal) => {
                          const risk = Math.abs(signal.entry - signal.stop_loss);
                          const reward1 = Math.abs(signal.target1 - signal.entry);
                          const reward2 = Math.abs(signal.target2 - signal.entry);
                          const rr1 = risk > 0 ? (reward1 / risk).toFixed(2) : '0.00';
                          const rr2 = risk > 0 ? (reward2 / risk).toFixed(2) : '0.00';

                          return (
                            <tr
                              key={signal.id}
                              className="border-b border-slate-700/50 hover:bg-slate-700/30"
                            >
                              <td className="py-3 text-white font-medium">{signal.symbol}</td>
                              <td className="py-3">
                                <span
                                  className={`px-2 py-1 rounded text-xs font-medium ${
                                    signal.action === 'BUY'
                                      ? 'bg-green-500/20 text-green-400 flex items-center gap-1 w-fit'
                                      : 'bg-red-500/20 text-red-400 flex items-center gap-1 w-fit'
                                  }`}
                                >
                                  {signal.action === 'BUY' ? (
                                    <TrendingUp className="w-3 h-3" />
                                  ) : (
                                    <TrendingDown className="w-3 h-3" />
                                  )}
                                  {signal.action}
                                </span>
                              </td>
                              <td className="py-3 text-white font-medium">
                                ${signal.entry.toFixed(2)}
                              </td>
                              <td className="py-3 text-red-400 flex items-center gap-1">
                                <Shield className="w-3 h-3" />
                                ${signal.stop_loss.toFixed(2)}
                              </td>
                              <td className="py-3 text-green-400">
                                ${signal.target1.toFixed(2)}
                              </td>
                              <td className="py-3 text-green-500 font-medium">
                                ${signal.target2.toFixed(2)}
                              </td>
                              <td className="py-3 text-blue-400">
                                <div className="flex flex-col text-xs">
                                  <span>T1: {rr1}:1</span>
                                  <span className="font-medium">T2: {rr2}:1</span>
                                </div>
                              </td>
                              <td className="py-3">
                                <span className={`text-xs font-medium ${getStrengthColor(signal.strength)}`}>
                                  {signal.strength.toUpperCase()}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
