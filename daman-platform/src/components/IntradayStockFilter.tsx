import { useState, useEffect } from 'react';
import { RefreshCw, TrendingUp, TrendingDown, Wifi, WifiOff } from 'lucide-react';
import { fetchLiveIntradayData, fetchMultipleIntradayData, DEFAULT_SCAN_SYMBOLS, IntradayStockData } from '../services/intradayStockService';

interface StockData {
  name: string;
  price: number;
  EMA20_15m: number;
  EMA50_15m: number;
  RSI3_5m: number;
  MACD_5m: number;
  MACDSignal_5m: number;
  source?: string;
}

interface FilterResult {
  triggered: boolean;
  criteria: string[];
  failedCriteria: string[];
}

const SUPPORT_TOLERANCE = 0.005;

const MOCK_DATA: Record<string, StockData> = {
  'META': { name: 'Meta Platforms Inc.', price: 500.00, EMA20_15m: 505.00, EMA50_15m: 502.00, RSI3_5m: 15.0, MACD_5m: 0.5, MACDSignal_5m: 0.2 },
  'SMCI': { name: 'Super Micro Computer, Inc.', price: 980.00, EMA20_15m: 979.00, EMA50_15m: 975.00, RSI3_5m: 18.0, MACD_5m: 1.0, MACDSignal_5m: 0.5 },
  'AMD': { name: 'Advanced Micro Devices, Inc.', price: 150.00, EMA20_15m: 149.00, EMA50_15m: 148.00, RSI3_5m: 12.0, MACD_5m: 0.5, MACDSignal_5m: 1.0 },
  'TSLA': { name: 'Tesla, Inc.', price: 200.00, EMA20_15m: 198.00, EMA50_15m: 202.00, RSI3_5m: 10.0, MACD_5m: 0.1, MACDSignal_5m: 0.0 },
  'GOOGL': { name: 'Alphabet Inc.', price: 180.00, EMA20_15m: 178.00, EMA50_15m: 175.00, RSI3_5m: 45.0, MACD_5m: 2.0, MACDSignal_5m: 1.5 },
  'UPST': { name: 'Upstart Holdings, Inc.', price: 25.00, EMA20_15m: 26.00, EMA50_15m: 28.00, RSI3_5m: 30.0, MACD_5m: -1.0, MACDSignal_5m: -0.5 }
};

const fetchStockData = async (ticker: string, useLiveData: boolean): Promise<StockData> => {
  if (useLiveData) {
    try {
      const liveData = await fetchLiveIntradayData(ticker);
      if (liveData) {
        return liveData;
      }
    } catch (error) {
      console.error(`Failed to fetch live data for ${ticker}, falling back to mock data`, error);
    }
  }

  await new Promise(resolve => setTimeout(resolve, 800));

  let data = MOCK_DATA[ticker];

  if (!data) {
    data = {
      name: `${ticker} Inc.`,
      price: 100.00,
      EMA20_15m: 101.00,
      EMA50_15m: 102.00,
      RSI3_5m: 55.0,
      MACD_5m: 0.5,
      MACDSignal_5m: 1.0,
      source: 'mock'
    };
  }

  return data;
};

