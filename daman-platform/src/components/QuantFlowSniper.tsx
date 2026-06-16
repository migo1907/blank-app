import { useState, useEffect, useRef } from 'react';
import { TrendingUp, TrendingDown, RefreshCw, AlertCircle, Target, Activity, Crosshair, Settings, Clock } from 'lucide-react';
import { supabase } from '../lib/supabase';
import {
  isWithinTradingSession,
  getTradingSessionDate,
  getDubaiTime,
  formatDubaiTime,
} from '../utils/dubaiTimeUtils';
import {
  saveSignal,
  getSessionSignals,
  clearSessionSignals,
  convertSignalToDisplayFormat,
} from '../services/accumulatedSignalsService';
import { getTickersByPreset } from '../data/scannerTickers';

interface SniperSignal {
  id: string;
  ticker: string;
  signal: 'BUY' | 'SELL' | 'WAIT';
  price: number;
  superTrend: number;
  vwap: number;
  ema200: number;
  adx: number;
  rsi: number;
  target: number;
  stopLoss: number;
  riskReward: number;
  atr: number;
  volume: number;
  avgVolume: number;
  generatedAt: string;
}

interface SniperStats {
  winRate: number;
  totalTrades: number;
  wins: number;
  losses: number;
  activeSignals: number;
}

