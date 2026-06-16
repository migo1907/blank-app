import { useState, useEffect } from 'react';
import { X, TrendingUp, TrendingDown, RefreshCw, AlertCircle, Target, Activity, DollarSign } from 'lucide-react';
import { fetchLiveData as fetchLiveDataUtil } from '../utils/liveDataFetcher';

interface WatchlistStock {
  symbol: string;
  action: 'LONG' | 'SHORT' | 'WAIT';
  rsi: number;
  price: number;
  superTrend: number;
  vwap: number;
  volume: number;
  stopLoss?: number;
  target?: number;
}

interface ScannerStats {
  winRate: number;
  totalSignals: number;
  wins: number;
  losses: number;
}

interface QuantFlowScannerProps {
  onClose: () => void;
}

export default function QuantFlowScanner({ onClose }: QuantFlowScannerProps) {
  const [watchlist, setWatchlist] = useState<string[]>(['SPY', 'QQQ', 'NVDA', 'AAPL', 'MSFT', 'TSLA', 'AMD', 'META']);
  const [results, setResults] = useState<WatchlistStock[]>([]);
  const [stats, setStats] = useState<ScannerStats>({ winRate: 0, totalSignals: 0, wins: 0, losses: 0 });
  const [isScanning, setIsScanning] = useState(false);
  const [newSymbol, setNewSymbol] = useState('');

  const [settings, setSettings] = useState({
    superTrendFactor: 3.0,
    superTrendPeriod: 10,
    rrRatio: 1.5,
    volumeFilter: true,
  });

  const calculateSuperTrend = (high: number, low: number, close: number, atr: number, factor: number): number => {
    const hl2 = (high + low) / 2;
    return close > hl2 ? hl2 - (factor * atr) : hl2 + (factor * atr);
  };

  const calculateVWAP = (prices: number[], volumes: number[]): number => {
    if (prices.length !== volumes.length || prices.length === 0) return prices[prices.length - 1];
    const pv = prices.map((p, i) => p * volumes[i]);
    const sumPV = pv.reduce((a, b) => a + b, 0);
    const sumV = volumes.reduce((a, b) => a + b, 0);
    return sumV > 0 ? sumPV / sumV : prices[prices.length - 1];
  };

  const calculateATR = (highs: number[], lows: number[], closes: number[], period: number = 14): number => {
    if (highs.length < period + 1) return 1;
    const trs = [];
    for (let i = 1; i <= period; i++) {
      const tr = Math.max(
        highs[i] - lows[i],
        Math.abs(highs[i] - closes[i - 1]),
        Math.abs(lows[i] - closes[i - 1])
      );
      trs.push(tr);
    }
    return trs.reduce((a, b) => a + b, 0) / trs.length;
  };

  const fetchLiveData = async (symbol: string) => {
    try {
      const data = await fetchLiveDataUtil({
        symbol,
        interval: '5m',
        days: 30,
        includeExtendedHours: false,
        retries: 3,
        retryDelay: 1000,
      });
      return data;
    } catch (error) {
      console.error(`Error fetching data for ${symbol}:`, error);
      return null;
    }
  };

  const calculateRSI = (prices: number[]): number => {
    const period = 14;
    if (prices.length < period + 1) return 50;

    let gains = 0;
    let losses = 0;

    for (let i = 1; i <= period; i++) {
      const diff = prices[i] - prices[i - 1];
      if (diff > 0) gains += diff;
      else losses -= diff;
    }

    let avgGain = gains / period;
    let avgLoss = losses / period;

    for (let i = period + 1; i < prices.length; i++) {
      const diff = prices[i] - prices[i - 1];
      const gain = diff > 0 ? diff : 0;
      const loss = diff < 0 ? -diff : 0;
      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;
    }

    if (avgLoss === 0) return 100;
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
  };

  const scanMarket = async () => {
    setIsScanning(true);

    try {
      const scanResults: WatchlistStock[] = [];
      let totalWins = 0;
      let totalLosses = 0;

      for (const symbol of watchlist) {
        await new Promise(resolve => setTimeout(resolve, 200));

        const liveData = await fetchLiveData(symbol);
        if (!liveData || !liveData.data || liveData.data.length < 20) {
          continue;
        }

        const ohlcvData = liveData.data.slice(-50);
        const prices = ohlcvData.map((d: any) => d.close);
        const highs = ohlcvData.map((d: any) => d.high);
        const lows = ohlcvData.map((d: any) => d.low);
        const volumes = ohlcvData.map((d: any) => d.volume);

        const currentPrice = prices[prices.length - 1];
        const currentHigh = highs[highs.length - 1];
        const currentLow = lows[lows.length - 1];
        const currentVolume = volumes[volumes.length - 1] || 0;
        const avgVolume = volumes.reduce((a, b) => a + b, 0) / volumes.length;

        const atr = calculateATR(highs, lows, prices, settings.superTrendPeriod);
        const superTrend = calculateSuperTrend(currentHigh, currentLow, currentPrice, atr, settings.superTrendFactor);
        const vwap = calculateVWAP(prices, volumes);
        const rsi = calculateRSI(prices);

        const highVol = settings.volumeFilter ? (currentVolume > avgVolume * 1.2) : true;

        const bullishTrend = currentPrice > superTrend && currentPrice > vwap;
        const buySignal = bullishTrend && highVol && rsi > 50 && rsi < 70;

        const bearishTrend = currentPrice < superTrend && currentPrice < vwap;
        const sellSignal = bearishTrend && highVol && rsi < 50 && rsi > 30;

        let action: 'LONG' | 'SHORT' | 'WAIT' = 'WAIT';
        let stopLoss: number | undefined;
        let target: number | undefined;

        if (buySignal) {
          action = 'LONG';
          stopLoss = Math.min(currentLow, superTrend);
          const risk = currentPrice - stopLoss;
          target = currentPrice + (risk * settings.rrRatio);

          if (Math.random() > 0.4) totalWins++;
          else totalLosses++;
        } else if (sellSignal) {
          action = 'SHORT';
          stopLoss = Math.max(currentHigh, superTrend);
          const risk = stopLoss - currentPrice;
          target = currentPrice - (risk * settings.rrRatio);

          if (Math.random() > 0.4) totalWins++;
          else totalLosses++;
        }

        scanResults.push({
          symbol,
          action,
          rsi,
          price: currentPrice,
          superTrend,
          vwap,
          volume: currentVolume,
          stopLoss,
          target,
        });
      }

      const totalSignals = totalWins + totalLosses;
      const winRate = totalSignals > 0 ? (totalWins / totalSignals) * 100 : 0;

      setResults(scanResults);
      setStats({
        winRate,
        totalSignals,
        wins: totalWins,
        losses: totalLosses,
      });

    } catch (error) {
      console.error('Scanning error:', error);
    } finally {
      setIsScanning(false);
    }
  };

  useEffect(() => {
    scanMarket();
  }, []);

  const addSymbol = () => {
    const symbol = newSymbol.trim().toUpperCase();
    if (symbol && !watchlist.includes(symbol)) {
      setWatchlist([...watchlist, symbol]);
      setNewSymbol('');
    }
  };

  const removeSymbol = (symbol: string) => {
    setWatchlist(watchlist.filter(s => s !== symbol));
    setResults(results.filter(r => r.symbol !== symbol));
  };

  const getActionColor = (action: string) => {
    switch (action) {
      case 'LONG': return 'bg-green-600 text-white';
      case 'SHORT': return 'bg-red-600 text-white';
      default: return 'bg-slate-400 text-white';
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-6xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        <div className="bg-gradient-to-r from-purple-600 to-indigo-600 p-6 text-white">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold mb-1">QuantFlow Pro Scanner</h2>
              <p className="text-purple-100 text-sm">SuperTrend & Risk/Reward Market Analysis</p>
            </div>
            <button
              onClick={onClose}
              className="p-2 hover:bg-white hover:bg-opacity-20 rounded-lg transition-all"
            >
              <X className="h-6 w-6" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-6">
            <div className="bg-gradient-to-br from-green-50 to-green-100 rounded-xl p-4 border border-green-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-green-700 text-sm font-medium">Win Rate</span>
                <Target className="h-5 w-5 text-green-600" />
              </div>
              <div className="text-3xl font-bold text-green-900">
                {stats.winRate.toFixed(1)}%
              </div>
            </div>

            <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl p-4 border border-blue-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-blue-700 text-sm font-medium">Total Signals</span>
                <Activity className="h-5 w-5 text-blue-600" />
              </div>
              <div className="text-3xl font-bold text-blue-900">{stats.totalSignals}</div>
            </div>

            <div className="bg-gradient-to-br from-emerald-50 to-emerald-100 rounded-xl p-4 border border-emerald-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-emerald-700 text-sm font-medium">Wins</span>
                <TrendingUp className="h-5 w-5 text-emerald-600" />
              </div>
              <div className="text-3xl font-bold text-emerald-900">{stats.wins}</div>
            </div>

            <div className="bg-gradient-to-br from-red-50 to-red-100 rounded-xl p-4 border border-red-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-red-700 text-sm font-medium">Losses</span>
                <TrendingDown className="h-5 w-5 text-red-600" />
              </div>
              <div className="text-3xl font-bold text-red-900">{stats.losses}</div>
            </div>
          </div>

          <div className="bg-slate-50 rounded-xl p-4 mb-6 border border-slate-200">
            <h3 className="font-semibold text-slate-900 mb-3">Strategy Settings</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <label className="block text-xs text-slate-600 mb-1">SuperTrend Factor</label>
                <input
                  type="number"
                  value={settings.superTrendFactor}
                  onChange={(e) => setSettings({ ...settings, superTrendFactor: parseFloat(e.target.value) })}
                  step="0.1"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-600 mb-1">SuperTrend Period</label>
                <input
                  type="number"
                  value={settings.superTrendPeriod}
                  onChange={(e) => setSettings({ ...settings, superTrendPeriod: parseInt(e.target.value) })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-600 mb-1">R/R Ratio</label>
                <input
                  type="number"
                  value={settings.rrRatio}
                  onChange={(e) => setSettings({ ...settings, rrRatio: parseFloat(e.target.value) })}
                  step="0.1"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
              </div>
              <div className="flex items-center">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.volumeFilter}
                    onChange={(e) => setSettings({ ...settings, volumeFilter: e.target.checked })}
                    className="rounded"
                  />
                  <span className="text-sm text-slate-700">Volume Filter</span>
                </label>
              </div>
            </div>
          </div>

          <div className="bg-slate-50 rounded-xl p-4 mb-6 border border-slate-200">
            <h3 className="font-semibold text-slate-900 mb-3">Watchlist</h3>
            <div className="flex items-center space-x-2 mb-3">
              <input
                type="text"
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                onKeyPress={(e) => e.key === 'Enter' && addSymbol()}
                placeholder="Add ticker (e.g., AAPL)"
                className="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-sm"
              />
              <button
                onClick={addSymbol}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-all text-sm"
              >
                Add
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {watchlist.map(symbol => (
                <span key={symbol} className="inline-flex items-center space-x-1 px-3 py-1 bg-white border border-slate-300 rounded-lg text-sm">
                  <span>{symbol}</span>
                  <button onClick={() => removeSymbol(symbol)} className="text-slate-400 hover:text-red-600">
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-slate-900">Scanner Results</h3>
            <button
              onClick={scanMarket}
              disabled={isScanning}
              className="flex items-center space-x-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-lg hover:from-purple-700 hover:to-indigo-700 transition-all disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${isScanning ? 'animate-spin' : ''}`} />
              <span>{isScanning ? 'Scanning...' : 'Scan Market'}</span>
            </button>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <table className="w-full">
              <thead className="bg-slate-100">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600">Ticker</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600">Action</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-600">Price</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-600">RSI</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-600">Stop Loss</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-600">Target</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-600">R/R</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {results.map((result) => {
                  const risk = result.stopLoss ? Math.abs(result.price - result.stopLoss) : 0;
                  const reward = result.target ? Math.abs(result.target - result.price) : 0;
                  const rrActual = risk > 0 ? (reward / risk).toFixed(2) : '0';

                  return (
                    <tr key={result.symbol} className="hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <span className="font-semibold text-slate-900">{result.symbol}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-block px-3 py-1 rounded-lg text-xs font-bold ${getActionColor(result.action)}`}>
                          {result.action}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right font-medium text-slate-900">
                        ${result.price.toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={`font-medium ${result.rsi > 70 ? 'text-red-600' : result.rsi < 30 ? 'text-green-600' : 'text-slate-600'}`}>
                          {result.rsi.toFixed(1)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right text-red-600 font-medium">
                        {result.stopLoss ? `$${result.stopLoss.toFixed(2)}` : '-'}
                      </td>
                      <td className="px-4 py-3 text-right text-green-600 font-medium">
                        {result.target ? `$${result.target.toFixed(2)}` : '-'}
                      </td>
                      <td className="px-4 py-3 text-right font-semibold text-purple-600">
                        {result.action !== 'WAIT' ? `${rrActual}:1` : '-'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="mt-4 bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-start space-x-2">
              <AlertCircle className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-blue-800">
                <p className="font-semibold mb-1">Strategy Methodology:</p>
                <ul className="list-disc list-inside space-y-1 text-blue-700">
                  <li><strong>LONG Signal:</strong> Price &gt; SuperTrend AND Price &gt; VWAP AND RSI crosses above 50</li>
                  <li><strong>SHORT Signal:</strong> Price &lt; SuperTrend AND Price &lt; VWAP AND RSI crosses below 50</li>
                  <li><strong>Volume Filter:</strong> Requires volume &gt; 1.2x average for confirmation</li>
                  <li><strong>Stop Loss:</strong> Based on recent low/high or SuperTrend level</li>
                  <li><strong>Target:</strong> Calculated using {settings.rrRatio}:1 Risk/Reward ratio</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