const checkFilter = (stockData: StockData): FilterResult => {
  const results: FilterResult = {
    triggered: false,
    criteria: [],
    failedCriteria: []
  };

  const price = stockData.price;
  const rsi3_5m = stockData.RSI3_5m;
  const macd_5m = stockData.MACD_5m;
  const macdSignal_5m = stockData.MACDSignal_5m;
  const ema20_15m = stockData.EMA20_15m;
  const ema50_15m = stockData.EMA50_15m;

  if (ema20_15m > ema50_15m) {
    results.criteria.push(`15m Trend: EMA(20) $${ema20_15m.toFixed(2)} > EMA(50) $${ema50_15m.toFixed(2)} (Bullish Bias)`);
  } else {
    results.failedCriteria.push(`15m Trend: EMA(20) $${ema20_15m.toFixed(2)} <= EMA(50) $${ema50_15m.toFixed(2)} (Bearish Bias)`);
  }

  if (rsi3_5m < 20.0) {
    results.criteria.push(`5m RSI(3) Oversold: ${rsi3_5m.toFixed(2)} (< 20.0)`);
  } else {
    results.failedCriteria.push(`5m RSI(3) too high: ${rsi3_5m.toFixed(2)} (Not a pullback)`);
  }

  if (macd_5m > macdSignal_5m) {
    results.criteria.push(`5m MACD Bullish Crossover: MACD ${macd_5m.toFixed(2)} > Signal ${macdSignal_5m.toFixed(2)}`);
  } else {
    results.failedCriteria.push(`5m MACD is Bearish: MACD ${macd_5m.toFixed(2)} <= Signal ${macdSignal_5m.toFixed(2)}`);
  }

  const tolerance20Low = ema20_15m * (1 - SUPPORT_TOLERANCE);
  const tolerance20High = ema20_15m * (1 + SUPPORT_TOLERANCE);
  const tolerance50Low = ema50_15m * (1 - SUPPORT_TOLERANCE);
  const tolerance50High = ema50_15m * (1 + SUPPORT_TOLERANCE);

  let supportHit = false;
  let supportDetails = '';

  if (price >= tolerance20Low && price <= tolerance20High) {
    supportHit = true;
    supportDetails = `15m EMA(20) Support Hit: Price $${price.toFixed(2)} is near EMA20 $${ema20_15m.toFixed(2)} (0.5% tolerance)`;
  } else if (price >= tolerance50Low && price <= tolerance50High) {
    supportHit = true;
    supportDetails = `15m EMA(50) Support Hit: Price $${price.toFixed(2)} is near EMA50 $${ema50_15m.toFixed(2)} (0.5% tolerance)`;
  }

  if (supportHit) {
    results.criteria.push(supportDetails);
  } else {
    results.failedCriteria.push(`Price ($${price.toFixed(2)}) is outside the 0.5% range of 15m EMAs.`);
  }

  if (results.criteria.length === 4) {
    results.triggered = true;
  }

  return results;
};

