import { useState, useEffect } from 'react';
import {
  TrendingUp, TrendingDown, Target, Shield, Clock, Activity,
  RefreshCw, Filter, Download, ChevronUp, ChevronDown, AlertCircle,
  BarChart3, CheckCircle, XCircle, Zap
} from 'lucide-react';
import { supabase } from '../lib/supabase';

interface TradingSignal {
  id: string;
  symbol: string;
  action: 'BUY' | 'SELL';
  price: number;
  target1: number;
  target2: number;
  stop_loss: number;
  indicator_name: string;
  timeframe: string;
  strength: 'weak' | 'moderate' | 'strong';
  status: string;
  triggered_at: string;
  potential_gain_t1: number;
  potential_gain_t2: number;
  risk_percent: number;
  notes: string;
}

export default function SignalsScreener() {
  const [signals, setSignals] = useState<TradingSignal[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'BUY' | 'SELL'>('all');
  const [sortField, setSortField] = useState<'triggered_at' | 'potential_gain_t2' | 'risk_percent'>('triggered_at');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [autoRefresh, setAutoRefresh] = useState(false);

  const fetchSignals = async () => {
    try {
      let query = supabase.from('active_signals').select('*');

      if (filter !== 'all') {
        query = query.eq('action', filter);
      }

      query = query.order(sortField, { ascending: sortDirection === 'asc' });

      const { data, error } = await query;

      if (error) throw error;

      setSignals(data || []);
    } catch (error) {
      console.error('Error fetching signals:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSignals();

    const subscription = supabase
      .channel('signals_changes')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'tradingview_signals' },
        () => {
          fetchSignals();
        }
      )
      .subscribe();

    return () => {
      subscription.unsubscribe();
    };
  }, [filter, sortField, sortDirection]);

  useEffect(() => {
    let interval: number | null = null;
    if (autoRefresh) {
      interval = window.setInterval(() => {
        fetchSignals();
      }, 30000); // Refresh every 30 seconds
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh]);

  const handleSort = (field: typeof sortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const getSignalColor = (action: 'BUY' | 'SELL') => {
    return action === 'BUY' ? 'text-green-600' : 'text-red-600';
  };

  const getSignalBg = (action: 'BUY' | 'SELL') => {
    return action === 'BUY' ? 'bg-green-50' : 'bg-red-50';
  };

  const getStrengthColor = (strength: string) => {
    switch (strength) {
      case 'strong': return 'text-purple-600 bg-purple-50';
      case 'moderate': return 'text-blue-600 bg-blue-50';
      case 'weak': return 'text-gray-600 bg-gray-50';
      default: return 'text-gray-600 bg-gray-50';
    }
  };

  const getRiskRewardRatio = (signal: TradingSignal) => {
    const reward = Math.abs(signal.potential_gain_t2);
    const risk = Math.abs(signal.risk_percent);
    return risk > 0 ? (reward / risk).toFixed(2) : 'N/A';
  };

  const exportToCSV = () => {
    const headers = ['Symbol', 'Action', 'Price', 'Target 1', 'Target 2', 'Stop Loss', 'Potential Gain T1', 'Potential Gain T2', 'Risk %', 'R:R Ratio', 'Strength', 'Timeframe', 'Indicator', 'Triggered'];
    const rows = signals.map(s => [
      s.symbol,
      s.action,
      s.price,
      s.target1,
      s.target2,
      s.stop_loss,
      `${s.potential_gain_t1}%`,
      `${s.potential_gain_t2}%`,
      `${s.risk_percent}%`,
      getRiskRewardRatio(s),
      s.strength,
      s.timeframe,
      s.indicator_name,
      new Date(s.triggered_at).toLocaleString()
    ]);

    const csv = [headers, ...rows].map(row => row.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `trading-signals-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-slate-100 py-8 px-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-4xl font-bold text-slate-900 mb-2">
                TradingView Signals Screener
              </h1>
              <p className="text-slate-600">
                Real-time buy/sell signals from your TradingView indicators
              </p>
            </div>
            <div className="flex items-center space-x-3">
              <button
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={`flex items-center space-x-2 px-4 py-2 rounded-lg border transition-colors ${
                  autoRefresh
                    ? 'bg-green-50 border-green-200 text-green-700'
                    : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
                }`}
              >
                <Activity className={`h-4 w-4 ${autoRefresh ? 'animate-pulse' : ''}`} />
                <span className="text-sm font-medium">
                  {autoRefresh ? 'Auto-Refresh ON' : 'Auto-Refresh OFF'}
                </span>
              </button>
              <button
                onClick={fetchSignals}
                className="flex items-center space-x-2 px-4 py-2 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
              >
                <RefreshCw className="h-4 w-4" />
                <span className="text-sm font-medium">Refresh</span>
              </button>
              <button
                onClick={exportToCSV}
                className="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                <Download className="h-4 w-4" />
                <span className="text-sm font-medium">Export CSV</span>
              </button>
            </div>
          </div>

          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-white rounded-xl p-4 border border-slate-200">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-600 mb-1">Active Signals</p>
                  <p className="text-2xl font-bold text-slate-900">{signals.length}</p>
                </div>
                <div className="p-3 bg-blue-50 rounded-lg">
                  <Zap className="h-6 w-6 text-blue-600" />
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl p-4 border border-slate-200">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-600 mb-1">Buy Signals</p>
                  <p className="text-2xl font-bold text-green-600">
                    {signals.filter(s => s.action === 'BUY').length}
                  </p>
                </div>
                <div className="p-3 bg-green-50 rounded-lg">
                  <TrendingUp className="h-6 w-6 text-green-600" />
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl p-4 border border-slate-200">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-600 mb-1">Sell Signals</p>
                  <p className="text-2xl font-bold text-red-600">
                    {signals.filter(s => s.action === 'SELL').length}
                  </p>
                </div>
                <div className="p-3 bg-red-50 rounded-lg">
                  <TrendingDown className="h-6 w-6 text-red-600" />
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl p-4 border border-slate-200">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-600 mb-1">Avg R:R Ratio</p>
                  <p className="text-2xl font-bold text-purple-600">
                    {signals.length > 0
                      ? (signals.reduce((sum, s) => sum + parseFloat(getRiskRewardRatio(s) as string), 0) / signals.length).toFixed(2)
                      : '0.00'}
                  </p>
                </div>
                <div className="p-3 bg-purple-50 rounded-lg">
                  <BarChart3 className="h-6 w-6 text-purple-600" />
                </div>
              </div>
            </div>
          </div>

          {/* Filters */}
          <div className="flex items-center space-x-3">
            <Filter className="h-5 w-5 text-slate-600" />
            <button
              onClick={() => setFilter('all')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                filter === 'all'
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50'
              }`}
            >
              All Signals
            </button>
            <button
              onClick={() => setFilter('BUY')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                filter === 'BUY'
                  ? 'bg-green-600 text-white'
                  : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50'
              }`}
            >
              Buy Only
            </button>
            <button
              onClick={() => setFilter('SELL')}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                filter === 'SELL'
                  ? 'bg-red-600 text-white'
                  : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50'
              }`}
            >
              Sell Only
            </button>
          </div>
        </div>

        {/* Signals Table */}
        {signals.length === 0 ? (
          <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
            <AlertCircle className="h-12 w-12 text-slate-400 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-slate-900 mb-2">No Active Signals</h3>
            <p className="text-slate-600 mb-4">
              Waiting for signals from your TradingView indicators...
            </p>
            <p className="text-sm text-slate-500">
              Webhook URL: <code className="bg-slate-100 px-2 py-1 rounded text-xs">
                {import.meta.env.VITE_SUPABASE_URL}/functions/v1/tradingview-webhook
              </code>
            </p>
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Symbol
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Action
                    </th>
                    <th className="px-6 py-4 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Entry Price
                    </th>
                    <th className="px-6 py-4 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Target 1
                    </th>
                    <th className="px-6 py-4 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Target 2
                    </th>
                    <th className="px-6 py-4 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Stop Loss
                    </th>
                    <th className="px-6 py-4 text-center text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      R:R Ratio
                    </th>
                    <th className="px-6 py-4 text-center text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Strength
                    </th>
                    <th
                      className="px-6 py-4 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider cursor-pointer hover:text-slate-900"
                      onClick={() => handleSort('triggered_at')}
                    >
                      <div className="flex items-center space-x-1">
                        <span>Time</span>
                        {sortField === 'triggered_at' && (
                          sortDirection === 'asc' ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />
                        )}
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {signals.map((signal) => (
                    <tr key={signal.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-6 py-4">
                        <div className="font-semibold text-slate-900">{signal.symbol}</div>
                        <div className="text-xs text-slate-500">{signal.timeframe}</div>
                      </td>
                      <td className="px-6 py-4">
                        <div className={`inline-flex items-center space-x-1 px-3 py-1 rounded-full text-sm font-semibold ${getSignalBg(signal.action)} ${getSignalColor(signal.action)}`}>
                          {signal.action === 'BUY' ? (
                            <TrendingUp className="h-4 w-4" />
                          ) : (
                            <TrendingDown className="h-4 w-4" />
                          )}
                          <span>{signal.action}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="font-semibold text-slate-900">${signal.price.toFixed(2)}</div>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="font-semibold text-slate-900">${signal.target1.toFixed(2)}</div>
                        <div className="text-xs text-green-600">
                          +{signal.potential_gain_t1.toFixed(2)}%
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="font-semibold text-slate-900">${signal.target2.toFixed(2)}</div>
                        <div className="text-xs text-green-600">
                          +{signal.potential_gain_t2.toFixed(2)}%
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="font-semibold text-slate-900">${signal.stop_loss.toFixed(2)}</div>
                        <div className="text-xs text-red-600">
                          {signal.risk_percent.toFixed(2)}%
                        </div>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <div className={`inline-flex items-center px-2 py-1 rounded-md text-sm font-bold ${
                          parseFloat(getRiskRewardRatio(signal) as string) >= 2
                            ? 'bg-green-100 text-green-700'
                            : parseFloat(getRiskRewardRatio(signal) as string) >= 1
                            ? 'bg-yellow-100 text-yellow-700'
                            : 'bg-red-100 text-red-700'
                        }`}>
                          {getRiskRewardRatio(signal)}:1
                        </div>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className={`inline-block px-2 py-1 rounded-md text-xs font-semibold ${getStrengthColor(signal.strength)}`}>
                          {signal.strength.toUpperCase()}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="text-sm text-slate-900">
                          {new Date(signal.triggered_at).toLocaleDateString()}
                        </div>
                        <div className="text-xs text-slate-500">
                          {new Date(signal.triggered_at).toLocaleTimeString()}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Setup Instructions */}
        <div className="mt-8 bg-blue-50 border border-blue-200 rounded-xl p-6">
          <h3 className="text-lg font-semibold text-blue-900 mb-3 flex items-center">
            <AlertCircle className="h-5 w-5 mr-2" />
            TradingView Setup Instructions
          </h3>
          <div className="space-y-3 text-sm text-blue-800">
            <p>
              <strong>Step 1:</strong> In TradingView, create an alert on your indicator
            </p>
            <p>
              <strong>Step 2:</strong> Set the alert to trigger on "Once Per Bar Close"
            </p>
            <p>
              <strong>Step 3:</strong> In the "Webhook URL" field, paste:
            </p>
            <code className="block bg-white px-3 py-2 rounded border border-blue-300 text-xs font-mono">
              {import.meta.env.VITE_SUPABASE_URL}/functions/v1/tradingview-webhook
            </code>
            <p className="mt-3">
              <strong>Step 4:</strong> In the "Message" field, paste this JSON (customize values):
            </p>
            <pre className="bg-white px-3 py-2 rounded border border-blue-300 text-xs font-mono overflow-x-auto">
{`{
  "symbol": "{{ticker}}",
  "action": "BUY",
  "price": {{close}},
  "target1": {{close}} * 1.05,
  "target2": {{close}} * 1.10,
  "stop_loss": {{close}} * 0.97,
  "indicator_name": "Your Indicator Name",
  "timeframe": "{{interval}}",
  "strength": "strong",
  "notes": "Alert from TradingView"
}`}
            </pre>
            <p className="text-xs text-blue-600 mt-2">
              💡 Tip: Use TradingView's alert message placeholders like {'{{ticker}}'}, {'{{close}}'}, {'{{interval}}'} for dynamic values
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
