import { useState, useEffect } from 'react';
import { RefreshCw, Wifi, WifiOff } from 'lucide-react';
import { fetchLiveDailyData, fetchMultipleDailyData, DEFAULT_DAILY_SCAN_SYMBOLS, DailyStockData } from '../services/dailyStockService';

interface StockData {
  name: string;
  price: number;
  SMA50: number;
  SMA200: number;
  RSI2: number;
  MACD: number;
  MACDSignal: number;
  source?: string;
}

interface FilterResult {
  triggered: boolean;
  criteria: string[];
  failedCriteria: string[];
}

const SUPPORT_TOLERANCE = 0.02;

const MOCK_DATA: Record<string, StockData> = {
  'META': { name: 'Meta Platforms Inc.', price: 500.00, SMA50: 450.00, SMA200: 380.00, RSI2: 65.0, MACD: 10.0, MACDSignal: 12.0 },
  'SMCI': { name: 'Super Micro Computer, Inc.', price: 980.00, SMA50: 1000.00, SMA200: 700.00, RSI2: 8.5, MACD: 1.5, MACDSignal: 1.0 },
  'AMD': { name: 'Advanced Micro Devices, Inc.', price: 150.00, SMA50: 140.00, SMA200: 120.00, RSI2: 35.0, MACD: 5.0, MACDSignal: 4.5 },
  'TSLA': { name: 'Tesla, Inc.', price: 200.00, SMA50: 205.00, SMA200: 190.00, RSI2: 9.8, MACD: -0.5, MACDSignal: -1.0 },
  'GOOGL': { name: 'Alphabet Inc.', price: 180.00, SMA50: 175.00, SMA200: 160.00, RSI2: 15.0, MACD: 2.0, MACDSignal: 1.5 },
  'UPST': { name: 'Upstart Holdings, Inc.', price: 25.00, SMA50: 27.00, SMA200: 35.00, RSI2: 20.0, MACD: -1.0, MACDSignal: -0.5 }
};

const fetchStockData = async (ticker: string, useLiveData: boolean): Promise<StockData> => {
  if (useLiveData) {
    try {
      const liveData = await fetchLiveDailyData(ticker);
      if (liveData) {
        return liveData;
      }
    } catch (error) {
      console.error(`Failed to fetch live daily data for ${ticker}, falling back to mock data`, error);
    }
  }

  await new Promise(resolve => setTimeout(resolve, 800));

  let data = MOCK_DATA[ticker];

  if (!data) {
    data = {
      name: `${ticker} Inc.`,
      price: 100.00,
      SMA50: 102.00,
      SMA200: 95.00,
      RSI2: 55.0,
      MACD: 0.5,
      MACDSignal: 1.0,
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
  const rsi2 = stockData.RSI2;
  const macd = stockData.MACD;
  const macdSignal = stockData.MACDSignal;
  const sma50 = stockData.SMA50;
  const sma200 = stockData.SMA200;

  if (rsi2 < 10.0) {
    results.criteria.push(`RSI(2) Oversold: ${rsi2.toFixed(2)} (< 10.0)`);
  } else {
    results.failedCriteria.push(`RSI(2) too high: ${rsi2.toFixed(2)}`);
  }

  if (macd > macdSignal) {
    results.criteria.push(`MACD Bullish Crossover: MACD ${macd.toFixed(2)} > Signal ${macdSignal.toFixed(2)}`);
  } else {
    results.failedCriteria.push(`MACD is Bearish: MACD ${macd.toFixed(2)} <= Signal ${macdSignal.toFixed(2)}`);
  }

  const tolerance50Low = sma50 * (1 - SUPPORT_TOLERANCE);
  const tolerance50High = sma50 * (1 + SUPPORT_TOLERANCE);
  const tolerance200Low = sma200 * (1 - SUPPORT_TOLERANCE);
  const tolerance200High = sma200 * (1 + SUPPORT_TOLERANCE);

  let supportHit = false;
  let supportDetails = '';

  if (price >= tolerance50Low && price <= tolerance50High) {
    supportHit = true;
    supportDetails = `SMA(50) Support Hit: Price $${price.toFixed(2)} is near SMA50 $${sma50.toFixed(2)}`;
  } else if (price >= tolerance200Low && price <= tolerance200High) {
    supportHit = true;
    supportDetails = `SMA(200) Support Hit: Price $${price.toFixed(2)} is near SMA200 $${sma200.toFixed(2)}`;
  }

  if (supportHit) {
    results.criteria.push(supportDetails);
  } else {
    results.failedCriteria.push(`Price ($${price.toFixed(2)}) is outside the 2.0% range of both SMA50 ($${sma50.toFixed(2)}) and SMA200 ($${sma200.toFixed(2)}).`);
  }

  if (results.criteria.length === 3) {
    results.triggered = true;
  }

  return results;
};

export default function DailyStockFilter() {
  const [automaticResults, setAutomaticResults] = useState<JSX.Element | null>(null);
  const [manualResults, setManualResults] = useState<JSX.Element | null>(null);
  const [manualTicker, setManualTicker] = useState('');
  const [isAutoScanning, setIsAutoScanning] = useState(false);
  const [isManualChecking, setIsManualChecking] = useState(false);
  const [useLiveData, setUseLiveData] = useState(true);
  const [scanSymbols, setScanSymbols] = useState<string[]>(DEFAULT_DAILY_SCAN_SYMBOLS);

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
            {isTriggered ? 'SIGNAL FIRED' : 'No Signal'}
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 text-sm gap-y-1 mb-3">
          <div className="text-slate-400">Price: <span className="text-white font-bold">${data.price.toFixed(2)}</span></div>
          <div className="text-slate-400">RSI(2): <span className="text-white">{data.RSI2.toFixed(2)}</span></div>
          <div className="text-slate-400">MACD: <span className="text-white">{data.MACD.toFixed(2)}</span></div>
          <div className="text-slate-400">SMA(50): <span className="text-white">${data.SMA50.toFixed(2)}</span></div>
          <div className="text-slate-400">SMA(200): <span className="text-white">${data.SMA200.toFixed(2)}</span></div>
          <div className="text-slate-400">Signal: <span className="text-white">{data.MACDSignal.toFixed(2)}</span></div>
        </div>

        <div className="mt-3 bg-slate-900/50 p-3 rounded">
          <p className="font-semibold text-slate-300 mb-2">Filter Conditions ({filterResult.criteria.length}/3 Met):</p>
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
          {useLiveData ? `Scanning ${scanSymbols.length} stocks for swing trade signals...` : 'Scanning market list (Simulated data)...'}
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
          Scan Complete! Found <span className="text-emerald-400">{triggeredCount}</span> swing trade signals from <span className="text-daman-blue-400">{scannedCount}</span> stocks scanned.
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
            <p className="text-slate-400 text-lg">No swing trade signals found at this time.</p>
            <p className="text-slate-500 text-sm mt-2">
              {useLiveData
                ? 'Swing scanners work 24/7 using daily bar data. Results shown are based on the most recent trading day close.'
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
            <p className="font-semibold mb-1">Real-Time Alpaca Daily Data Active</p>
            <p className="text-slate-400">
              Fetching live daily bars with calculated SMA(50), SMA(200), RSI(2), and MACD indicators for swing trading.
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
          1. Automatic Market Screening (Swing Trading Focus)
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