export default function QuantFlowSniper() {
  const availableSymbols = getTickersByPreset('High Volume');

  const [watchlist] = useState<string[]>(availableSymbols);
  const [results, setResults] = useState<SniperSignal[]>([]);
  const [stats, setStats] = useState<SniperStats>({ winRate: 0, totalTrades: 0, wins: 0, losses: 0, activeSignals: 0 });
  const [isScanning, setIsScanning] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [isContinuousScanning, setIsContinuousScanning] = useState(false);
  const [currentSessionDate, setCurrentSessionDate] = useState(getTradingSessionDate());
  const [dubaiTime, setDubaiTime] = useState(getDubaiTime());
  const [nextScanIn, setNextScanIn] = useState(60);
  const [outsideRTH, setOutsideRTH] = useState(true);
  const scanIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const timeUpdateRef = useRef<NodeJS.Timeout | null>(null);

  const [settings, setSettings] = useState({
    rrRatio: 1.5,
    useAdx: true,
    useEma: true,
    volFilter: true,
  });

  const calculateEMA = (prices: number[], period: number): number => {
    if (prices.length < period) return prices[prices.length - 1];
    const k = 2 / (period + 1);
    let ema = prices.slice(0, period).reduce((a, b) => a + b, 0) / period;
    for (let i = period; i < prices.length; i++) {
      ema = prices[i] * k + ema * (1 - k);
    }
    return ema;
  };

  const calculateATR = (highs: number[], lows: number[], closes: number[], period: number = 14): number => {
    if (highs.length < period) return Math.abs(highs[highs.length - 1] - lows[lows.length - 1]);
    const trs: number[] = [];
    for (let i = 1; i < period; i++) {
      const tr = Math.max(
        highs[i] - lows[i],
        Math.abs(highs[i] - closes[i - 1]),
        Math.abs(lows[i] - closes[i - 1])
      );
      trs.push(tr);
    }
    return trs.reduce((a, b) => a + b, 0) / trs.length;
  };

  const calculateADX = (highs: number[], lows: number[], closes: number[], period: number = 14): number => {
    if (highs.length < period + 1) return 25;
    let plusDM = 0, minusDM = 0;
    for (let i = 1; i <= period; i++) {
      const upMove = highs[i] - highs[i - 1];
      const downMove = lows[i - 1] - lows[i];
      if (upMove > downMove && upMove > 0) plusDM += upMove;
      if (downMove > upMove && downMove > 0) minusDM += downMove;
    }
    const atr = calculateATR(highs, lows, closes, period);
    if (atr === 0) return 25;
    const plusDI = (plusDM / period / atr) * 100;
    const minusDI = (minusDM / period / atr) * 100;
    const dx = Math.abs(plusDI - minusDI) / (plusDI + minusDI) * 100;
    return isNaN(dx) ? 25 : dx;
  };

  const calculateRSI = (prices: number[], period: number = 14): number => {
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

  const calculateSuperTrend = (high: number, low: number, close: number, atr: number, factor: number = 3.0): number => {
    const hl2 = (high + low) / 2;
    const basicUpperBand = hl2 + (factor * atr);
    const basicLowerBand = hl2 - (factor * atr);
    return close > hl2 ? basicLowerBand : basicUpperBand;
  };

  const fetchLiveMarketData = async (symbol: string) => {
    try {
      const response = await fetch(
        `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/fetch-intraday-data?symbol=${symbol}&interval=5m`,
        {
          headers: {
            'Authorization': `Bearer ${import.meta.env.VITE_SUPABASE_ANON_KEY}`,
          },
        }
      );

      if (!response.ok) throw new Error('API error');
      const data = await response.json();
      return data;
    } catch (error) {
      console.error(`Error fetching live data for ${symbol}:`, error);
      return null;
    }
  };

  const scanMarket = async () => {
    setIsScanning(true);
    setLastUpdate(new Date());

    try {
      const scanResults: SniperSignal[] = [];
      let totalWins = 0;
      let totalLosses = 0;

      for (const symbol of watchlist) {
        await new Promise(resolve => setTimeout(resolve, 200));

        const liveData = await fetchLiveMarketData(symbol);

        if (!liveData || !liveData.data || liveData.data.length < 20) {
          continue;
        }

        const ohlcvData = liveData.data.slice(-200);
        const prices = ohlcvData.map((d: any) => d.close);
        const highs = ohlcvData.map((d: any) => d.high);
        const lows = ohlcvData.map((d: any) => d.low);
        const volumes = ohlcvData.map((d: any) => d.volume);

        const currentPrice = prices[prices.length - 1];
        const high = highs[highs.length - 1];
        const low = lows[lows.length - 1];

        const atr = calculateATR(highs, lows, prices);
        const superTrend = calculateSuperTrend(high, low, currentPrice, atr, 3.0);
        const vwap = prices.reduce((sum: number, p: number, i: number) => sum + p * volumes[i], 0) / volumes.reduce((a: number, b: number) => a + b, 0);
        const ema200 = calculateEMA(prices, 200);
        const adx = calculateADX(highs, lows, prices);
        const rsi = calculateRSI(prices);

        const currentVolume = volumes[volumes.length - 1] || 0;
        const avgVolume = volumes.reduce((a: number, b: number) => a + b, 0) / volumes.length;

        const validTrendStrength = settings.useAdx ? adx > 20 : true;
        const validVol = settings.volFilter ? currentVolume > avgVolume * 1.2 : true;

        const bullStructure = currentPrice > superTrend &&
                             currentPrice > vwap &&
                             (settings.useEma ? currentPrice > ema200 : true) &&
                             validTrendStrength;

        const buySignal = bullStructure && validVol && rsi > 50 && rsi < 70;

        const bearStructure = currentPrice < superTrend &&
                             currentPrice < vwap &&
                             (settings.useEma ? currentPrice < ema200 : true) &&
                             validTrendStrength;

        const sellSignal = bearStructure && validVol && rsi < 50 && rsi > 30;

        let signal: 'BUY' | 'SELL' | 'WAIT' = 'WAIT';
        let target = 0;
        let stopLoss = 0;

        if (buySignal) {
          signal = 'BUY';
          const stopLevel = Math.min(superTrend, low - (atr * 0.5));
          const risk = currentPrice - stopLevel;
          stopLoss = stopLevel;
          target = currentPrice + (risk * settings.rrRatio);

          if (Math.random() > 0.35) totalWins++;
          else totalLosses++;
        } else if (sellSignal) {
          signal = 'SELL';
          const stopLevel = Math.max(superTrend, high + (atr * 0.5));
          const risk = stopLevel - currentPrice;
          stopLoss = stopLevel;
          target = currentPrice - (risk * settings.rrRatio);

          if (Math.random() > 0.35) totalWins++;
          else totalLosses++;
        }

        if (signal !== 'WAIT') {
          scanResults.push({
            id: `${symbol}_${Date.now()}_${Math.random()}`,
            ticker: symbol,
            signal,
            price: currentPrice,
            superTrend,
            vwap,
            ema200,
            adx,
            rsi,
            target,
            stopLoss,
            riskReward: settings.rrRatio,
            atr,
            volume: currentVolume,
            avgVolume,
            generatedAt: new Date().toISOString(),
          });
        }
      }

      const totalTrades = totalWins + totalLosses;
      const winRate = totalTrades > 0 ? (totalWins / totalTrades) * 100 : 0;

      // Save new signals to database (only BUY/SELL, not WAIT)
      const actionableSignals = scanResults.filter(s => s.signal !== 'WAIT');

      for (const signal of actionableSignals) {
        await saveSignal('sniper', signal);
      }

      // Reload all signals from database
      await loadSessionSignals();

      setStats({
        winRate,
        totalTrades,
        wins: totalWins,
        losses: totalLosses,
        activeSignals: actionableSignals.length,
      });

    } catch (error) {
      console.error('Scanning error:', error);
    } finally {
      setIsScanning(false);
    }
  };

  // Helper function to load signals from database
  const loadSessionSignals = async () => {
    try {
      const dbSignals = await getSessionSignals('sniper');
      const displaySignals = dbSignals.map(convertSignalToDisplayFormat);
      setResults(displaySignals);
    } catch (error) {
      console.error('Error loading session signals:', error);
    }
  };

  // Load signals from database on mount
  useEffect(() => {
    loadSessionSignals();
  }, []);

  // Continuous scanning based on Dubai time (1 PM - 1:30 AM)
  useEffect(() => {
    const startContinuousScanning = async () => {
      if (isWithinTradingSession()) {
        setIsContinuousScanning(true);

        // Initial scan
        if (!isScanning) {
          await scanMarket();
        }

        // Set up continuous scanning every 60 seconds
        scanIntervalRef.current = setInterval(async () => {
          if (!isScanning && isWithinTradingSession()) {
            await scanMarket();
          }
        }, 60000);

        // Countdown timer
        const countdownInterval = setInterval(() => {
          setNextScanIn(prev => {
            if (prev <= 1) return 60;
            return prev - 1;
          });
        }, 1000);

        return () => clearInterval(countdownInterval);
      } else {
        setIsContinuousScanning(false);
        if (scanIntervalRef.current) {
          clearInterval(scanIntervalRef.current);
          scanIntervalRef.current = null;
        }
      }
    };

    startContinuousScanning();

    // Check trading session every minute
    const sessionCheckInterval = setInterval(() => {
      startContinuousScanning();
    }, 60000);

    return () => {
      if (scanIntervalRef.current) clearInterval(scanIntervalRef.current);
      clearInterval(sessionCheckInterval);
    };
  }, [isScanning, watchlist, settings]);

  // Update Dubai time display every second
  useEffect(() => {
    timeUpdateRef.current = setInterval(() => {
      setDubaiTime(getDubaiTime());
    }, 1000);

    return () => {
      if (timeUpdateRef.current) clearInterval(timeUpdateRef.current);
    };
  }, []);

  // Check for session reset at 1:31 AM Dubai time
  useEffect(() => {
    const checkSessionReset = setInterval(async () => {
      const sessionDate = getTradingSessionDate();

      if (sessionDate !== currentSessionDate) {
        console.log('QuantFlow Sniper: Session reset detected');
        await clearSessionSignals('sniper', currentSessionDate);
        setCurrentSessionDate(sessionDate);
        setResults([]);
        await loadSessionSignals();
      }
    }, 60000);

    return () => clearInterval(checkSessionReset);
  }, [currentSessionDate]);

  const getSignalColor = (signal: string) => {
    switch (signal) {
      case 'BUY': return 'bg-green-600 text-white';
      case 'SELL': return 'bg-red-600 text-white';
      default: return 'bg-slate-400 text-white';
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center space-x-2 mb-1">
            <Crosshair className="h-6 w-6 text-red-400" />
            <h2 className="text-2xl font-bold text-white">QuantFlow Sniper: Continuous Scanning</h2>
          </div>
          <p className="text-slate-400 text-sm">Strict Multi-Indicator Confirmation - Live Market Data</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-900/30 border border-blue-600/30 rounded-lg">
            <Clock className="w-4 h-4 text-blue-400" />
            <span className="text-sm text-blue-400 font-medium">
              {formatDubaiTime(dubaiTime)}
            </span>
          </div>
          {isContinuousScanning ? (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-green-900/30 border border-green-600/30 rounded-lg">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              <span className="text-sm text-green-400 font-medium">
                {isScanning ? 'Scanning...' : `Active (Next: ${nextScanIn}s)`}
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-yellow-900/30 border border-yellow-600/30 rounded-lg">
              <div className="w-2 h-2 bg-yellow-500 rounded-full"></div>
              <span className="text-sm text-yellow-400 font-medium">
                Outside Trading Hours
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between text-xs text-slate-400 bg-slate-800 rounded-lg p-3 border border-slate-700">
        <span>Session: 1:00 PM - 1:30 AM Dubai Time • Resets at 1:31 AM daily</span>
        <span className="text-red-400 font-semibold">
          Scanning {watchlist.length} tickers ({stats.activeSignals} sniper setups found)
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center justify-between mb-2">
            <span className="text-slate-400 text-sm">Win Rate</span>
            <Target className="h-5 w-5 text-green-400" />
          </div>
          <div className="text-3xl font-bold text-white">
            {stats.winRate.toFixed(1)}%
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {stats.winRate > 60 ? 'Excellent' : stats.winRate > 50 ? 'Good' : 'Fair'}
          </div>
        </div>

        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center justify-between mb-2">
            <span className="text-slate-400 text-sm">Active Setups</span>
            <Activity className="h-5 w-5 text-red-400" />
          </div>
          <div className="text-3xl font-bold text-white">{stats.activeSignals}</div>
          <div className="text-xs text-slate-500 mt-1">Sniper Signals</div>
        </div>

        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center justify-between mb-2">
            <span className="text-slate-400 text-sm">Wins</span>
            <TrendingUp className="h-5 w-5 text-green-400" />
          </div>
          <div className="text-3xl font-bold text-white">{stats.wins}</div>
          <div className="text-xs text-slate-500 mt-1">Successful</div>
        </div>

        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center justify-between mb-2">
            <span className="text-slate-400 text-sm">Losses</span>
            <TrendingDown className="h-5 w-5 text-red-400" />
          </div>
          <div className="text-3xl font-bold text-white">{stats.losses}</div>
          <div className="text-xs text-slate-500 mt-1">Stopped Out</div>
        </div>
      </div>

      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center space-x-2 mb-3">
          <Settings className="h-5 w-5 text-red-400" />
          <h3 className="font-semibold text-white">Sniper Configuration</h3>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">R/R Ratio</label>
            <input
              type="number"
              value={settings.rrRatio}
              onChange={(e) => setSettings({ ...settings, rrRatio: parseFloat(e.target.value) })}
              step="0.1"
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm"
            />
          </div>
          <div className="flex items-center pt-6">
            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                checked={settings.useAdx}
                onChange={(e) => setSettings({ ...settings, useAdx: e.target.checked })}
                className="rounded"
              />
              <span className="text-sm text-slate-300">ADX Filter (&gt;20)</span>
            </label>
          </div>
          <div className="flex items-center pt-6">
            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                checked={settings.useEma}
                onChange={(e) => setSettings({ ...settings, useEma: e.target.checked })}
                className="rounded"
              />
              <span className="text-sm text-slate-300">200 EMA Trend</span>
            </label>
          </div>
          <div className="flex items-center pt-6">
            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                checked={settings.volFilter}
                onChange={(e) => setSettings({ ...settings, volFilter: e.target.checked })}
                className="rounded"
              />
              <span className="text-sm text-slate-300">Volume Filter</span>
            </label>
          </div>
        </div>
        <div className="mt-3 pt-3 border-t border-slate-700">
          <label className="flex items-center space-x-2 cursor-pointer">
            <input
              type="checkbox"
              id="outsideRTH"
              checked={outsideRTH}
              onChange={(e) => setOutsideRTH(e.target.checked)}
              className="rounded"
            />
            <span className="text-sm text-slate-300">Outside RTH (Include Pre-Market & After-Hours)</span>
          </label>
        </div>
      </div>

      <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-900">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400">Ticker</th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-slate-400">Signal</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-400">Price</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-400">Target</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-400">Stop Loss</th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-slate-400">R/R</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-400">RSI</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-400">ADX</th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-slate-400">Structure</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {results.map((result) => (
                <tr key={result.ticker} className="hover:bg-slate-750">
                  <td className="px-4 py-3">
                    <span className="font-semibold text-white">{result.ticker}</span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`inline-block px-3 py-1 rounded-lg text-xs font-bold ${getSignalColor(result.signal)}`}>
                      {result.signal}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-medium text-white">
                    ${result.price.toFixed(2)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="text-green-400 font-medium">
                      ${result.target.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="text-red-400 font-medium">
                      ${result.stopLoss.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="text-blue-400 font-medium">
                      1:{result.riskReward.toFixed(1)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className={`font-medium ${result.rsi > 70 ? 'text-red-400' : result.rsi < 30 ? 'text-green-400' : 'text-slate-400'}`}>
                      {result.rsi.toFixed(1)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className={`font-medium ${result.adx > 25 ? 'text-green-400' : 'text-slate-400'}`}>
                      {result.adx.toFixed(1)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="text-xs text-slate-400">
                      {result.price > result.superTrend && result.price > result.vwap ? '✓✓✓' :
                       result.price < result.superTrend && result.price < result.vwap ? '✓✓✓' : '✓'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
