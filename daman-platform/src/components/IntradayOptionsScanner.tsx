import { useState, useEffect, useRef } from 'react';
import { Clock, TrendingUp, TrendingDown, Target, AlertCircle, Play, Square, RefreshCw, Database, Zap } from 'lucide-react';
import { supabase } from '../lib/supabase';
import { fetchLiveData as fetchLiveDataUtil } from '../utils/liveDataFetcher';

interface OptionsSignal {
  id?: string;
  timestamp: string;
  ticker: string;
  side: 'LONG' | 'SHORT';
  optionsStrike: number;
  expiryDate: string;
  delta: number;
  optionEntry: number;
  optionStop: number;
  optionTarget: number;
  optionRR: number;
  stockEntry: number;
  stockStop: number;
  stockTarget: number;
  stockRR: number;
  atr: number;
  rsi: number;
  macdHist: number;
  vwap: number;
  impliedVol: number;
  signalTime: string;
}

interface ScanSettings {
  rrMin: number;
  volumeMult: number;
  vwapTolerance: number;
  rsiLongMin: number;
  rsiLongMax: number;
  rsiShortMin: number;
  rsiShortMax: number;
  requireTrendStack: boolean;
  requireMacdRising: boolean;
  optionsDte: number;
  deltaMin: number;
  deltaMax: number;
  minOptionVolume: number;
  minOpenInterest: number;
  aggressiveMode: boolean;
}

interface ScanStats {
  totalScanned: number;
  signalsFound: number;
  rejectedCount: number;
  reasons: Record<string, number>;
}

interface SymbolAnalysis {
  symbol: string;
  timestamp: string;
  status: 'rejected' | 'accepted';
  reason: string;
  details: any;
}

const WATCHLIST = [
  'SPY', 'QQQ', 'IWM', 'DIA',
  'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN', 'GOOGL', 'META', 'AMD',
  'TSLL', 'TQQQ', 'SOXL', 'LABU', 'UVXY', 'NFLX', 'CRM', 'AVGO'
];

const PRESETS = {
  balanced: {
    rrMin: 1.6,
    volumeMult: 1.1,
    vwapTolerance: 0.0003,
    rsiLongMin: 53,
    rsiLongMax: 67,
    rsiShortMin: 33,
    rsiShortMax: 47,
    deltaMin: 0.40,
    deltaMax: 0.70,
    minOptionVolume: 50,
    minOpenInterest: 500,
  },
  aggressive: {
    rrMin: 1.5,
    volumeMult: 1.05,
    vwapTolerance: 0.0005,
    rsiLongMin: 50,
    rsiLongMax: 70,
    rsiShortMin: 30,
    rsiShortMax: 50,
    deltaMin: 0.35,
    deltaMax: 0.65,
    minOptionVolume: 30,
    minOpenInterest: 300,
  },
  aggressiveOptions: {
    rrMin: 2.0,
    volumeMult: 1.0,
    vwapTolerance: 0.0005,
    rsiLongMin: 50,
    rsiLongMax: 70,
    rsiShortMin: 30,
    rsiShortMax: 50,
    deltaMin: 0.30,
    deltaMax: 0.60,
    minOptionVolume: 10,
    minOpenInterest: 100,
  },
};

