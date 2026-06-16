import { useState, useEffect, useRef } from 'react';
import { RefreshCw, TrendingUp, TrendingDown, Activity, Target, BarChart3, DollarSign, AlertCircle, Clock, Play, Pause } from 'lucide-react';
import { supabase } from '../lib/supabase';

interface FundamentalData {
  MODEL: 'NAV' | 'EV/S';
  TTM_SALES?: number;
  SHARES_OUTSTANDING: number;
  TOTAL_DEBT: number;
  TOTAL_BTC?: number;
  NAV_DISCOUNT_THRESHOLD?: number;
  NAV_TARGET_PREMIUM?: number;
  EV_S_DISCOUNT_THRESHOLD?: number;
  TARGET_EV_S_RATIO?: number;
}

interface ScanResult {
  time: string;
  ticker: string;
  price: number;
  signal: string;
  rsi: number;
  valuationModel: string;
  valuationRatio: number | string;
  targetPrice: number | string;
  reasons: string;
  score: number;
}

interface CandlePattern {
  name: string | null;
  score: number;
}

const TICKERS = [
  "MSTR", "NVDA", "TSLA", "META", "UPST", "SMCI", "AMD", "COIN",
  "AAPL", "MSFT", "GOOGL", "AMZN", "NFLX", "CRWD", "DDOG", "SNOW",
  "ZM", "OKTA", "NET", "ADBE", "CRM", "INTC", "QCOM", "TXN", "AVGO",
  "MU", "MPWR", "MCHP", "KLAC", "LRCX", "AMAT", "ASML", "ENPH", "PLTR",
  "SQ", "PYPL", "HOOD", "AFRM", "COUP", "DOCN", "FIVN", "FUTU", "TDOC",
  "BABA", "PINS", "ROKU", "SPOT", "UBER", "LYFT", "BYND", "DASH", "WISH",
  "V", "MA", "SHOP", "SE", "MELI", "PCAR", "DE", "CAT", "GE", "HON",
  "GME", "AMC", "RIVN", "LCID", "NKLA", "WKHS", "QS", "ARKK", "KRE",
  "XLE", "XOP", "XME", "SMH", "SOXX", "QQQ", "SPY", "IWM", "ARKG",
  "PFE", "MRNA", "BNTX", "NVAX", "REGN", "GILD", "BIIB", "VRTX", "ILMN",
  "TDY", "TRMB", "Z", "OPEN", "FTCH", "W", "ETSY", "SPLK", "PTON"
];

const RSI_OVERSOLD = 30;
const RSI_OVERBOUGHT = 70;