export default function IntradayStockFilter() {
  const [automaticResults, setAutomaticResults] = useState<JSX.Element | null>(null);
  const [manualResults, setManualResults] = useState<JSX.Element | null>(null);
  const [manualTicker, setManualTicker] = useState('');
  const [isAutoScanning, setIsAutoScanning] = useState(false);
  const [isManualChecking, setIsManualChecking] = useState(false);
  const [useLiveData, setUseLiveData] = useState(true);
  const [scanSymbols, setScanSymbols] = useState<string[]>(DEFAULT_SCAN_SYMBOLS);

  const createResultHtml = (ticker: string, data: StockData, filterResult: FilterResult) => {
    const isTriggered = filterResult.triggered;

    return (
      <div
        key={ticker}
        className={`p-4 rounded-lg mb-3 shadow-md transition-all duration-300 ${
          isTriggered ? 'bg-emerald-900/20 border-l-4 border-emerald-500' : 'bg-slate-800/50 border border-slate-700'
        }`}
      >
        <div className="flex flex-wrap justify-between items-center mb-2 border-b border-slate-700 pb-2">
          <div>
            <h3 className="text-xl font-bold text-white">{ticker}: {data.name}</h3>
            {data.source && (
              <span className="text-xs text-slate-500">Source: {data.source}</span>
            )}
          </div>
          <span className={`text-sm font-bold p-1 rounded-md ${
            isTriggered ? 'text-emerald-400' : 'text-red-400'
          }`}>
            {isTriggered ? 'INTRADAY BUY SIGNAL FIRED' : 'No Intraday Signal'}
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 text-sm gap-y-1 mb-3">
          <div className="text-slate-400">Price: <span className="text-white font-bold">${data.price.toFixed(2)}</span></div>
          <div className="text-slate-400">15m EMA(20): <span className="text-white">${data.EMA20_15m.toFixed(2)}</span></div>
          <div className="text-slate-400">5m RSI(3): <span className="text-white">{data.RSI3_5m.toFixed(2)}</span></div>
          <div className="text-slate-400">5m MACD: <span className="text-white">{data.MACD_5m.toFixed(2)}</span></div>
          <div className="text-slate-400">15m EMA(50): <span className="text-white">${data.EMA50_15m.toFixed(2)}</span></div>
          <div className="text-slate-400">5m Signal: <span className="text-white">{data.MACDSignal_5m.toFixed(2)}</span></div>
        </div>

        <div className="mt-3 bg-slate-900/50 p-3 rounded">
          <p className="font-semibold text-slate-300 mb-2">Intraday Filter Conditions ({filterResult.criteria.length}/4 Met):</p>
          <ul className="space-y-1 text-sm">
            {filterResult.criteria.map((c, i) => (
              <li key={i} className="text-emerald-300 font-medium">{c}</li>
            ))}
            {filterResult.failedCriteria.map((c, i) => (
              <li key={i} className="text-red-400">{c}</li>
            ))}
          </ul>
        </div>
      </div>
    );
  };

  const runAutomaticFilter = async () => {
    setIsAutoScanning(true);
    setAutomaticResults(
      <div className="text-center py-4">
        <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-2 text-daman-blue-500" />
        <p className="text-daman-blue-400">
          {useLiveData ? `Scanning ${scanSymbols.length} stocks for intraday signals...` : 'Scanning market list (Simulated data)...'}
        </p>
      </div>
    );

    const tickers = useLiveData ? scanSymbols : Object.keys(MOCK_DATA);
    const signalResults: JSX.Element[] = [];
    let triggeredCount = 0;
    let scannedCount = 0;
    let failedCount = 0;

    for (const ticker of tickers) {
      try {
        const data = await fetchStockData(ticker, useLiveData);
        if (!data) {
          failedCount++;
          continue;
        }
        const result = checkFilter(data);
        scannedCount++;

        if (result.triggered) {
          signalResults.push(createResultHtml(ticker, data, result));
          triggeredCount++;
        }

        if (scannedCount % 10 === 0) {
          setAutomaticResults(
            <div className="text-center py-4">
              <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-2 text-daman-blue-500" />
              <p className="text-daman-blue-400">
                Scanning... {scannedCount}/{tickers.length} stocks checked
              </p>
              <p className="text-emerald-400 text-sm mt-2">
                {triggeredCount} signals found so far
              </p>
            </div>
          );
        }
      } catch (error) {
        failedCount++;
        console.error(`Error scanning ${ticker}:`, error);
      }
    }

    setAutomaticResults(
      <div>
        <p className="text-md font-bold mb-3 text-white">
          Scan Complete! Found <span className="text-emerald-400">{triggeredCount}</span> Intraday signals from <span className="text-daman-blue-400">{scannedCount}</span> stocks scanned.
          {failedCount > 0 && (
            <span className="text-amber-400 text-sm ml-2">
              ({failedCount} symbols had insufficient data)
            </span>
          )}
        </p>
        {signalResults.length > 0 ? (
          signalResults
        ) : (
          <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-8 text-center">
            <p className="text-slate-400 text-lg">No intraday signals found at this time.</p>
            <p className="text-slate-500 text-sm mt-2">
              {useLiveData
                ? 'Scanners work best during market hours (9:30 AM - 4:00 PM ET). Outside hours, we use the most recent available data.'
                : 'Try again later or adjust filter criteria.'
              }
            </p>
          </div>
        )}
      </div>
    );
    setIsAutoScanning(false);
  };

  const runManualFilter = async () => {
    const ticker = manualTicker.trim().toUpperCase();

    if (!ticker) {
      setManualResults(
        <p className="text-center py-4 text-red-500">Please enter a stock ticker.</p>
      );
      return;
    }

    setIsManualChecking(true);
    setManualResults(
      <div className="text-center py-4">
        <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-2 text-daman-blue-500" />
        <p className="text-daman-blue-400">Fetching data for <strong>{ticker}</strong>...</p>
      </div>
    );

    const data = await fetchStockData(ticker, useLiveData);
    const result = checkFilter(data);
    setManualResults(createResultHtml(ticker, data, result));
    setIsManualChecking(false);
  };

  useEffect(() => {
    runAutomaticFilter();
  }, []);

  return (
    <div className="space-y-6">
      <div className="bg-slate-900/50 border border-emerald-500/30 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4 border-b border-slate-700 pb-2">
          <h3 className="text-xl font-semibold text-emerald-400">
            Live Data Feed
          </h3>
          <button
            onClick={() => setUseLiveData(!useLiveData)}
            className={`flex items-center space-x-2 px-4 py-2 rounded-lg font-semibold transition-all ${
              useLiveData
                ? 'bg-emerald-600 text-white hover:bg-emerald-700'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            {useLiveData ? (
              <>
                <Wifi className="h-4 w-4" />
                <span>Live (Alpaca)</span>
              </>
            ) : (
              <>
                <WifiOff className="h-4 w-4" />
                <span>Mock Data</span>
              </>
            )}
          </button>
        </div>
        {useLiveData ? (
          <div className="text-sm text-emerald-300 bg-emerald-900/20 p-3 rounded">
            <p className="font-semibold mb-1">Real-Time Alpaca Data Active</p>
            <p className="text-slate-400">
              Fetching live 5m and 15m intraday bars with calculated EMA, RSI, and MACD indicators.
              Scanning {scanSymbols.length} symbols: {scanSymbols.slice(0, 8).join(', ')}, and more...
            </p>
          </div>
        ) : (
          <div className="text-sm text-amber-300 bg-amber-900/20 p-3 rounded">
            <p className="font-semibold mb-1">Mock Data Mode</p>
            <p className="text-slate-400">
              Using simulated data for demonstration. Enable Live Data to use real-time Alpaca market data.
            </p>
          </div>
        )}
      </div>

      <div className="bg-slate-900/50 border border-slate-700 rounded-lg p-6">
        <h3 className="text-xl font-semibold mb-4 text-white border-b border-slate-700 pb-2">
          1. Automatic Market Screening (Intraday Focus)
        </h3>
        <button
          onClick={runAutomaticFilter}
          disabled={isAutoScanning}
          className="w-full py-3 bg-daman-blue-600 hover:bg-daman-blue-700 disabled:opacity-50 text-white font-semibold rounded-lg transition duration-150 shadow-md focus:outline-none focus:ring-2 focus:ring-daman-blue-500 focus:ring-opacity-50 flex items-center justify-center space-x-2"
        >
          {isAutoScanning ? (
            <>
              <RefreshCw className="h-5 w-5 animate-spin" />
              <span>Scanning...</span>
            </>
          ) : (
            <span>
              {useLiveData
                ? `Run Live Scan (${scanSymbols.length} Stocks)`
                : 'Run Automatic Scan on Full List (Mock Data)'
              }
            </span>
          )}
        </button>
        <div className="mt-4 min-h-[200px]">
          {automaticResults || (
            <p className="text-slate-500 italic text-center pt-8">Press the button above to run the full market scan.</p>
          )}
        </div>
      </div>

      <div className="bg-slate-900/50 border border-slate-700 rounded-lg p-6">
        <h3 className="text-xl font-semibold mb-4 text-white border-b border-slate-700 pb-2">
          2. Manual Ticker Check
        </h3>
        <div className="flex flex-col sm:flex-row gap-4">
          <input
            type="text"
            value={manualTicker}
            onChange={(e) => setManualTicker(e.target.value.toUpperCase())}
            onKeyPress={(e) => e.key === 'Enter' && runManualFilter()}
            placeholder="Enter Ticker (e.g., SMCI, UPST, or anything else)"
            className="flex-grow p-3 rounded-lg bg-slate-800 border border-slate-600 text-white placeholder-slate-500 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 focus:outline-none uppercase"
          />
          <button
            onClick={runManualFilter}
            disabled={isManualChecking}
            className="py-3 px-6 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-semibold rounded-lg transition duration-150 shadow-md focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-opacity-50 flex items-center justify-center space-x-2"
          >
            {isManualChecking ? (
              <>
                <RefreshCw className="h-5 w-5 animate-spin" />
                <span>Checking...</span>
              </>
            ) : (
              <span>Check Ticker Manually</span>
            )}
          </button>
        </div>
        <div className="mt-4 min-h-[200px]">
          {manualResults || (
            <p className="text-slate-500 italic text-center pt-8">Enter a stock ticker and check its criteria.</p>
          )}
        </div>
      </div>
    </div>
  );
}