export default function IntradayOptionsScanner() {
  const [isScanning, setIsScanning] = useState(false);
  const [signals, setSignals] = useState<OptionsSignal[]>([]);
  const [lastScanTime, setLastScanTime] = useState<Date | null>(null);
  const [dubaiTime, setDubaiTime] = useState<string>('');
  const [isWithinWindow, setIsWithinWindow] = useState(false);
  const [preset, setPreset] = useState<'balanced' | 'aggressive' | 'aggressiveOptions'>('balanced');
  const [liveDataStatus, setLiveDataStatus] = useState<'connected' | 'fetching' | 'error' | 'idle'>('idle');
  const [lastDataUpdate, setLastDataUpdate] = useState<Date | null>(null);
  const [dataFeedCount, setDataFeedCount] = useState(0);
  const scanIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const [scanStats, setScanStats] = useState<ScanStats>({ totalScanned: 0, signalsFound: 0, rejectedCount: 0, reasons: {} });
  const [analysisLog, setAnalysisLog] = useState<SymbolAnalysis[]>([]);
  const [showDebugPanel, setShowDebugPanel] = useState(false);
  const [settings, setSettings] = useState<ScanSettings>({
    rrMin: 1.6,
    volumeMult: 1.1,
    vwapTolerance: 0.0003,
    rsiLongMin: 53,
    rsiLongMax: 67,
    rsiShortMin: 33,
    rsiShortMax: 47,
    requireTrendStack: true,
    requireMacdRising: false,
    optionsDte: 1,
    deltaMin: 0.40,
    deltaMax: 0.70,
    minOptionVolume: 50,
    minOpenInterest: 500,
    aggressiveMode: false,
  });

  useEffect(() => {
    loadHistoricalSignals();
    const timer = setInterval(updateDubaiTime, 1000);
    return () => {
      clearInterval(timer);
      if (scanIntervalRef.current) {
        clearInterval(scanIntervalRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (isWithinWindow && !isScanning) {
      startScanning();
    } else if (!isWithinWindow && isScanning) {
      stopScanning();
    }
  }, [isWithinWindow]);

  useEffect(() => {
    const presetSettings = PRESETS[preset];
    setSettings(prev => ({ ...prev, ...presetSettings }));
  }, [preset]);

  const updateDubaiTime = () => {
    const now = new Date();
    const dubaiFormatter = new Intl.DateTimeFormat('en-US', {
      timeZone: 'Asia/Dubai',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
    const dubaiTimeStr = dubaiFormatter.format(now);
    setDubaiTime(dubaiTimeStr);

    const [hours, minutes] = dubaiTimeStr.split(':').map(Number);
    const totalMinutes = hours * 60 + minutes;
    const startMinutes = 13 * 60;
    const endMinutes = 1 * 60 + 30;
    const within = totalMinutes >= startMinutes || totalMinutes <= endMinutes;
    setIsWithinWindow(within);
  };

  const logAnalysis = (symbol: string, status: 'rejected' | 'accepted', reason: string, details: any) => {
    const analysis: SymbolAnalysis = {
      symbol,
      timestamp: new Date().toISOString(),
      status,
      reason,
      details
    };
    setAnalysisLog(prev => [...prev.slice(-49), analysis]);
  };

  const loadHistoricalSignals = async () => {
    try {
      const { data, error } = await supabase
        .from('intraday_options_signals')
        .select('*')
        .order('signal_time', { ascending: false })
        .limit(100);

      if (error) throw error;

      if (data) {
        const mapped: OptionsSignal[] = data.map((row: any) => ({
          id: row.id,
          timestamp: row.timestamp,
          ticker: row.ticker,
          side: row.side,
          optionsStrike: row.options_strike,
          expiryDate: row.expiry_date,
          delta: row.delta,
          optionEntry: row.option_entry,
          optionStop: row.option_stop,
          optionTarget: row.option_target,
          optionRR: row.option_rr,
          stockEntry: row.stock_entry,
          stockStop: row.stock_stop,
          stockTarget: row.stock_target,
          stockRR: row.stock_rr,
          atr: row.atr,
          rsi: row.rsi,
          macdHist: row.macd_hist,
          vwap: row.vwap,
          impliedVol: row.implied_vol || 0,
          signalTime: row.signal_time,
        }));
        setSignals(mapped);
      }
    } catch (error) {
      console.error('Error loading signals:', error);
    }
  };

  const saveSignalToDatabase = async (signal: OptionsSignal) => {
    try {
      const { error } = await supabase
        .from('intraday_options_signals')
        .insert({
          timestamp: signal.timestamp,
          ticker: signal.ticker,
          side: signal.side,
          options_strike: signal.optionsStrike,
          expiry_date: signal.expiryDate,
          delta: signal.delta,
          option_entry: signal.optionEntry,
          option_stop: signal.optionStop,
          option_target: signal.optionTarget,
          option_rr: signal.optionRR,
          stock_entry: signal.stockEntry,
          stock_stop: signal.stockStop,
          stock_target: signal.stockTarget,
          stock_rr: signal.stockRR,
          atr: signal.atr,
          rsi: signal.rsi,
          macd_hist: signal.macdHist,
          vwap: signal.vwap,
          implied_vol: signal.impliedVol,
          signal_time: signal.signalTime,
        });

      if (error) throw error;
    } catch (error) {
      console.error('Error saving signal:', error);
    }
  };

  const calculateEMA = (prices: number[], period: number): number => {
    if (prices.length < period) return prices[prices.length - 1];
    const k = 2 / (period + 1);
    let ema = prices.slice(0, period).reduce((a, b) => a + b) / period;
    for (let i = period; i < prices.length; i++) {
      ema = prices[i] * k + ema * (1 - k);
    }
    return ema;
  };

  const calculateRSI = (prices: number[], period: number = 14): number => {
    if (prices.length < period + 1) return 50;

    let gains = 0;
    let losses = 0;

    for (let i = 1; i <= period; i++) {
      const diff = prices[prices.length - period + i] - prices[prices.length - period + i - 1];
      if (diff > 0) gains += diff;
      else losses -= diff;
    }

    let avgGain = gains / period;
    let avgLoss = losses / period;

    for (let i = prices.length - period + 1; i < prices.length; i++) {
      const diff = prices[i] - prices[i - 1];
      const gain = diff > 0 ? diff : 0;
      const loss = diff < 0 ? -diff : 0;
      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;
    }

    const rs = avgGain / (avgLoss + 1e-9);
    return 100 - 100 / (1 + rs);
  };

  const calculateMACD = (prices: number[]): { line: number; signal: number; hist: number } => {
    if (prices.length < 26) {
      return { line: 0, signal: 0, hist: 0 };
    }

    const macdLine: number[] = [];
    for (let i = 26; i <= prices.length; i++) {
      const slice = prices.slice(0, i);
      const ema12 = calculateEMA(slice, 12);
      const ema26 = calculateEMA(slice, 26);
      macdLine.push(ema12 - ema26);
    }

    const line = macdLine[macdLine.length - 1];
    const signal = calculateEMA(macdLine, 9);
    const hist = line - signal;
    return { line, signal, hist };
  };

  const calculateATR = (highs: number[], lows: number[], closes: number[], period: number = 14): number => {
    if (highs.length < period + 1 || lows.length < period + 1 || closes.length < period + 1) return 0;
    const trs: number[] = [];
    const startIdx = Math.max(1, highs.length - period);
    for (let i = startIdx; i < highs.length; i++) {
      const tr = Math.max(
        Math.max(0, highs[i] - lows[i]),
        Math.abs(highs[i] - closes[i - 1]),
        Math.abs(lows[i] - closes[i - 1])
      );
      trs.push(tr);
    }
    return trs.length > 0 ? trs.reduce((a, b) => a + b, 0) / trs.length : 0;
  };

  const calculateVWAP = (prices: number[], volumes: number[]): number => {
    const pv = prices.reduce((sum, p, i) => sum + p * volumes[i], 0);
    const totalVol = volumes.reduce((a, b) => a + b, 0);
    return totalVol > 0 ? pv / totalVol : prices[prices.length - 1];
  };

  const fetchRealOptionPrice = async (symbol: string, strike: number, optionType: 'CALL' | 'PUT'): Promise<number | null> => {
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      const response = await fetch(
        `${supabaseUrl}/functions/v1/fetch-options-prices?symbol=${symbol}`,
        {
          headers: {
            'Authorization': `Bearer ${supabaseKey}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        return null;
      }

      const result = await response.json();

      if (!result.success || !result.data) {
        return null;
      }

      const optionsData = result.data;
      const optionsList = optionType === 'CALL' ? optionsData.calls : optionsData.puts;

      if (!Array.isArray(optionsList) || optionsList.length === 0) {
        return null;
      }

      const targetDTE = settings.optionsDte;
      const targetExpiry = new Date();
      targetExpiry.setDate(targetExpiry.getDate() + targetDTE);

      let closestOption = null;
      let minStrikeDiff = Infinity;

      for (const opt of optionsList) {
        const strikeDiff = Math.abs(opt.strike - strike);
        if (strikeDiff < minStrikeDiff && strikeDiff < 5) {
          minStrikeDiff = strikeDiff;
          closestOption = opt;
        }
      }

      if (closestOption) {
        const price = closestOption.mid || closestOption.last || closestOption.bid || 0;
        if (price > 0 && price < strike * 0.5) {
          return price;
        }
      }

      return null;
    } catch (error) {
      return null;
    }
  };

  const fetchLiveData = async (symbol: string) => {
    try {
      setLiveDataStatus('fetching');
      const data = await fetchLiveDataUtil({
        symbol,
        interval: '15m',
        days: 60,
        includeExtendedHours: true,
        retries: 3,
        retryDelay: 1000,
      });

      if (data && data.success) {
        setLiveDataStatus('connected');
        setLastDataUpdate(new Date());
        setDataFeedCount(prev => prev + 1);
      } else {
        setLiveDataStatus('error');
      }

      return data;
    } catch (error) {
      console.error(`Error fetching data for ${symbol}:`, error);
      setLiveDataStatus('error');
      return null;
    }
  };

  const analyzeSymbol = async (symbol: string): Promise<OptionsSignal | null> => {
    const liveData = await fetchLiveData(symbol);
    if (!liveData || !liveData.data || liveData.data.length < 50) {
      logAnalysis(symbol, 'rejected', `Insufficient data (${liveData?.data?.length || 0} bars, need 50+)`, {});
      return null;
    }

    const ohlcvData = liveData.data.slice(-200);
    const prices = ohlcvData.map((d: any) => d.close).filter((p: number) => p && !isNaN(p));
    const highs = ohlcvData.map((d: any) => d.high).filter((h: number) => h && !isNaN(h));
    const lows = ohlcvData.map((d: any) => d.low).filter((l: number) => l && !isNaN(l));
    const volumes = ohlcvData.map((d: any) => d.volume).filter((v: number) => v !== undefined && !isNaN(v));

    if (prices.length < 50 || highs.length < 50 || lows.length < 50) {
      logAnalysis(symbol, 'rejected', 'Invalid or missing OHLCV data after filtering', {});
      return null;
    }

    const currentPrice = prices[prices.length - 1];
    const currentVolume = volumes[volumes.length - 1] || 0;
    const avgVolume = volumes.slice(-20).reduce((a, b) => a + b, 0) / Math.max(1, volumes.slice(-20).length);

    const ema20 = calculateEMA(prices, 20);
    const ema50 = calculateEMA(prices, 50);
    const rsi = calculateRSI(prices, 14);
    const macd = calculateMACD(prices);
    const atr = calculateATR(highs, lows, prices, 14);
    const vwap = calculateVWAP(prices, volumes);

    if (!isFinite(ema20) || !isFinite(ema50) || !isFinite(rsi) || !isFinite(atr) || !isFinite(vwap)) {
      logAnalysis(symbol, 'rejected', 'Invalid indicator calculations (NaN/Infinity)', { ema20, ema50, rsi, atr, vwap });
      return null;
    }

    const volumeCheck = currentVolume >= avgVolume * settings.volumeMult;

    const trendLong = settings.requireTrendStack
      ? currentPrice > ema20 && ema20 > ema50
      : ema20 > ema50;
    const trendShort = settings.requireTrendStack
      ? currentPrice < ema20 && ema20 < ema50
      : ema20 < ema50;

    const rsiLongOk = rsi >= settings.rsiLongMin && rsi <= settings.rsiLongMax;
    const rsiShortOk = rsi >= settings.rsiShortMin && rsi <= settings.rsiShortMax;

    const macdLong = macd.hist > 0;
    const macdShort = macd.hist < 0;

    const vwapTol = settings.vwapTolerance;
    const vwapLong = currentPrice >= vwap * (1 - vwapTol);
    const vwapShort = currentPrice <= vwap * (1 + vwapTol);

    const longSignal = trendLong && rsiLongOk && macdLong && vwapLong && volumeCheck;
    const shortSignal = trendShort && rsiShortOk && macdShort && vwapShort && volumeCheck;

    if (!longSignal && !shortSignal) return null;

    const side: 'LONG' | 'SHORT' = longSignal ? 'LONG' : 'SHORT';

    const atrMultStop = 1.5;
    const atrMultTarget = 2.0;

    const stockEntry = currentPrice;
    const stockStop = side === 'LONG' ? stockEntry - atrMultStop * atr : stockEntry + atrMultStop * atr;
    const stockTarget = side === 'LONG' ? stockEntry + atrMultTarget * atr : stockEntry - atrMultTarget * atr;
    const stockRR = side === 'LONG'
      ? (stockTarget - stockEntry) / (stockEntry - stockStop + 1e-9)
      : (stockEntry - stockTarget) / (stockStop - stockEntry + 1e-9);

    if (stockRR < settings.rrMin) return null;

    const deltaTarget = (settings.deltaMin + settings.deltaMax) / 2;
    const optionsStrike = side === 'LONG'
      ? Math.round((stockEntry * 1.02) / 5) * 5
      : Math.round((stockEntry * 0.98) / 5) * 5;

    const strikeDistance = Math.abs(optionsStrike - stockEntry) / stockEntry;
    const estimatedDelta = side === 'LONG'
      ? Math.max(settings.deltaMin, deltaTarget - strikeDistance * 2)
      : Math.max(settings.deltaMin, deltaTarget - strikeDistance * 2);

    const optionType: 'CALL' | 'PUT' = side === 'LONG' ? 'CALL' : 'PUT';
    let optionEntry = stockEntry * 0.035 * estimatedDelta;

    const realPrice = await fetchRealOptionPrice(symbol, optionsStrike, optionType);
    if (realPrice && realPrice > 0) {
      optionEntry = realPrice;
      console.log(`Using live option price for ${symbol} ${optionType}: $${realPrice.toFixed(2)}`);
    } else {
      console.log(`Falling back to simulated price for ${symbol}: $${optionEntry.toFixed(2)}`);
    }

    const stockMoveToStop = Math.abs(stockEntry - stockStop);
    const stockMoveToTarget = Math.abs(stockTarget - stockEntry);

    const optionStop = optionEntry - stockMoveToStop * estimatedDelta;
    const optionTarget = optionEntry + stockMoveToTarget * estimatedDelta;
    const optionRR = (optionTarget - optionEntry) / (optionEntry - optionStop + 1e-9);

    if (optionRR < settings.rrMin) return null;
    if (optionStop <= 0) return null;

    const now = new Date();
    const expiryDate = new Date(now);
    expiryDate.setDate(expiryDate.getDate() + settings.optionsDte);

    const dubaiFormatter = new Intl.DateTimeFormat('en-US', {
      timeZone: 'Asia/Dubai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });

    const impliedVol = 0.30 + (Math.abs(rsi - 50) / 100);

    return {
      timestamp: now.toISOString(),
      ticker: symbol,
      side,
      optionsStrike,
      expiryDate: expiryDate.toISOString().split('T')[0],
      delta: parseFloat(estimatedDelta.toFixed(2)),
      optionEntry: parseFloat(optionEntry.toFixed(2)),
      optionStop: parseFloat(Math.max(0.01, optionStop).toFixed(2)),
      optionTarget: parseFloat(optionTarget.toFixed(2)),
      optionRR: parseFloat(optionRR.toFixed(2)),
      stockEntry: parseFloat(stockEntry.toFixed(2)),
      stockStop: parseFloat(stockStop.toFixed(2)),
      stockTarget: parseFloat(stockTarget.toFixed(2)),
      stockRR: parseFloat(stockRR.toFixed(2)),
      atr: parseFloat(atr.toFixed(4)),
      rsi: parseFloat(rsi.toFixed(2)),
      macdHist: parseFloat(macd.hist.toFixed(4)),
      vwap: parseFloat(vwap.toFixed(2)),
      impliedVol: parseFloat(impliedVol.toFixed(4)),
      signalTime: dubaiFormatter.format(now),
    };
  };

  const runScan = async () => {
    setLastScanTime(new Date());
    const newSignals: OptionsSignal[] = [];

    setScanStats({ totalScanned: 0, signalsFound: 0, rejectedCount: 0, reasons: {} });
    setAnalysisLog([]);

    for (const symbol of WATCHLIST) {
      await new Promise(resolve => setTimeout(resolve, 250));
      const signal = await analyzeSymbol(symbol);

      setScanStats(prev => ({
        ...prev,
        totalScanned: prev.totalScanned + 1,
        signalsFound: signal ? prev.signalsFound + 1 : prev.signalsFound,
        rejectedCount: signal ? prev.rejectedCount : prev.rejectedCount + 1,
      }));
      if (signal) {
        newSignals.push(signal);
        await saveSignalToDatabase(signal);
      }
    }

    if (newSignals.length > 0) {
      setSignals(prev => [...newSignals, ...prev].slice(0, 200));
    }
  };

  const startScanning = () => {
    setIsScanning(true);
    runScan();
    if (scanIntervalRef.current) {
      clearInterval(scanIntervalRef.current);
    }
    scanIntervalRef.current = setInterval(runScan, 2 * 1000);
  };

  const stopScanning = () => {
    setIsScanning(false);
    if (scanIntervalRef.current) {
      clearInterval(scanIntervalRef.current);
      scanIntervalRef.current = null;
    }
  };

  const clearSignals = async () => {
    if (confirm('Clear all accumulated signals from database?')) {
      try {
        await supabase.from('intraday_options_signals').delete().neq('id', '00000000-0000-0000-0000-000000000000');
        setSignals([]);
      } catch (error) {
        console.error('Error clearing signals:', error);
      }
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-lg border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 flex items-center space-x-2">
            <Target className="h-7 w-7 text-daman-blue-600" />
            <span>Intraday Options Scanner (0-2 DTE)</span>
          </h2>
          <p className="text-sm text-slate-600 mt-1 flex items-center space-x-2">
            <span>High-probability options signals with live data feed</span>
            <span className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
              liveDataStatus === 'connected' ? 'bg-green-100 text-green-700' :
              liveDataStatus === 'fetching' ? 'bg-blue-100 text-blue-700' :
              liveDataStatus === 'error' ? 'bg-red-100 text-red-700' :
              'bg-slate-100 text-slate-700'
            }`}>
              <span className={`h-1.5 w-1.5 rounded-full ${
                liveDataStatus === 'connected' ? 'bg-green-500 animate-pulse' :
                liveDataStatus === 'fetching' ? 'bg-blue-500 animate-pulse' :
                liveDataStatus === 'error' ? 'bg-red-500' :
                'bg-slate-400'
              }`}></span>
              <span>
                {liveDataStatus === 'connected' ? `Live (${dataFeedCount} updates)` :
                 liveDataStatus === 'fetching' ? 'Fetching...' :
                 liveDataStatus === 'error' ? 'Connection Error' :
                 'Ready'}
              </span>
            </span>
          </p>
        </div>
        <div className="flex items-center space-x-4">
          <div className="text-right">
            <div className="text-xs text-slate-500">Dubai Time</div>
            <div className="text-lg font-mono font-bold text-slate-900">{dubaiTime}</div>
            <div className={`text-xs font-semibold ${isWithinWindow ? 'text-green-600' : 'text-red-600'}`}>
              {isWithinWindow ? 'ACTIVE WINDOW' : 'INACTIVE'}
            </div>
            <div className="text-xs text-slate-500">1 PM - 1:30 AM GST</div>
            {lastDataUpdate && (
              <div className="text-xs text-slate-500 mt-1">
                Last update: {lastDataUpdate.toLocaleTimeString()}
              </div>
            )}
          </div>
          <button
            onClick={isScanning ? stopScanning : runScan}
            className={`px-4 py-2 rounded-lg font-semibold flex items-center space-x-2 ${
              isScanning
                ? 'bg-red-600 hover:bg-red-700 text-white'
                : 'bg-daman-blue-600 hover:bg-daman-blue-700 text-white'
            }`}
          >
            {isScanning ? (
              <>
                <Square className="h-4 w-4" />
                <span>Stop</span>
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                <span>Scan Now</span>
              </>
            )}
          </button>
        </div>
      </div>

      <div className="mb-6 p-4 bg-slate-50 rounded-lg">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Preset Strategy</label>
            <select
              value={preset}
              onChange={(e) => setPreset(e.target.value as any)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
            >
              <option value="balanced">Balanced</option>
              <option value="aggressive">Aggressive</option>
              <option value="aggressiveOptions">Aggressive Options</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Options DTE</label>
            <input
              type="number"
              value={settings.optionsDte}
              onChange={(e) => setSettings({ ...settings, optionsDte: parseInt(e.target.value) })}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
              min="0"
              max="2"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Min RR</label>
            <input
              type="number"
              value={settings.rrMin}
              onChange={(e) => setSettings({ ...settings, rrMin: parseFloat(e.target.value) })}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
              step="0.1"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Volume Mult</label>
            <input
              type="number"
              value={settings.volumeMult}
              onChange={(e) => setSettings({ ...settings, volumeMult: parseFloat(e.target.value) })}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
              step="0.05"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Delta Range</label>
            <div className="flex space-x-1">
              <input
                type="number"
                value={settings.deltaMin}
                onChange={(e) => setSettings({ ...settings, deltaMin: parseFloat(e.target.value) })}
                className="w-full px-2 py-2 border border-slate-300 rounded-lg text-sm"
                step="0.05"
              />
              <input
                type="number"
                value={settings.deltaMax}
                onChange={(e) => setSettings({ ...settings, deltaMax: parseFloat(e.target.value) })}
                className="w-full px-2 py-2 border border-slate-300 rounded-lg text-sm"
                step="0.05"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">RSI Long</label>
            <div className="flex space-x-1">
              <input
                type="number"
                value={settings.rsiLongMin}
                onChange={(e) => setSettings({ ...settings, rsiLongMin: parseFloat(e.target.value) })}
                className="w-full px-2 py-2 border border-slate-300 rounded-lg text-sm"
              />
              <input
                type="number"
                value={settings.rsiLongMax}
                onChange={(e) => setSettings({ ...settings, rsiLongMax: parseFloat(e.target.value) })}
                className="w-full px-2 py-2 border border-slate-300 rounded-lg text-sm"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">RSI Short</label>
            <div className="flex space-x-1">
              <input
                type="number"
                value={settings.rsiShortMin}
                onChange={(e) => setSettings({ ...settings, rsiShortMin: parseFloat(e.target.value) })}
                className="w-full px-2 py-2 border border-slate-300 rounded-lg text-sm"
              />
              <input
                type="number"
                value={settings.rsiShortMax}
                onChange={(e) => setSettings({ ...settings, rsiShortMax: parseFloat(e.target.value) })}
                className="w-full px-2 py-2 border border-slate-300 rounded-lg text-sm"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Actions</label>
            <button
              onClick={clearSignals}
              className="w-full px-3 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg text-sm font-medium"
            >
              Clear All
            </button>
          </div>
        </div>
      </div>

      {lastScanTime && (
        <div className="flex items-center justify-between mb-4 text-sm text-slate-600 bg-slate-50 rounded-lg px-4 py-2">
          <div className="flex items-center space-x-2">
            <Clock className="h-4 w-4" />
            <span>Last scan: {lastScanTime.toLocaleTimeString()}</span>
          </div>
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <Database className="h-4 w-4" />
              <span>{signals.length} total signals</span>
            </div>
            <div className="flex items-center space-x-2">
              <Zap className="h-4 w-4 text-yellow-500" />
              <span>Preset: {preset === 'balanced' ? 'Balanced' : preset === 'aggressive' ? 'Aggressive' : 'Aggressive Options'}</span>
            </div>
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="bg-slate-100 border-b border-slate-200">
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700">Time</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700">Ticker</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700">Side</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700">Strike</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700">Expiry</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700">Delta</th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700">Entry</th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700">Stop</th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700">Target</th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700">RR</th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700">RSI</th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700">IV</th>
            </tr>
          </thead>
          <tbody>
            {signals.length === 0 && (
              <tr>
                <td colSpan={12} className="px-4 py-8 text-center text-slate-500">
                  <AlertCircle className="h-8 w-8 mx-auto mb-2 text-slate-400" />
                  <p>No signals yet. Start scanning to find opportunities.</p>
                </td>
              </tr>
            )}
            {signals.map((signal, idx) => (
              <tr key={idx} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="px-4 py-3 text-xs text-slate-600">{signal.signalTime}</td>
                <td className="px-4 py-3 text-sm font-bold text-slate-900">{signal.ticker}</td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex items-center space-x-1 px-2 py-1 rounded text-xs font-bold ${
                      signal.side === 'LONG'
                        ? 'bg-green-100 text-green-800'
                        : 'bg-red-100 text-red-800'
                    }`}
                  >
                    {signal.side === 'LONG' ? (
                      <TrendingUp className="h-3 w-3" />
                    ) : (
                      <TrendingDown className="h-3 w-3" />
                    )}
                    <span>{signal.side}</span>
                  </span>
                </td>
                <td className="px-4 py-3 text-sm font-mono text-slate-900">${signal.optionsStrike}</td>
                <td className="px-4 py-3 text-xs text-slate-600">{signal.expiryDate}</td>
                <td className="px-4 py-3 text-sm font-mono text-slate-900">{signal.delta.toFixed(2)}</td>
                <td className="px-4 py-3 text-sm font-mono text-right text-slate-900">${signal.optionEntry}</td>
                <td className="px-4 py-3 text-sm font-mono text-right text-red-600">${signal.optionStop}</td>
                <td className="px-4 py-3 text-sm font-mono text-right text-green-600">${signal.optionTarget}</td>
                <td className="px-4 py-3 text-sm font-mono font-bold text-right text-daman-blue-600">
                  {signal.optionRR.toFixed(2)}
                </td>
                <td className="px-4 py-3 text-sm font-mono text-right text-slate-700">{signal.rsi.toFixed(1)}</td>
                <td className="px-4 py-3 text-sm font-mono text-right text-slate-700">{(signal.impliedVol * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
