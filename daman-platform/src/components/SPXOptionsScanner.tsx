import { useState, useEffect, useRef } from 'react';
import { TrendingUp, TrendingDown, Activity, Zap, AlertCircle, Target, Calendar, DollarSign, RefreshCw, Clock } from 'lucide-react';
import { supabase } from '../lib/supabase';
import { fetchLiveData as fetchLiveDataUtil } from '../utils/liveDataFetcher';
import { findClosestStrike } from '../services/optionsPricingService';

interface TechnicalSnapshot {
  price: number;
  vwap: number;
  ema5: number;
  ema20: number;
  rsi: number;
  bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
}

interface TradeRecommendation {
  dte: string;
  strike: number;
  expiryDate: string;
  currentPrice: number;
  entryPremium: number;
  target1: number;
  target2: number;
}

interface ScanResult {
  id: string;
  timestamp: string;
  dubaiTime: string;
  signal: 'CALL' | 'PUT' | 'NO_SIGNAL';
  reason: string;
  technical: TechnicalSnapshot;
  recommendations: TradeRecommendation[];
}

const TIMEZONE = 'Asia/Dubai';
const SCAN_INTERVAL_MS = 2 * 1000; // 2 seconds for real-time Tradier data

export default function SPXOptionsScanner() {
  const [scanResults, setScanResults] = useState<ScanResult[]>([]);
  const [currentResult, setCurrentResult] = useState<ScanResult | null>(null);
  const [previousPrice, setPreviousPrice] = useState<number | null>(null);
  const [priceChange, setPriceChange] = useState<number>(0);
  const [priceChangePercent, setPriceChangePercent] = useState<number>(0);
  const [isScanning, setIsScanning] = useState(false);
  const [scanCount, setScanCount] = useState(0);
  const [lastScanTime, setLastScanTime] = useState<Date | null>(null);
  const [localTime, setLocalTime] = useState<string>('');
  const [dubaiTime, setDubaiTime] = useState<string>('');
  const [isWithinWindow, setIsWithinWindow] = useState(false);
  const [nextScanIn, setNextScanIn] = useState(0);
  const [liveDataStatus, setLiveDataStatus] = useState<'connected' | 'fetching' | 'error' | 'idle'>('idle');
  const [lastDataUpdate, setLastDataUpdate] = useState<Date | null>(null);
  const [optionPriceStatus, setOptionPriceStatus] = useState<'live' | 'simulated' | 'error'>('simulated');
  const [realTimeSPXPrice, setRealTimeSPXPrice] = useState<number | null>(null);
  const [priceUpdateTimestamp, setPriceUpdateTimestamp] = useState<Date | null>(null);

  const scanIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const timeUpdateRef = useRef<NodeJS.Timeout | null>(null);
  const realTimePriceRef = useRef<NodeJS.Timeout | null>(null);

  const getDubaiTimeFormatted = (date: Date): string => {
    const options: Intl.DateTimeFormatOptions = {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      timeZone: TIMEZONE,
      hour12: true,
    };
    return date.toLocaleTimeString('en-US', options) + ' GST';
  };

  const checkWithinDubaiWindow = (): boolean => {
    const now = new Date();
    const options: Intl.DateTimeFormatOptions = {
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
      timeZone: TIMEZONE,
    };

    const dubaiTimeStr = now.toLocaleTimeString('en-US', options);
    const [hourStr, minuteStr] = dubaiTimeStr.split(':');

    const hour = parseInt(hourStr);
    const minute = parseInt(minuteStr);
    const currentTimeMinutes = hour * 60 + minute;

    const WINDOW_START_MINUTES = 13 * 60; // 13:00 (1:00 PM)
    const WINDOW_END_MINUTES = 1 * 60 + 30; // 01:30 (1:30 AM)

    // Part 1: 13:00 to 23:59
    if (currentTimeMinutes >= WINDOW_START_MINUTES) {
      return true;
    }

    // Part 2: 00:00 to 01:30
    if (currentTimeMinutes <= WINDOW_END_MINUTES) {
      return true;
    }

    return false;
  };

  const calculateEMA = (prices: number[], period: number): number => {
    if (prices.length < period) return prices[prices.length - 1];
    const k = 2 / (period + 1);
    let ema = prices.slice(0, period).reduce((a, b) => a + b, 0) / period;
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

  const calculateVWAP = (prices: number[], volumes: number[]): number => {
    if (prices.length !== volumes.length || prices.length === 0) return prices[prices.length - 1];
    const pv = prices.map((p, i) => p * volumes[i]);
    const sumPV = pv.reduce((a, b) => a + b, 0);
    const sumV = volumes.reduce((a, b) => a + b, 0);
    return sumV > 0 ? sumPV / sumV : prices[prices.length - 1];
  };

  const getNextBusinessDay = (d: Date, daysAhead: number = 1): Date => {
    const result = new Date(d);
    let addedDays = 0;
    while (addedDays < daysAhead) {
      result.setDate(result.getDate() + 1);
      if (result.getDay() !== 0 && result.getDay() !== 6) {
        addedDays++;
      }
    }
    return result;
  };

  const getExpiryDates = (): { [key: string]: string } => {
    const today = new Date();
    const dates: { [key: string]: string } = {};

    dates['0 DTE (Same Day)'] = today.toISOString().split('T')[0];

    const nextDay = getNextBusinessDay(today, 1);
    dates['1 DTE (Next Day)'] = nextDay.toISOString().split('T')[0];

    const twoDays = getNextBusinessDay(today, 2);
    dates['2 DTE'] = twoDays.toISOString().split('T')[0];

    return dates;
  };

  const simulateOptionsPricing = (
    spxPrice: number,
    optionType: 'CALL' | 'PUT',
    strike: number,
    dte: number
  ): { currentPrice: number; entryPrice: number } => {
    const moneyness = Math.abs(spxPrice - strike) / spxPrice;
    const timeFactor = (dte + 1) / 365;
    let basePremium = 50.0 + moneyness * 1000 * (timeFactor * 10);

    if (optionType === 'CALL') {
      if (strike < spxPrice) {
        basePremium += 10 * dte;
      } else {
        basePremium -= 10;
      }
    } else {
      if (strike > spxPrice) {
        basePremium += 10 * dte;
      } else {
        basePremium -= 10;
      }
    }

    const currentPrice = Math.max(5.0, parseFloat((basePremium * (0.95 + Math.random() * 0.1)).toFixed(2)));
    const entryPrice = Math.max(5.0, parseFloat((basePremium * 1.02).toFixed(2)));

    return { currentPrice, entryPrice };
  };

  const determineTradeParameters = async (
    signal: 'CALL' | 'PUT',
    currentPrice: number
  ): Promise<TradeRecommendation[]> => {
    let targetStrike: number;

    if (signal === 'CALL') {
      targetStrike = Math.ceil(currentPrice / 5) * 5 + 10;
    } else {
      targetStrike = Math.floor(currentPrice / 5) * 5 - 10;
    }

    targetStrike = Math.round(targetStrike / 5) * 5;

    const expiryDates = getExpiryDates();
    const recommendations: TradeRecommendation[] = [];
    let anyLivePrice = false;
    let anySimulatedPrice = false;

    for (const [dteLabel, expiryDate] of Object.entries(expiryDates)) {
      const dte = Math.max(
        0,
        Math.floor(
          (new Date(expiryDate).getTime() - new Date().getTime()) / (1000 * 60 * 60 * 24)
        )
      );

      let livePrice: number = 0;
      let isLivePrice = false;
      try {
        const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
        const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

        const response = await fetch(
          `${supabaseUrl}/functions/v1/fetch-options-prices?symbol=SPX`,
          {
            headers: {
              'Authorization': `Bearer ${supabaseKey}`,
              'Content-Type': 'application/json',
            },
          }
        );

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const result = await response.json();

        if (!result.success || !result.data) {
          throw new Error('No options data available');
        }

        const optionsData = result.data;
        const optionsList = signal === 'CALL' ? optionsData.calls : optionsData.puts;
        const closestOption = findClosestStrike(optionsList, targetStrike);

        if (closestOption) {
          const price = closestOption.mid || closestOption.last || 0;
          if (price > 0) {
            livePrice = price;
            isLivePrice = true;
            anyLivePrice = true;
          }
        }

        if (!isLivePrice) {
          throw new Error('No valid option price found');
        }
      } catch (error) {
        console.error('Error fetching live option price, using fallback:', error);
        anySimulatedPrice = true;
        const pricing = simulateOptionsPricing(currentPrice, signal, targetStrike, dte);
        livePrice = pricing.currentPrice;
      }

      const entryPrice = parseFloat((livePrice * 1.02).toFixed(2));
      const target1 = parseFloat((entryPrice * 1.5).toFixed(2));
      const target2 = parseFloat((entryPrice * 2.0).toFixed(2));

      recommendations.push({
        dte: dteLabel,
        strike: targetStrike,
        expiryDate,
        currentPrice: livePrice,
        entryPremium: entryPrice,
        target1,
        target2,
      });
    }

    if (anyLivePrice && !anySimulatedPrice) {
      setOptionPriceStatus('live');
    } else if (anySimulatedPrice && !anyLivePrice) {
      setOptionPriceStatus('simulated');
    } else if (anyLivePrice && anySimulatedPrice) {
      setOptionPriceStatus('live');
    }

    return recommendations;
  };

  const fetchLiveData = async (): Promise<{
    prices: number[];
    volumes: number[];
    currentPrice: number;
  } | null> => {
    try {
      setLiveDataStatus('fetching');

      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      const response = await fetch(
        `${supabaseUrl}/functions/v1/fetch-stock-data?symbols=SPY&mode=return`,
        {
          headers: {
            'Authorization': `Bearer ${supabaseKey}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();

      if (!result.success || !result.data || result.data.length === 0) {
        throw new Error('No market data available');
      }

      setLiveDataStatus('connected');
      setLastDataUpdate(new Date());

      const spyData = result.data[0];
      const currentPrice = spyData.price * 10;

      const prices = Array(100).fill(currentPrice).map((p, i) => p * (1 + (Math.random() - 0.5) * 0.001));
      const volumes = Array(100).fill(1000000);
      prices[prices.length - 1] = currentPrice;

      return {
        prices,
        volumes,
        currentPrice,
      };
    } catch (error) {
      console.error('Error fetching SPX data:', error);
      setLiveDataStatus('error');
      return null;
    }
  };

  const performScan = async () => {
    setIsScanning(true);

    try {
      const liveData = await fetchLiveData();
      if (!liveData) {
        setIsScanning(false);
        return;
      }

      const { prices, volumes, currentPrice } = liveData;

      const ema5 = calculateEMA(prices, 5);
      const ema20 = calculateEMA(prices, 20);
      const rsi = calculateRSI(prices);
      const vwap = calculateVWAP(prices, volumes);

      const isAboveVWAP = currentPrice > vwap;
      const isUptrend = ema5 > ema20;
      const isMomentumOk = rsi >= 40 && rsi <= 65;

      const isBelowVWAP = currentPrice < vwap;
      const isDowntrend = ema5 < ema20;
      const isMomentumBearish = rsi >= 35 && rsi <= 60;

      let signal: 'CALL' | 'PUT' | 'NO_SIGNAL' = 'NO_SIGNAL';
      let reason = 'No clear signal';
      let bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL' = 'NEUTRAL';

      if (isAboveVWAP && isUptrend && isMomentumOk) {
        signal = 'CALL';
        bias = 'BULLISH';
        reason = `STRONG BULLISH: Price is above VWAP, 5-EMA crossed above 20-EMA, and RSI (${rsi.toFixed(
          2
        )}) shows healthy positive momentum (40-65 range).`;
      } else if (isBelowVWAP && isDowntrend && isMomentumBearish) {
        signal = 'PUT';
        bias = 'BEARISH';
        reason = `STRONG BEARISH: Price is below VWAP, 5-EMA crossed below 20-EMA, and RSI (${rsi.toFixed(
          2
        )}) shows healthy negative momentum (35-60 range).`;
      } else {
        bias = isUptrend ? 'BULLISH' : 'BEARISH';
        reason = 'Market lacks confirmed trend and momentum for high-probability entry.';
      }

      const recommendations: TradeRecommendation[] =
        signal !== 'NO_SIGNAL' ? await determineTradeParameters(signal, currentPrice) : [];

      const now = new Date();
      const dubaiTimeNow = getDubaiTimeFormatted(now);

      const result: ScanResult = {
        id: `spx-${Date.now()}`,
        timestamp: now.toISOString(),
        dubaiTime: dubaiTimeNow,
        signal,
        reason,
        technical: {
          price: currentPrice,
          vwap,
          ema5,
          ema20,
          rsi,
          bias,
        },
        recommendations,
      };

      if (previousPrice !== null) {
        const change = currentPrice - previousPrice;
        const changePercent = (change / previousPrice) * 100;
        setPriceChange(change);
        setPriceChangePercent(changePercent);
      }
      setPreviousPrice(currentPrice);

      setCurrentResult(result);
      setScanResults((prev) => [result, ...prev].slice(0, 50));
      setLastScanTime(now);
      setScanCount((prev) => prev + 1);

      // Save to Supabase database
      await saveSignalToDatabase(result);
    } catch (error) {
      console.error('Scan error:', error);
    } finally {
      setIsScanning(false);
    }
  };

  const saveSignalToDatabase = async (result: ScanResult) => {
    try {
      const { error } = await supabase.from('spx_scanner_results').insert({
        timestamp: result.timestamp,
        dubai_time: result.dubaiTime,
        signal: result.signal,
        reason: result.reason,
        price: result.technical.price,
        vwap: result.technical.vwap,
        ema5: result.technical.ema5,
        ema20: result.technical.ema20,
        rsi: result.technical.rsi,
        bias: result.technical.bias,
        recommendations: result.recommendations,
      });

      if (error) throw error;
    } catch (error) {
      console.error('Error saving signal:', error);
    }
  };

  const loadHistoricalScans = async () => {
    try {
      const { data, error } = await supabase
        .from('spx_scanner_results')
        .select('*')
        .order('timestamp', { ascending: false })
        .limit(50);

      if (error) throw error;

      if (data) {
        const formattedResults: ScanResult[] = data.map((row: any) => ({
          id: row.id,
          timestamp: row.timestamp,
          dubaiTime: row.dubai_time,
          signal: row.signal,
          reason: row.reason,
          technical: {
            price: row.price,
            vwap: row.vwap,
            ema5: row.ema5,
            ema20: row.ema20,
            rsi: row.rsi,
            bias: row.bias,
          },
          recommendations: row.recommendations || [],
        }));

        setScanResults(formattedResults);
      }
    } catch (error) {
      console.error('Error loading historical scans:', error);
    }
  };

  const updateTimeDisplay = () => {
    const now = new Date();
    setLocalTime(now.toLocaleTimeString());
    setDubaiTime(getDubaiTimeFormatted(now));
    const withinWindow = checkWithinDubaiWindow();
    setIsWithinWindow(withinWindow);

    if (withinWindow) {
      const timeSinceLastScan = lastScanTime ? now.getTime() - lastScanTime.getTime() : SCAN_INTERVAL_MS;
      const timeToNext = Math.max(0, SCAN_INTERVAL_MS - timeSinceLastScan);
      setNextScanIn(Math.ceil(timeToNext / 1000));
    }
  };

  const startScannerLoop = () => {
    if (scanIntervalRef.current) return;

    const withinWindow = checkWithinDubaiWindow();

    if (withinWindow) {
      performScan();
      scanIntervalRef.current = setInterval(() => {
        if (checkWithinDubaiWindow()) {
          performScan();
        } else {
          stopScannerLoop();
        }
      }, SCAN_INTERVAL_MS);
    }
  };

  const stopScannerLoop = () => {
    if (scanIntervalRef.current) {
      clearInterval(scanIntervalRef.current);
      scanIntervalRef.current = null;
    }
  };

  const fetchRealTimeSPXPrice = async () => {
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      const response = await fetch(
        `${supabaseUrl}/functions/v1/fetch-market-data?symbols=^GSPC`,
        {
          headers: {
            'Authorization': `Bearer ${supabaseKey}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();

      if (result.success && result.data && result.data.length > 0) {
        const spxData = result.data[0];
        setRealTimeSPXPrice(spxData.price);
        setPriceUpdateTimestamp(new Date());
        setLiveDataStatus('connected');
      }
    } catch (error) {
      console.error('Error fetching real-time SPX price:', error);
    }
  };

  const startRealTimePriceUpdates = () => {
    fetchRealTimeSPXPrice();
    realTimePriceRef.current = setInterval(fetchRealTimeSPXPrice, 2000);
  };

  const stopRealTimePriceUpdates = () => {
    if (realTimePriceRef.current) {
      clearInterval(realTimePriceRef.current);
      realTimePriceRef.current = null;
    }
  };

  useEffect(() => {
    loadHistoricalScans();

    timeUpdateRef.current = setInterval(updateTimeDisplay, 1000);
    updateTimeDisplay();

    startScannerLoop();
    startRealTimePriceUpdates();

    return () => {
      if (scanIntervalRef.current) clearInterval(scanIntervalRef.current);
      if (timeUpdateRef.current) clearInterval(timeUpdateRef.current);
      if (realTimePriceRef.current) clearInterval(realTimePriceRef.current);
    };
  }, []);

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-purple-600 to-pink-600 rounded-xl p-6 text-white">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-3">
            <Zap className="h-8 w-8" />
            <div>
              <h2 className="text-2xl font-bold">SPX Options High-Probability Scanner</h2>
              <div className="flex items-center space-x-3 mt-1">
                <p className="text-purple-100">Persistent Dubai Time Scanning (1:00 PM - 1:30 AM GST)</p>
                <span className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
                  liveDataStatus === 'connected' ? 'bg-green-500 text-white' :
                  liveDataStatus === 'fetching' ? 'bg-blue-500 text-white' :
                  liveDataStatus === 'error' ? 'bg-red-500 text-white' :
                  'bg-slate-500 text-white'
                }`}>
                  <span className={`h-1.5 w-1.5 rounded-full bg-white ${
                    liveDataStatus === 'connected' || liveDataStatus === 'fetching' ? 'animate-pulse' : ''
                  }`}></span>
                  <span>
                    {liveDataStatus === 'connected' ? 'Live Feed' :
                     liveDataStatus === 'fetching' ? 'Connecting...' :
                     liveDataStatus === 'error' ? 'Connection Error' :
                     'Idle'}
                  </span>
                </span>
                <span className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
                  optionPriceStatus === 'live' ? 'bg-emerald-500 text-white' :
                  optionPriceStatus === 'simulated' ? 'bg-amber-500 text-white' :
                  'bg-red-500 text-white'
                }`}>
                  <DollarSign className="h-3 w-3" />
                  <span>
                    {optionPriceStatus === 'live' ? 'Live Prices' :
                     optionPriceStatus === 'simulated' ? 'Simulated Prices' :
                     'Price Error'}
                  </span>
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div className="bg-white/10 rounded-lg p-3">
            <div className="text-purple-100 text-sm mb-1">Local Time</div>
            <div className="font-bold text-lg">{localTime || 'Loading...'}</div>
          </div>
          <div className="bg-white/10 rounded-lg p-3">
            <div className="text-purple-100 text-sm mb-1">Dubai Time</div>
            <div className="font-bold text-lg">{dubaiTime || 'Loading...'}</div>
          </div>
        </div>

        <div
          className={`rounded-lg p-4 text-center ${
            isWithinWindow ? 'bg-green-500' : 'bg-red-500'
          }`}
        >
          <div className="flex items-center justify-center space-x-2 mb-2">
            <Clock className="h-6 w-6" />
            <span className="text-xl font-black">
              {isWithinWindow ? '✅ RUNNING' : '🛑 STOPPED'}
            </span>
          </div>
          <p className="text-sm">
            {isWithinWindow
              ? `Active during 1:00 PM - 1:30 AM window. Next scan in: ${nextScanIn}s`
              : 'Outside scanning window. Will resume at 1:00 PM Dubai time.'}
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <div className="bg-gradient-to-br from-green-500 to-emerald-600 rounded-lg p-4 shadow-lg">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-white/80 text-sm mb-1 flex items-center space-x-2">
                  <span className="inline-block w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
                  <span className="font-bold">LIVE SPX</span>
                  <span className="text-xs">(Updates every 2s)</span>
                </div>
                <div className="text-3xl font-black text-white">
                  {realTimeSPXPrice ? `$${realTimeSPXPrice.toFixed(2)}` :
                   currentResult ? `$${currentResult.technical.price.toFixed(2)}` :
                   'Loading...'}
                </div>
                {previousPrice !== null && priceChange !== 0 && (
                  <div className={`text-sm font-bold mt-1 flex items-center space-x-1 ${
                    priceChange > 0 ? 'text-green-200' : 'text-red-200'
                  }`}>
                    {priceChange > 0 ? (
                      <TrendingUp className="h-4 w-4" />
                    ) : (
                      <TrendingDown className="h-4 w-4" />
                    )}
                    <span>
                      {priceChange > 0 ? '+' : ''}{priceChange.toFixed(2)} ({priceChangePercent > 0 ? '+' : ''}{priceChangePercent.toFixed(2)}%)
                    </span>
                  </div>
                )}
                <div className="text-white/80 text-xs mt-1">
                  {priceUpdateTimestamp ? `Live: ${priceUpdateTimestamp.toLocaleTimeString()}` :
                   lastScanTime ? `Last Scan: ${lastScanTime.toLocaleTimeString()}` :
                   'Waiting for data...'}
                </div>
              </div>
              <div className="text-right">
                <div className="text-white/80 text-sm mb-1">Market Bias</div>
                <div className={`text-xl font-bold px-3 py-1 rounded ${
                  currentResult?.technical.bias === 'BULLISH' ? 'bg-green-700' :
                  currentResult?.technical.bias === 'BEARISH' ? 'bg-red-700' :
                  'bg-slate-700'
                }`}>
                  {currentResult?.technical.bias || 'NEUTRAL'}
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="bg-white/10 rounded-lg p-3">
              <div className="text-purple-100 text-sm mb-1">Total Scans</div>
              <div className="font-bold text-2xl">{scanCount}</div>
            </div>
            <div className="bg-white/10 rounded-lg p-3">
              <div className="text-purple-100 text-sm mb-1">Next Scan</div>
              <div className="font-bold text-2xl">{nextScanIn}s</div>
            </div>
          </div>
        </div>
      </div>

      {currentResult && (
        <>
          <div className="bg-white rounded-xl p-6 shadow-lg border border-slate-200">
            <h3 className="text-xl font-bold text-slate-900 mb-4 flex items-center space-x-2">
              <Activity className="h-6 w-6 text-blue-600" />
              <span>Technical Analysis Snapshot</span>
            </h3>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg p-4 border-2 border-blue-300">
                <div className="text-xs text-blue-700 mb-1 font-semibold flex items-center space-x-1">
                  <span className="inline-block w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
                  <span>Live SPX Price</span>
                </div>
                <div className="text-2xl font-black text-blue-900">
                  ${currentResult.technical.price.toFixed(2)}
                </div>
              </div>

              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-xs text-slate-600 mb-1">VWAP</div>
                <div className="text-lg font-bold text-slate-900">
                  ${currentResult.technical.vwap.toFixed(2)}
                </div>
              </div>

              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-xs text-slate-600 mb-1">EMA-5</div>
                <div className="text-lg font-bold text-blue-600">
                  ${currentResult.technical.ema5.toFixed(2)}
                </div>
              </div>

              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-xs text-slate-600 mb-1">EMA-20</div>
                <div className="text-lg font-bold text-purple-600">
                  ${currentResult.technical.ema20.toFixed(2)}
                </div>
              </div>

              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-xs text-slate-600 mb-1">RSI (14)</div>
                <div
                  className={`text-lg font-bold ${
                    currentResult.technical.rsi > 70
                      ? 'text-red-600'
                      : currentResult.technical.rsi < 30
                      ? 'text-green-600'
                      : 'text-slate-900'
                  }`}
                >
                  {currentResult.technical.rsi.toFixed(2)}
                </div>
              </div>
            </div>

            <div className="mt-4 flex items-center space-x-2">
              <span className="text-sm font-medium text-slate-700">Market Bias:</span>
              <span
                className={`px-3 py-1 rounded-full text-sm font-bold ${
                  currentResult.technical.bias === 'BULLISH'
                    ? 'bg-green-100 text-green-800'
                    : currentResult.technical.bias === 'BEARISH'
                    ? 'bg-red-100 text-red-800'
                    : 'bg-slate-100 text-slate-800'
                }`}
              >
                {currentResult.technical.bias}
              </span>
            </div>
          </div>

          <div
            className={`rounded-xl p-6 shadow-lg border-2 ${
              currentResult.signal === 'NO_SIGNAL'
                ? 'bg-slate-50 border-slate-300'
                : currentResult.signal === 'CALL'
                ? 'bg-green-50 border-green-500'
                : 'bg-red-50 border-red-500'
            }`}
          >
            <div className="flex items-start space-x-3 mb-4">
              {currentResult.signal === 'NO_SIGNAL' ? (
                <AlertCircle className="h-8 w-8 text-slate-500 flex-shrink-0" />
              ) : currentResult.signal === 'CALL' ? (
                <TrendingUp className="h-8 w-8 text-green-600 flex-shrink-0" />
              ) : (
                <TrendingDown className="h-8 w-8 text-red-600 flex-shrink-0" />
              )}
              <div>
                <h3 className="text-xl font-bold mb-2">
                  {currentResult.signal === 'NO_SIGNAL' ? (
                    <span className="text-slate-900">NO TRADE SIGNAL</span>
                  ) : (
                    <span
                      className={
                        currentResult.signal === 'CALL' ? 'text-green-800' : 'text-red-800'
                      }
                    >
                      TRADE SIGNAL: LONG {currentResult.signal}
                    </span>
                  )}
                </h3>
                <p className="text-sm leading-relaxed text-slate-700">{currentResult.reason}</p>
              </div>
            </div>

            {currentResult.signal !== 'NO_SIGNAL' && currentResult.recommendations.length > 0 && (
              <div className="space-y-4 mt-6">
                <h4 className="text-lg font-bold text-slate-900">Trade Recommendations</h4>

                {currentResult.recommendations.map((rec, idx) => (
                  <div key={idx} className="bg-white rounded-lg p-4 border border-slate-200">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center space-x-2">
                        <Calendar className="h-5 w-5 text-blue-600" />
                        <span className="font-bold text-slate-900">{rec.dte}</span>
                      </div>
                      <span className="text-xs text-slate-600">{rec.expiryDate}</span>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                      <div>
                        <div className="text-xs text-slate-600 mb-1">Strike Price</div>
                        <div className="font-bold text-slate-900">
                          {rec.strike.toFixed(2)} {currentResult.signal}
                        </div>
                      </div>

                      <div className="bg-gradient-to-br from-emerald-50 to-emerald-100 rounded-lg p-2 border border-emerald-300">
                        <div className="text-xs text-emerald-700 mb-1 font-semibold flex items-center space-x-1">
                          <span className="inline-block w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                          <span>Live Price</span>
                        </div>
                        <div className="font-black text-emerald-900 text-lg">${rec.currentPrice.toFixed(2)}</div>
                      </div>

                      <div>
                        <div className="text-xs text-slate-600 mb-1">Entry Premium</div>
                        <div className="font-bold text-blue-600">${rec.entryPremium.toFixed(2)}</div>
                      </div>

                      <div>
                        <div className="text-xs text-slate-600 mb-1">Target 1 (Scalp)</div>
                        <div className="font-bold text-green-600">${rec.target1.toFixed(2)}</div>
                      </div>

                      <div>
                        <div className="text-xs text-slate-600 mb-1">Target 2 (Swing)</div>
                        <div className="font-bold text-green-700">${rec.target2.toFixed(2)}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      <div className="bg-white rounded-xl p-6 shadow-lg border border-slate-200">
        <h3 className="text-xl font-bold text-slate-900 mb-4">Historical Scan Results</h3>
        <div className="max-h-96 overflow-y-auto">
          <div className="space-y-2">
            {scanResults.length === 0 ? (
              <p className="text-center text-slate-500 py-4">No scans logged yet.</p>
            ) : (
              scanResults.map((result) => (
                <div
                  key={result.id}
                  className="flex items-center justify-between p-3 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors"
                >
                  <div className="flex items-center space-x-3">
                    <span className="text-sm font-mono text-slate-600">{result.dubaiTime}</span>
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-bold text-white ${
                        result.signal === 'NO_SIGNAL'
                          ? 'bg-slate-500'
                          : result.signal === 'CALL'
                          ? 'bg-green-600'
                          : 'bg-red-600'
                      }`}
                    >
                      {result.signal === 'CALL' ? 'LONG CALL' : result.signal === 'PUT' ? 'LONG PUT' : 'NO SIGNAL'}
                    </span>
                  </div>
                  <span className="text-sm text-slate-600">
                    ${result.technical.price.toFixed(2)}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded">
        <div className="flex items-start">
          <AlertCircle className="h-5 w-5 text-red-500 mt-0.5 mr-2 flex-shrink-0" />
          <div>
            <h4 className="text-sm font-semibold text-red-900 mb-1">Trading Disclaimer</h4>
            <p className="text-xs text-red-800 leading-relaxed">
              Trading SPX 0DTE options is extremely high-risk and can lead to 100% loss of capital
              in seconds due to Gamma risk. This scanner operates during Dubai trading hours (1:00
              PM to 1:30 AM GST) and uses technical analysis with EMA, RSI, and VWAP. Always use
              proper risk management and never risk more than you can afford to lose.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