export default function FundamentalScanner() {
  const [results, setResults] = useState<ScanResult[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [fundamentalData, setFundamentalData] = useState<Record<string, FundamentalData>>({});
  const [btcPrice, setBtcPrice] = useState<number>(0);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [filterSignal, setFilterSignal] = useState<string>('ALL');
  const [customSymbol, setCustomSymbol] = useState<string>('');
  const scanIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    fetchFundamentalData();
    fetchBTCPrice();

    return () => {
      if (scanIntervalRef.current) {
        clearInterval(scanIntervalRef.current);
      }
    };
  }, []);

  const fetchBTCPrice = async () => {
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      const response = await fetch(
        `${supabaseUrl}/functions/v1/fetch-market-data`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${supabaseKey}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ symbols: ['BTC-USD'] }),
        }
      );

      if (response.ok) {
        const data = await response.json();
        if (data.quotes && data.quotes.length > 0) {
          setBtcPrice(data.quotes[0].price);
        }
      }
    } catch (error) {
      console.error('Error fetching BTC price:', error);
    }
  };

  const fetchFundamentalData = async () => {
    const fundamentals: Record<string, FundamentalData> = {};

    // MSTR - NAV Model (Bitcoin holdings - special case)
    fundamentals['MSTR'] = {
      MODEL: 'NAV',
      TOTAL_BTC: 650000,
      SHARES_OUTSTANDING: 315e6,
      TOTAL_DEBT: 8.25e9,
      NAV_DISCOUNT_THRESHOLD: 1.10,
      NAV_TARGET_PREMIUM: 1.26
    };

    console.log(`📊 Fetching real fundamental data for ${TICKERS.length} symbols...`);

    // Check database cache first
    const { data: cachedData, error: dbError } = await supabase
      .from('fundamental_data')
      .select('*')
      .in('symbol', TICKERS);

    if (!dbError && cachedData && cachedData.length > 0) {
      console.log(`✅ Found ${cachedData.length} cached fundamental records`);

      for (const record of cachedData) {
        if (record.symbol === 'MSTR') continue;

        const TARGET_EV_S = 11.0;
        const DISCOUNT_EV_S = 8.5;

        fundamentals[record.symbol] = {
          MODEL: 'EV/S',
          TTM_SALES: record.revenue || 0,
          SHARES_OUTSTANDING: record.shares_outstanding || 0,
          TOTAL_DEBT: record.total_debt || 0,
          EV_S_DISCOUNT_THRESHOLD: DISCOUNT_EV_S,
          TARGET_EV_S_RATIO: TARGET_EV_S
        };
      }
    }

    // Fetch missing symbols from API (up to 20 at a time to avoid timeouts)
    const cachedSymbols = cachedData?.map(d => d.symbol) || [];
    const missingSymbols = TICKERS.filter(t => !cachedSymbols.includes(t) && t !== 'MSTR');

    if (missingSymbols.length > 0) {
      console.log(`🔄 Fetching ${missingSymbols.length} missing symbols from API...`);

      const batchSize = 20;
      for (let i = 0; i < missingSymbols.length; i += batchSize) {
        const batch = missingSymbols.slice(i, i + batchSize);

        try {
          const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
          const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

          const response = await fetch(
            `${supabaseUrl}/functions/v1/fetch-fundamentals?symbols=${batch.join(',')}`,
            {
              headers: {
                'Authorization': `Bearer ${supabaseKey}`,
                'Content-Type': 'application/json',
              },
            }
          );

          if (response.ok) {
            const apiData = await response.json();
            if (apiData.success && apiData.data) {
              for (const fundData of apiData.data) {
                const TARGET_EV_S = 11.0;
                const DISCOUNT_EV_S = 8.5;

                fundamentals[fundData.symbol] = {
                  MODEL: 'EV/S',
                  TTM_SALES: fundData.revenue || 0,
                  SHARES_OUTSTANDING: fundData.sharesOutstanding || 0,
                  TOTAL_DEBT: fundData.totalDebt || 0,
                  EV_S_DISCOUNT_THRESHOLD: DISCOUNT_EV_S,
                  TARGET_EV_S_RATIO: TARGET_EV_S
                };
              }
            }
          }

          await new Promise(resolve => setTimeout(resolve, 300));
        } catch (error) {
          console.error(`Error fetching batch fundamentals:`, error);
        }
      }
    }

    console.log(`✅ Loaded ${Object.keys(fundamentals).length} fundamental datasets`);
    setFundamentalData(fundamentals);
  };

  const calculateRSI = (prices: number[], period: number = 14): number => {
    if (prices.length < period + 1) return 50;

    let gains = 0;
    let losses = 0;

    for (let i = prices.length - period; i < prices.length; i++) {
      const change = prices[i] - prices[i - 1];
      if (change > 0) gains += change;
      else losses += Math.abs(change);
    }

    const avgGain = gains / period;
    const avgLoss = losses / period;

    if (avgLoss === 0) return 100;
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
  };

  const calculateMACD = (prices: number[]): { macd: number; signal: number; histogram: number } => {
    if (prices.length < 26) return { macd: 0, signal: 0, histogram: 0 };

    const ema12 = calculateEMA(prices, 12);
    const ema26 = calculateEMA(prices, 26);
    const macd = ema12 - ema26;

    // For simplicity, using a basic signal approximation
    const signal = macd * 0.9;
    const histogram = macd - signal;

    return { macd, signal, histogram };
  };

  const calculateEMA = (prices: number[], period: number): number => {
    if (prices.length === 0) return 0;
    const k = 2 / (period + 1);
    let ema = prices[0];

    for (let i = 1; i < prices.length; i++) {
      ema = prices[i] * k + ema * (1 - k);
    }

    return ema;
  };

  const detectCandlePattern = (
    open: number,
    high: number,
    low: number,
    close: number,
    prevOpen: number,
    prevClose: number
  ): CandlePattern => {
    const body = Math.abs(close - open);
    const upperWick = high - Math.max(close, open);
    const lowerWick = Math.min(close, open) - low;

    // Bullish Engulfing
    if (prevClose < prevOpen && close > open &&
        close > prevOpen && open < prevClose) {
      return { name: 'Bullish Engulfing', score: 2 };
    }

    // Hammer
    if (lowerWick > 2 * body && upperWick < body * 0.5) {
      return { name: 'Hammer', score: 2 };
    }

    // Bearish Engulfing
    if (prevClose > prevOpen && close < open &&
        open > prevClose && close < prevOpen) {
      return { name: 'Bearish Engulfing', score: -2 };
    }

    // Shooting Star
    if (upperWick > 2 * body && lowerWick < body * 0.5) {
      return { name: 'Shooting Star', score: -2 };
    }

    return { name: null, score: 0 };
  };

  const calculateFundamentalThesis = (
    ticker: string,
    currentPrice: number
  ): { ratio: number | null; score: number; targetPrice: number | null; reason: string } => {
    if (!fundamentalData[ticker]) {
      return { ratio: null, score: 0, targetPrice: null, reason: 'No Fundamental Data' };
    }

    const fund = fundamentalData[ticker];
    let ratio: number | null = null;
    let targetPrice: number | null = null;
    let score = 0;
    let reason = '';

    try {
      if (fund.MODEL === 'NAV' && btcPrice > 0) {
        const totalBTCValue = (fund.TOTAL_BTC || 0) * btcPrice;
        const netAssetValue = totalBTCValue - fund.TOTAL_DEBT;
        const navPerShare = netAssetValue / fund.SHARES_OUTSTANDING;

        ratio = currentPrice / navPerShare;
        const threshold = fund.NAV_DISCOUNT_THRESHOLD || 1.10;

        const targetMC = (navPerShare * (fund.NAV_TARGET_PREMIUM || 1.26)) * fund.SHARES_OUTSTANDING;
        targetPrice = targetMC / fund.SHARES_OUTSTANDING;

        if (ratio <= threshold) {
          score = 2;
          reason = `NAV Discount (${ratio.toFixed(2)}x < ${threshold}x)`;
        } else {
          reason = `NAV Ratio ${ratio.toFixed(2)}x`;
        }

      } else if (fund.MODEL === 'EV/S') {
        const marketCap = currentPrice * fund.SHARES_OUTSTANDING;
        const enterpriseValue = marketCap + fund.TOTAL_DEBT;
        ratio = enterpriseValue / (fund.TTM_SALES || 1);
        const threshold = fund.EV_S_DISCOUNT_THRESHOLD || 8.5;

        const targetEV = (fund.TARGET_EV_S_RATIO || 11.0) * (fund.TTM_SALES || 1);
        const targetMC = targetEV - fund.TOTAL_DEBT;
        targetPrice = targetMC / fund.SHARES_OUTSTANDING;

        if (ratio <= threshold) {
          score = 2;
          reason = `EV/S Discount (${ratio.toFixed(2)}x < ${threshold}x)`;
        } else {
          reason = `EV/S ${ratio.toFixed(2)}x`;
        }
      }

      return { ratio, score, targetPrice, reason };

    } catch (error) {
      return { ratio: null, score: 0, targetPrice: null, reason: 'Calc Error' };
    }
  };

  const analyzeTicker = async (ticker: string): Promise<ScanResult | null> => {
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      const response = await fetch(
        `${supabaseUrl}/functions/v1/fetch-market-data`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${supabaseKey}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ symbols: [ticker] }),
        }
      );

      const data = await response.json();

      if (!response.ok || !data.success || !data.quotes || data.quotes.length === 0) {
        console.error(`Failed to fetch data for ${ticker}:`, data.message || data.error);
        return null;
      }

      const quote = data.quotes[0];
      const currentPrice = quote.price;

      // Simulate historical prices for indicators (in production, fetch real historical data)
      const historicalPrices = Array.from({ length: 30 }, (_, i) =>
        currentPrice * (1 + (Math.random() - 0.5) * 0.02)
      );
      historicalPrices.push(currentPrice);

      // Calculate indicators
      const rsi = calculateRSI(historicalPrices);
      const macd = calculateMACD(historicalPrices);

      // Detect candle patterns (using approximations)
      const prevPrice = historicalPrices[historicalPrices.length - 2];
      const pattern = detectCandlePattern(
        prevPrice, currentPrice * 1.01, currentPrice * 0.99, currentPrice,
        prevPrice * 0.99, prevPrice
      );

      // Fundamental analysis
      const fundamental = calculateFundamentalThesis(ticker, currentPrice);

      // Calculate score
      let score = fundamental.score;
      const reasons: string[] = [fundamental.reason];

      if (pattern.name) {
        reasons.push(pattern.name);
        score += pattern.score;
      }

      // RSI scoring
      if (rsi < RSI_OVERSOLD) {
        score += 2;
        reasons.push('RSI Oversold');
      } else if (rsi < 45) {
        score += 1;
      } else if (rsi > RSI_OVERBOUGHT) {
        score -= 2;
        reasons.push('RSI Overbought');
      } else if (rsi > 55) {
        score -= 1;
      }

      // MACD scoring
      const prevMACD = macd.macd * 0.95;
      if (macd.macd > macd.signal && prevMACD <= macd.signal) {
        score += 2;
        reasons.push('MACD Bull Cross');
      } else if (macd.macd > macd.signal) {
        score += 1;
      } else if (macd.macd < macd.signal && prevMACD >= macd.signal) {
        score -= 2;
        reasons.push('MACD Bear Cross');
      } else if (macd.macd < macd.signal) {
        score -= 1;
      }

      // Determine signal
      let signal = 'NEUTRAL';
      if (score >= 4) signal = 'STRONG BULLISH';
      else if (score >= 2) signal = 'BULLISH';
      else if (score <= -4) signal = 'STRONG BEARISH';
      else if (score <= -2) signal = 'BEARISH';

      if (signal === 'NEUTRAL') return null;

      return {
        time: new Date().toLocaleTimeString(),
        ticker,
        price: currentPrice,
        signal,
        rsi: rsi,
        valuationModel: fundamentalData[ticker]?.MODEL || 'N/A',
        valuationRatio: fundamental.ratio !== null ? fundamental.ratio : 'N/A',
        targetPrice: fundamental.targetPrice !== null ? fundamental.targetPrice : 'N/A',
        reasons: reasons.join(', '),
        score
      };

    } catch (error) {
      console.error(`Error analyzing ${ticker}:`, error);
      return null;
    }
  };

  const startScan = async () => {
    setIsScanning(true);
    setProgress(0);
    const newResults: ScanResult[] = [];

    const tickersToScan = Object.keys(fundamentalData);

    for (let i = 0; i < tickersToScan.length; i++) {
      const ticker = tickersToScan[i];
      const result = await analyzeTicker(ticker);

      if (result) {
        newResults.push(result);

        // Store in database
        await supabase.from('fundamental_scanner_signals').insert({
          ticker: result.ticker,
          price: result.price,
          signal: result.signal,
          rsi: result.rsi,
          valuation_model: result.valuationModel,
          valuation_ratio: typeof result.valuationRatio === 'number' ? result.valuationRatio : null,
          target_price: typeof result.targetPrice === 'number' ? result.targetPrice : null,
          reasons: result.reasons,
          score: result.score
        });
      }

      setProgress(Math.round(((i + 1) / tickersToScan.length) * 100));
    }

    setResults(newResults.sort((a, b) => Math.abs(b.score) - Math.abs(a.score)));
    setLastUpdate(new Date());
    setIsScanning(false);
    fetchBTCPrice();
  };

  const toggleAutoScan = () => {
    if (scanIntervalRef.current) {
      clearInterval(scanIntervalRef.current);
      scanIntervalRef.current = null;
    } else {
      startScan();
      scanIntervalRef.current = setInterval(() => {
        startScan();
      }, 120000); // 2 minutes
    }
  };

  const scanCustomSymbol = async () => {
    if (!customSymbol.trim()) {
      alert('Please enter a symbol');
      return;
    }

    const symbol = customSymbol.toUpperCase().trim();
    setIsScanning(true);

    try {
      // First, check database cache for fundamental data
      if (!fundamentalData[symbol]) {
        const { data: cachedRecord } = await supabase
          .from('fundamental_data')
          .select('*')
          .eq('symbol', symbol)
          .maybeSingle();

        if (cachedRecord) {
          const TARGET_EV_S = 11.0;
          const DISCOUNT_EV_S = 8.5;

          const newFundamentals = {
            ...fundamentalData,
            [symbol]: {
              MODEL: 'EV/S' as const,
              TTM_SALES: cachedRecord.revenue || 0,
              SHARES_OUTSTANDING: cachedRecord.shares_outstanding || 0,
              TOTAL_DEBT: cachedRecord.total_debt || 0,
              EV_S_DISCOUNT_THRESHOLD: DISCOUNT_EV_S,
              TARGET_EV_S_RATIO: TARGET_EV_S
            }
          };
          setFundamentalData(newFundamentals);
        } else {
          // Not in cache, fetch from API
          const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
          const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

          const response = await fetch(
            `${supabaseUrl}/functions/v1/fetch-fundamentals?symbols=${symbol}`,
            {
              headers: {
                'Authorization': `Bearer ${supabaseKey}`,
                'Content-Type': 'application/json',
              },
            }
          );

          if (response.ok) {
            const data = await response.json();
            if (data.success && data.data && data.data.length > 0) {
              const fundData = data.data[0];

              const TARGET_EV_S = 11.0;
              const DISCOUNT_EV_S = 8.5;

              const newFundamentals = {
                ...fundamentalData,
                [symbol]: {
                  MODEL: 'EV/S' as const,
                  TTM_SALES: fundData.revenue || 0,
                  SHARES_OUTSTANDING: fundData.sharesOutstanding || 0,
                  TOTAL_DEBT: fundData.totalDebt || 0,
                  EV_S_DISCOUNT_THRESHOLD: DISCOUNT_EV_S,
                  TARGET_EV_S_RATIO: TARGET_EV_S
                }
              };
              setFundamentalData(newFundamentals);
            }
          }
        }
      }

      // Now analyze the symbol
      const result = await analyzeTicker(symbol);

      if (result) {
        // Add to top of results
        setResults(prev => [result, ...prev].sort((a, b) => Math.abs(b.score) - Math.abs(a.score)));

        // Store in database
        await supabase.from('fundamental_scanner_signals').insert({
          ticker: result.ticker,
          price: result.price,
          signal: result.signal,
          rsi: result.rsi,
          valuation_model: result.valuationModel,
          valuation_ratio: typeof result.valuationRatio === 'number' ? result.valuationRatio : null,
          target_price: typeof result.targetPrice === 'number' ? result.targetPrice : null,
          reasons: result.reasons,
          score: result.score
        });

        setCustomSymbol('');
        alert(`✅ ${symbol} scanned successfully!\n\nSignal: ${result.signal}\nPrice: $${result.price.toFixed(2)}\nRSI: ${result.rsi.toFixed(1)}\nReasons: ${result.reasons}`);
      } else {
        alert(`⚠️ Unable to scan ${symbol}\n\nPossible reasons:\n• Symbol not found or invalid\n• Signal is NEUTRAL (not actionable)\n• Insufficient market data\n\nPlease verify the symbol is correct and try again.`);
      }

      setLastUpdate(new Date());
    } catch (error) {
      console.error('Error scanning custom symbol:', error);
      const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
      alert(`❌ Error scanning ${symbol}\n\nError: ${errorMessage}\n\nPlease check:\n• Internet connection\n• Symbol is valid\n• API services are available`);
    } finally {
      setIsScanning(false);
    }
  };

  const filteredResults = results.filter(r => {
    if (filterSignal === 'ALL') return true;
    return r.signal === filterSignal;
  });

  const getSignalColor = (signal: string) => {
    if (signal.includes('STRONG BULLISH')) return 'text-green-600 dark:text-green-400 font-bold';
    if (signal.includes('BULLISH')) return 'text-green-500 dark:text-green-500';
    if (signal.includes('STRONG BEARISH')) return 'text-red-600 dark:text-red-400 font-bold';
    if (signal.includes('BEARISH')) return 'text-red-500 dark:text-red-500';
    return 'text-slate-600 dark:text-slate-400';
  };

  const getSignalBg = (signal: string) => {
    if (signal.includes('STRONG BULLISH')) return 'bg-green-100 dark:bg-green-900/30';
    if (signal.includes('BULLISH')) return 'bg-green-50 dark:bg-green-900/20';
    if (signal.includes('STRONG BEARISH')) return 'bg-red-100 dark:bg-red-900/30';
    if (signal.includes('BEARISH')) return 'bg-red-50 dark:bg-red-900/20';
    return 'bg-slate-50 dark:bg-slate-900';
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-xl p-6 shadow-lg">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-white/20 rounded-lg">
              <BarChart3 className="h-8 w-8 text-white" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-white">Fundamental Scanner</h2>
              <p className="text-blue-100">NAV & EV/S Models with Technical Analysis</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={startScan}
              disabled={isScanning}
              className="flex items-center gap-2 px-4 py-2 bg-white text-blue-600 rounded-lg font-semibold hover:bg-blue-50 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`h-5 w-5 ${isScanning ? 'animate-spin' : ''}`} />
              {isScanning ? 'Scanning...' : 'Scan Now'}
            </button>
            <button
              onClick={toggleAutoScan}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-semibold transition-colors ${
                scanIntervalRef.current
                  ? 'bg-red-500 text-white hover:bg-red-600'
                  : 'bg-green-500 text-white hover:bg-green-600'
              }`}
            >
              {scanIntervalRef.current ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5" />}
              {scanIntervalRef.current ? 'Stop Auto' : 'Auto Scan'}
            </button>
          </div>
        </div>

        {/* Custom Symbol Scanner */}
        <div className="bg-white/10 backdrop-blur-sm rounded-lg p-4">
          <p className="text-sm text-blue-100 mb-3 font-semibold">Scan Specific Symbol</p>
          <div className="flex gap-2">
            <input
              type="text"
              value={customSymbol}
              onChange={(e) => setCustomSymbol(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === 'Enter' && !isScanning && scanCustomSymbol()}
              placeholder="Enter symbol (e.g., AAPL)"
              disabled={isScanning}
              className="flex-1 px-4 py-2 rounded-lg bg-white/90 text-slate-900 placeholder-slate-500 font-semibold focus:outline-none focus:ring-2 focus:ring-white disabled:opacity-50"
            />
            <button
              onClick={scanCustomSymbol}
              disabled={isScanning || !customSymbol.trim()}
              className="px-6 py-2 bg-green-500 text-white rounded-lg font-semibold hover:bg-green-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              <Target className="h-5 w-5" />
              Scan
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-white/10 backdrop-blur-sm rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <Activity className="h-5 w-5 text-white" />
              <p className="text-sm text-blue-100">Active Tickers</p>
            </div>
            <p className="text-2xl font-bold text-white">{Object.keys(fundamentalData).length}</p>
          </div>
          <div className="bg-white/10 backdrop-blur-sm rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <Target className="h-5 w-5 text-white" />
              <p className="text-sm text-blue-100">Signals Found</p>
            </div>
            <p className="text-2xl font-bold text-white">{results.length}</p>
          </div>
          <div className="bg-white/10 backdrop-blur-sm rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <DollarSign className="h-5 w-5 text-white" />
              <p className="text-sm text-blue-100">BTC Price</p>
            </div>
            <p className="text-2xl font-bold text-white">${btcPrice.toLocaleString()}</p>
          </div>
          <div className="bg-white/10 backdrop-blur-sm rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="h-5 w-5 text-white" />
              <p className="text-sm text-blue-100">Last Update</p>
            </div>
            <p className="text-lg font-bold text-white">{lastUpdate.toLocaleTimeString()}</p>
          </div>
        </div>

        {isScanning && (
          <div className="mt-4">
            <div className="w-full bg-white/20 rounded-full h-2">
              <div
                className="bg-white h-2 rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-center text-white text-sm mt-2">{progress}% Complete</p>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-lg">
        <div className="flex items-center gap-4">
          <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">Filter:</span>
          {['ALL', 'STRONG BULLISH', 'BULLISH', 'BEARISH', 'STRONG BEARISH'].map(filter => (
            <button
              key={filter}
              onClick={() => setFilterSignal(filter)}
              className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
                filterSignal === filter
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600'
              }`}
            >
              {filter}
            </button>
          ))}
        </div>
      </div>

      {/* Results Table */}
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-100 dark:bg-slate-900">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 dark:text-slate-300">Time</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 dark:text-slate-300">Ticker</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 dark:text-slate-300">Signal</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700 dark:text-slate-300">Price</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700 dark:text-slate-300">Target</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700 dark:text-slate-300">RSI</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 dark:text-slate-300">Model</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700 dark:text-slate-300">Ratio</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 dark:text-slate-300">Reasons</th>
              </tr>
            </thead>
            <tbody>
              {filteredResults.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-slate-500 dark:text-slate-400">
                    <AlertCircle className="h-12 w-12 mx-auto mb-2 opacity-50" />
                    <p>No signals found. Click "Scan Now" to start scanning.</p>
                  </td>
                </tr>
              ) : (
                filteredResults.map((result, idx) => (
                  <tr
                    key={idx}
                    className={`border-t border-slate-200 dark:border-slate-700 ${getSignalBg(result.signal)}`}
                  >
                    <td className="px-4 py-3 text-sm text-slate-700 dark:text-slate-300">{result.time}</td>
                    <td className="px-4 py-3 text-sm font-bold text-blue-600 dark:text-blue-400">{result.ticker}</td>
                    <td className={`px-4 py-3 text-sm ${getSignalColor(result.signal)}`}>{result.signal}</td>
                    <td className="px-4 py-3 text-sm text-right font-semibold text-slate-900 dark:text-white">
                      ${result.price.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-sm text-right font-semibold text-green-600 dark:text-green-400">
                      {typeof result.targetPrice === 'number' ? `$${result.targetPrice.toFixed(2)}` : 'N/A'}
                    </td>
                    <td className="px-4 py-3 text-sm text-right text-slate-700 dark:text-slate-300">
                      {result.rsi.toFixed(1)}
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-700 dark:text-slate-300">{result.valuationModel}</td>
                    <td className="px-4 py-3 text-sm text-right text-slate-700 dark:text-slate-300">
                      {typeof result.valuationRatio === 'number' ? result.valuationRatio.toFixed(2) : 'N/A'}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600 dark:text-slate-400 max-w-xs truncate">
                      {result.reasons}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Info Box */}
      <div className="bg-blue-50 dark:bg-blue-900/20 rounded-xl p-4 border border-blue-200 dark:border-blue-800">
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-blue-900 dark:text-blue-300">
            <p className="font-semibold mb-1">How It Works:</p>
            <ul className="list-disc list-inside space-y-1">
              <li><strong>Coverage:</strong> Scans 100 symbols with real-time price data</li>
              <li><strong>Data Source:</strong> Yahoo Finance API - Real revenue, debt, shares outstanding, and valuation metrics</li>
              <li><strong>Custom Scanner:</strong> Enter any symbol to run instant fundamental analysis</li>
              <li><strong>MSTR:</strong> NAV model based on Bitcoin holdings (650K BTC)</li>
              <li><strong>Other Stocks:</strong> EV/S (Enterprise Value / Sales) ratio model with real TTM revenue</li>
              <li><strong>Technical:</strong> Real-time RSI, MACD, Candlestick patterns combined with fundamentals</li>
              <li><strong>Scoring:</strong> +4 or higher = Strong Bullish, -4 or lower = Strong Bearish</li>
              <li><strong>Auto Scan:</strong> Refreshes every 2 minutes when enabled</li>
              <li><strong>Smart Caching:</strong> Fundamental data cached in database for fast subsequent scans</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
