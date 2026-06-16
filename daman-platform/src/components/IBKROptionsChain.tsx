import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, RefreshCw, Activity, Database } from 'lucide-react';
import { supabase } from '../lib/supabase';

interface IBKROption {
  symbol: string;
  expiration: string;
  strike: number;
  option_type: string;
  bid: number;
  ask: number;
  last: number;
  mid: number;
  volume: number;
  open_interest: number;
  implied_volatility: number;
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
  underlying_price: number;
  timestamp: string;
  updated_at: string;
}

export default function IBKROptionsChain() {
  const [options, setOptions] = useState<IBKROption[]>([]);
  const [loading, setLoading] = useState(false);
  const [symbol, setSymbol] = useState('SPY');
  const [expiration, setExpiration] = useState('');
  const [minStrike, setMinStrike] = useState(400);
  const [maxStrike, setMaxStrike] = useState(450);
  const [strikeInterval, setStrikeInterval] = useState(5);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);

  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(() => {
        fetchOptionsData();
      }, 5000);

      return () => clearInterval(interval);
    }
  }, [autoRefresh, symbol, expiration]);

  const fetchOptionsData = async () => {
    setLoading(true);
    try {
      const { data, error } = await supabase
        .from('ibkr_options_realtime')
        .select('*')
        .eq('symbol', symbol)
        .gte('strike', minStrike)
        .lte('strike', maxStrike)
        .order('strike', { ascending: true })
        .order('option_type', { ascending: false });

      if (error) throw error;

      setOptions(data || []);
      setLastUpdate(new Date());
    } catch (error) {
      console.error('Error fetching IBKR options:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchFromIBKR = async () => {
    setLoading(true);
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      const params = new URLSearchParams({
        symbol,
        expiration,
        minStrike: minStrike.toString(),
        maxStrike: maxStrike.toString(),
        strikeInterval: strikeInterval.toString(),
      });

      const response = await fetch(
        `${supabaseUrl}/functions/v1/fetch-ibkr-options?${params}`,
        {
          headers: {
            Authorization: `Bearer ${supabaseKey}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error('Failed to fetch from IBKR');
      }

      const result = await response.json();
      console.log('IBKR Response:', result);

      await fetchOptionsData();
    } catch (error) {
      console.error('Error fetching from IBKR:', error);
    } finally {
      setLoading(false);
    }
  };

  const calls = options.filter(opt => opt.option_type === 'CALL' || opt.option_type === 'C');
  const puts = options.filter(opt => opt.option_type === 'PUT' || opt.option_type === 'P');

  const groupedByStrike = new Map<number, { call?: IBKROption; put?: IBKROption }>();

  calls.forEach(call => {
    if (!groupedByStrike.has(call.strike)) {
      groupedByStrike.set(call.strike, {});
    }
    groupedByStrike.get(call.strike)!.call = call;
  });

  puts.forEach(put => {
    if (!groupedByStrike.has(put.strike)) {
      groupedByStrike.set(put.strike, {});
    }
    groupedByStrike.get(put.strike)!.put = put;
  });

  const strikes = Array.from(groupedByStrike.keys()).sort((a, b) => b - a);

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Activity className="w-6 h-6 text-blue-400" />
          <h2 className="text-xl font-bold text-white">IBKR Live Options Chain</h2>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              autoRefresh
                ? 'bg-green-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            {autoRefresh ? 'Auto-Refresh ON' : 'Auto-Refresh OFF'}
          </button>
          <button
            onClick={fetchOptionsData}
            disabled={loading}
            className="px-4 py-2 bg-gray-800 text-white rounded-lg hover:bg-gray-700 transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <Database className="w-4 h-4" />
            Load from DB
          </button>
          <button
            onClick={fetchFromIBKR}
            disabled={loading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Fetch from IBKR
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4 mb-6">
        <div>
          <label className="block text-sm text-gray-400 mb-2">Symbol</label>
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-2">Expiration</label>
          <input
            type="text"
            value={expiration}
            onChange={(e) => setExpiration(e.target.value)}
            placeholder="YYYYMMDD"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-2">Min Strike</label>
          <input
            type="number"
            value={minStrike}
            onChange={(e) => setMinStrike(Number(e.target.value))}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-2">Max Strike</label>
          <input
            type="number"
            value={maxStrike}
            onChange={(e) => setMaxStrike(Number(e.target.value))}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-2">Interval</label>
          <input
            type="number"
            value={strikeInterval}
            onChange={(e) => setStrikeInterval(Number(e.target.value))}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
          />
        </div>
      </div>

      {lastUpdate && (
        <div className="text-sm text-gray-400 mb-4">
          Last updated: {lastUpdate.toLocaleTimeString()}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="px-4 py-3 text-left text-sm font-semibold text-gray-400" colSpan={5}>
                CALLS
              </th>
              <th className="px-4 py-3 text-center text-sm font-semibold text-white">
                STRIKE
              </th>
              <th className="px-4 py-3 text-right text-sm font-semibold text-gray-400" colSpan={5}>
                PUTS
              </th>
            </tr>
            <tr className="border-b border-gray-800 text-xs text-gray-500">
              <th className="px-2 py-2 text-left">Bid</th>
              <th className="px-2 py-2 text-left">Ask</th>
              <th className="px-2 py-2 text-left">Last</th>
              <th className="px-2 py-2 text-left">IV</th>
              <th className="px-2 py-2 text-left">Delta</th>
              <th className="px-2 py-2 text-center font-semibold">Price</th>
              <th className="px-2 py-2 text-right">Delta</th>
              <th className="px-2 py-2 text-right">IV</th>
              <th className="px-2 py-2 text-right">Last</th>
              <th className="px-2 py-2 text-right">Ask</th>
              <th className="px-2 py-2 text-right">Bid</th>
            </tr>
          </thead>
          <tbody>
            {strikes.map((strike) => {
              const { call, put } = groupedByStrike.get(strike) || {};
              return (
                <tr key={strike} className="border-b border-gray-800 hover:bg-gray-800/50">
                  <td className="px-2 py-2 text-sm text-green-400">
                    {call?.bid.toFixed(2) || '-'}
                  </td>
                  <td className="px-2 py-2 text-sm text-green-400">
                    {call?.ask.toFixed(2) || '-'}
                  </td>
                  <td className="px-2 py-2 text-sm text-white">
                    {call?.last.toFixed(2) || '-'}
                  </td>
                  <td className="px-2 py-2 text-sm text-gray-400">
                    {call ? `${(call.implied_volatility * 100).toFixed(1)}%` : '-'}
                  </td>
                  <td className="px-2 py-2 text-sm text-gray-400">
                    {call?.delta?.toFixed(3) || '-'}
                  </td>
                  <td className="px-2 py-2 text-center text-sm font-semibold text-white">
                    ${strike}
                  </td>
                  <td className="px-2 py-2 text-sm text-right text-gray-400">
                    {put?.delta?.toFixed(3) || '-'}
                  </td>
                  <td className="px-2 py-2 text-sm text-right text-gray-400">
                    {put ? `${(put.implied_volatility * 100).toFixed(1)}%` : '-'}
                  </td>
                  <td className="px-2 py-2 text-sm text-right text-white">
                    {put?.last.toFixed(2) || '-'}
                  </td>
                  <td className="px-2 py-2 text-sm text-right text-red-400">
                    {put?.ask.toFixed(2) || '-'}
                  </td>
                  <td className="px-2 py-2 text-sm text-right text-red-400">
                    {put?.bid.toFixed(2) || '-'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {strikes.length === 0 && !loading && (
          <div className="text-center py-12 text-gray-500">
            No options data available. Click "Fetch from IBKR" to load data.
          </div>
        )}

        {loading && (
          <div className="text-center py-12">
            <RefreshCw className="w-8 h-8 text-blue-400 animate-spin mx-auto" />
            <p className="text-gray-400 mt-2">Loading options data...</p>
          </div>
        )}
      </div>
    </div>
  );
}
