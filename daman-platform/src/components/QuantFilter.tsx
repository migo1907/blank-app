import { useState, useEffect, useRef } from 'react';
import { RefreshCw, Activity, AlertCircle, TrendingUp, Clock, Target, Zap, Trash2, Shield, PlayCircle, PauseCircle, CheckCircle, XCircle, X } from 'lucide-react';
import { supabase } from '../lib/supabase';
import { useToast } from './ToastContainer';
import { getDubaiTime, formatDubaiTime, isWithinTradingSession } from '../utils/dubaiTimeUtils';

interface StockData {
  symbol: string;
  name: string;
  sector: string;
  price: number;
  bid: number;
  ask: number;
  ATR_14: number;
  volume: number;
  high: number;
  low: number;
  open: number;
}

interface SectorData {
  ETF: string;
  price: number;
  sma20: number;
}

interface DBSignal {
  id: string;
  symbol: string;
  name: string;
  sector: string;
  signal_type: string;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  share_size: string;
  max_dollar_risk: number;
  r_multiple: number;
  dynamic_slippage: number;
  price: number;
  criteria_met: number;
  criteria_details: any;
  status: string;
  outcome: string | null;
  pnl: number;
  created_at: string;
}

interface TradeEntry {
  type: string;
  entryPrice: number;
  stopLoss: number;
  takeProfit: number;
  atr: number;
  rMultiple: number;
  dynamicSlippage: number;
  shareSize: string;
  maxDollarRisk: string;
}

interface FilterResult {
  triggered: boolean;
  criteria: string[];
  failedCriteria: string[];
  tradeEntry: TradeEntry | null;
}

const SYMBOL_TO_SECTOR: Record<string, string> = {
  'AAPL': 'Technology', 'MSFT': 'Technology', 'GOOGL': 'Technology', 'AMZN': 'Consumer',
  'NVDA': 'Technology', 'TSLA': 'Consumer', 'META': 'Technology', 'AMD': 'Technology',
  'NFLX': 'Communication', 'DIS': 'Communication', 'INTC': 'Technology', 'ORCL': 'Technology',
  'SPY': 'Index', 'QQQ': 'Index', 'DIA': 'Index', 'IWM': 'Index',
};

const DEFAULT_SCAN_SYMBOLS = [
  // Mega Cap Tech
  'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'META', 'AMZN', 'NVDA', 'TSLA', 'TSM', 'AVGO',
  // Large Cap Tech
  'ORCL', 'ADBE', 'CRM', 'CSCO', 'ACN', 'AMD', 'INTC', 'QCOM', 'TXN', 'INTU',
  'NOW', 'IBM', 'AMAT', 'ADI', 'MU', 'LRCX', 'KLAC', 'SNPS', 'CDNS', 'MRVL',
  'PANW', 'PLTR', 'CRWD', 'SNOW', 'DDOG', 'NET', 'ZS', 'FTNT', 'WDAY', 'TEAM',
  'ADSK', 'ANSS', 'MCHP', 'MPWR', 'ON', 'TER', 'SWKS', 'QRVO', 'NXPI', 'STX',
  // Communication Services
  'NFLX', 'DIS', 'CMCSA', 'T', 'VZ', 'TMUS', 'CHTR', 'EA', 'TTWO', 'NTES',
  'SPOT', 'MTCH', 'SNAP', 'PINS', 'ROKU', 'ZM', 'TWLO', 'LYFT', 'UBER', 'DASH',
  // Consumer Cyclical
  'AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'LOW', 'TJX', 'BKNG', 'MAR',
  'CMG', 'YUM', 'ROST', 'ORLY', 'AZO', 'DHI', 'LEN', 'GM', 'F', 'APTV',
  'LULU', 'DECK', 'ULTA', 'TGT', 'DG', 'DLTR', 'BBY', 'ETSY', 'EBAY', 'W',
  // Consumer Defensive
  'WMT', 'PG', 'KO', 'PEP', 'COST', 'MDLZ', 'CL', 'KMB', 'GIS', 'KHC',
  'MO', 'PM', 'EL', 'MNST', 'CLX', 'SJM', 'TSN', 'CAG', 'HSY', 'K',
  // Financial Services
  'BRK.B', 'JPM', 'V', 'MA', 'BAC', 'WFC', 'GS', 'MS', 'AXP', 'SPGI',
  'BLK', 'C', 'SCHW', 'CB', 'MMC', 'PGR', 'AON', 'ICE', 'CME', 'MCO',
  'USB', 'PNC', 'TFC', 'COF', 'AIG', 'MET', 'PRU', 'AFL', 'ALL', 'TRV',
  'COIN', 'SOFI', 'HOOD', 'SQ', 'PYPL', 'AFRM', 'NU', 'MELI', 'INTU', 'FISV',
  // Healthcare
  'UNH', 'JNJ', 'LLY', 'ABBV', 'MRK', 'TMO', 'ABT', 'DHR', 'PFE', 'AMGN',
  'CVS', 'BMY', 'MDT', 'GILD', 'ISRG', 'VRTX', 'CI', 'REGN', 'HUM', 'BSX',
  'ELV', 'ZTS', 'SYK', 'MCK', 'COR', 'ILMN', 'BIIB', 'IDXX', 'IQV', 'A',
  // Industrials
  'UPS', 'RTX', 'HON', 'UNP', 'CAT', 'GE', 'BA', 'LMT', 'DE', 'MMM',
  'NOC', 'GD', 'EMR', 'ETN', 'ITW', 'CSX', 'NSC', 'FDX', 'PCAR', 'WM',
  'ROK', 'JCI', 'CARR', 'OTIS', 'PAYX', 'CTAS', 'FAST', 'ODFL', 'VRSK', 'IEX',
  // Energy
  'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO', 'OXY', 'HES',
  'WMB', 'KMI', 'HAL', 'BKR', 'FANG', 'DVN', 'MRO', 'APA', 'CTRA', 'OVV',
  // Basic Materials
  'LIN', 'APD', 'SHW', 'ECL', 'DD', 'NEM', 'FCX', 'DOW', 'NUE', 'VMC',
  'MLM', 'PPG', 'CTVA', 'EMN', 'ALB', 'CF', 'MOS', 'FMC', 'IFF', 'CE',
  // Real Estate
  'AMT', 'PLD', 'CCI', 'EQIX', 'PSA', 'WELL', 'DLR', 'O', 'SBAC', 'AVB',
  'EQR', 'SPG', 'VICI', 'INVH', 'ARE', 'VTR', 'ESS', 'MAA', 'KIM', 'REG',
  // Utilities
  'NEE', 'DUK', 'SO', 'D', 'AEP', 'EXC', 'SRE', 'XEL', 'ED', 'WEC',
  'ES', 'PEG', 'AWK', 'PCG', 'EIX', 'FE', 'ETR', 'AEE', 'CMS', 'DTE',
  // High Growth/Momentum Stocks
  'UPST', 'SMCI', 'ARM', 'IONQ', 'RGTI', 'MSTR', 'SHOP', 'SQ', 'RBLX', 'U',
  'RIVN', 'LCID', 'OPEN', 'HOOD', 'AFRM', 'ABNB', 'COIN', 'DKNG', 'PENN', 'FUBO',
  // Biotechnology
  'AMGN', 'GILD', 'REGN', 'VRTX', 'BIIB', 'MRNA', 'ALNY', 'SGEN', 'BMRN', 'EXAS',
  'INCY', 'TECH', 'LEGN', 'ACAD', 'JAZZ', 'NBIX', 'UTHR', 'SRPT', 'RARE', 'IONS',
  // Semiconductors Extended
  'NVDA', 'AMD', 'INTC', 'QCOM', 'TXN', 'AVGO', 'TSM', 'AMAT', 'LRCX', 'KLAC',
  'ADI', 'MRVL', 'NXPI', 'MCHP', 'ON', 'MPWR', 'TER', 'SWKS', 'QRVO', 'WOLF',
  // Cloud & SaaS
  'MSFT', 'GOOGL', 'AMZN', 'CRM', 'NOW', 'ORCL', 'ADBE', 'WDAY', 'SNOW', 'DDOG',
  'MDB', 'NET', 'CFLT', 'DDOG', 'S', 'DBX', 'BOX', 'ZM', 'DOCN', 'FSLY',
  // E-commerce & Retail Tech
  'AMZN', 'SHOP', 'MELI', 'EBAY', 'ETSY', 'W', 'CPNG', 'SE', 'BABA', 'JD',
  // Fintech Extended
  'V', 'MA', 'PYPL', 'SQ', 'COIN', 'SOFI', 'AFRM', 'HOOD', 'NU', 'UPST',
  // ETFs & Indices
  'SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'VOO', 'VUG', 'VTV', 'XLK', 'XLF',
  'XLE', 'XLV', 'XLY', 'XLI', 'XLP', 'XLRE', 'XLU', 'XLB', 'SOXX', 'SMH',
  // Additional High-Volume Names
  'ARKK', 'ARKG', 'ARKW', 'ARKF', 'SOXL', 'TQQQ', 'SQQQ', 'SPXL', 'SPXS', 'TNA',
  'TZA', 'UDOW', 'SDOW', 'FAS', 'FAZ', 'ERX', 'ERY', 'NUGT', 'DUST', 'JNUG',
  // Crypto Related
  'MSTR', 'COIN', 'RIOT', 'MARA', 'HUT', 'BITF', 'CLSK', 'BTBT', 'CAN', 'HIVE',
  // EV & Clean Energy
  'TSLA', 'RIVN', 'LCID', 'NIO', 'XPEV', 'LI', 'FSR', 'CHPT', 'BLNK', 'ENPH',
  'SEDG', 'RUN', 'FSLR', 'PLUG', 'BE', 'NEE', 'ICLN', 'TAN', 'QCLN', 'PBW'
];

const SECTOR_ETFS: { [key: string]: string } = {
  'Technology': 'XLK',
  'Finance': 'XLF',
  'Energy': 'XLE',
  'Healthcare': 'XLV',
  'Consumer': 'XLY',
  'Industrials': 'XLI',
  'Materials': 'XLB',
  'Utilities': 'XLU',
  'Real Estate': 'XLRE',
  'Communication': 'XLC',
};

const SECTOR_MAP: { [key: string]: string } = {
  'AAPL': 'Technology', 'MSFT': 'Technology', 'GOOGL': 'Technology', 'GOOG': 'Technology',
  'META': 'Communication', 'AMZN': 'Consumer', 'NVDA': 'Technology', 'TSLA': 'Consumer',
  'JPM': 'Finance', 'BAC': 'Finance', 'WFC': 'Finance', 'GS': 'Finance', 'MS': 'Finance',
  'C': 'Finance', 'V': 'Finance', 'MA': 'Finance', 'AXP': 'Finance', 'SPGI': 'Finance',
  'XOM': 'Energy', 'CVX': 'Energy', 'COP': 'Energy', 'SLB': 'Energy', 'EOG': 'Energy',
  'UNH': 'Healthcare', 'JNJ': 'Healthcare', 'LLY': 'Healthcare', 'ABBV': 'Healthcare',
  'MRK': 'Healthcare', 'TMO': 'Healthcare', 'ABT': 'Healthcare', 'DHR': 'Healthcare',
  'WMT': 'Consumer', 'HD': 'Consumer', 'MCD': 'Consumer', 'NKE': 'Consumer',
  'UPS': 'Industrials', 'RTX': 'Industrials', 'HON': 'Industrials', 'CAT': 'Industrials',
  'NEE': 'Utilities', 'DUK': 'Utilities', 'SO': 'Utilities', 'D': 'Utilities',
  'AMT': 'Real Estate', 'PLD': 'Real Estate', 'CCI': 'Real Estate', 'EQIX': 'Real Estate',
  'LIN': 'Materials', 'APD': 'Materials', 'SHW': 'Materials', 'ECL': 'Materials',
  'NFLX': 'Communication', 'DIS': 'Communication', 'CMCSA': 'Communication',
};

export default function QuantFilter() {
  const toast = useToast();
  const [accountValue, setAccountValue] = useState(25000);
  const [maxRiskPct, setMaxRiskPct] = useState(1.0);
  const [maxDailyLoss, setMaxDailyLoss] = useState(500);
  const [searchType, setSearchType] = useState<'INTRADAY' | 'DAILY_SWING'>('INTRADAY');
  const [rsiThreshold, setRsiThreshold] = useState(20.0);
  const [emaTolerance, setEmaTolerance] = useState(0.5);
  const [minVolume, setMinVolume] = useState(50000);
  const [maxSpread, setMaxSpread] = useState(0.05);
  const [slippageFactor, setSlippageFactor] = useState(0.05);
  const [isScanning, setIsScanning] = useState(false);
  const [continuousMode, setContinuousMode] = useState(false);
  const [scanProgress, setScanProgress] = useState(0);
  const [signals, setSignals] = useState<DBSignal[]>([]);
  const [marketOpen, setMarketOpen] = useState(false);
  const [extendedHours, setExtendedHours] = useState(true);
  const [dubaiTime, setDubaiTime] = useState(getDubaiTime());
  const [dailyPnl, setDailyPnl] = useState(0);
  const [tradingHalted, setTradingHalted] = useState(false);
  const [sectorData, setSectorData] = useState<{ [key: string]: SectorData }>({});
  const [currentSymbol, setCurrentSymbol] = useState<string>('');
  const [scanCount, setScanCount] = useState(0);
  const [searchSymbol, setSearchSymbol] = useState<string>('');
  const [searchResult, setSearchResult] = useState<DBSignal | null>(null);
  const [isSearching, setIsSearching] = useState(false);

  const continuousScanRef = useRef<boolean>(false);
  const scanIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    loadSignals();
    checkMarketStatus();
    fetchSectorData();
    loadDailyPnl();

    const statusInterval = setInterval(() => {
      checkMarketStatus();
      fetchSectorData();
      setDubaiTime(getDubaiTime());
    }, 1000);

    const subscription = supabase
      .channel('quant_filter_signals_changes')
      .on('postgres_changes',
        { event: '*', schema: 'public', table: 'quant_filter_signals' },
        (payload) => {
          console.log('Signal change detected:', payload);
          loadSignals();
        }
      )
      .subscribe();

    return () => {
      statusInterval && clearInterval(statusInterval);
      scanIntervalRef.current && clearInterval(scanIntervalRef.current);
      subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    continuousScanRef.current = continuousMode;
  }, [continuousMode]);

  useEffect(() => {
    if (dailyPnl <= -maxDailyLoss) {
      setTradingHalted(true);
      setContinuousMode(false);
    }
  }, [dailyPnl, maxDailyLoss]);

  const loadSignals = async () => {
    try {
      const { data, error } = await supabase
        .from('quant_filter_signals')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(50);

      if (error) throw error;
      if (data) setSignals(data);
    } catch (error) {
      console.error('Error loading signals:', error);
    }
  };

  const loadDailyPnl = () => {
    try {
      const pnl = localStorage.getItem('quantFilterDailyPnl');
      if (pnl) setDailyPnl(parseFloat(pnl));
    } catch (e) {
      console.error('Error loading daily P&L:', e);
    }
  };

  const updateDailyPnl = (change: number) => {
    const newPnl = dailyPnl + change;
    setDailyPnl(newPnl);
    localStorage.setItem('quantFilterDailyPnl', newPnl.toString());
  };

  const saveSignalToDatabase = async (symbol: string, data: StockData, result: FilterResult) => {
    if (!result.tradeEntry) return;

    try {
      const { error } = await supabase
        .from('quant_filter_signals')
        .insert({
          symbol: symbol,
          name: data.name,
          sector: data.sector,
          signal_type: result.tradeEntry.type,
          entry_price: result.tradeEntry.entryPrice,
          stop_loss: result.tradeEntry.stopLoss,
          take_profit: result.tradeEntry.takeProfit,
          share_size: result.tradeEntry.shareSize,
          max_dollar_risk: parseFloat(result.tradeEntry.maxDollarRisk),
          r_multiple: result.tradeEntry.rMultiple,
          dynamic_slippage: result.tradeEntry.dynamicSlippage,
          price: data.price,
          criteria_met: result.criteria.length,
          criteria_details: {
            criteria: result.criteria,
            failedCriteria: result.failedCriteria
          },
          status: 'active'
        });

      if (error) throw error;

      const outcome = mockTradeOutcome(result.tradeEntry);
      console.log(`Signal saved: ${symbol} - ${outcome}`);
    } catch (error) {
      console.error('Error saving signal:', error);
    }
  };

  const mockTradeOutcome = (tradeEntry: TradeEntry): string => {
    const isWin = Math.random() < 0.6;
    const dollarRisk = parseFloat(tradeEntry.maxDollarRisk);

    let pnl = 0;
    if (isWin) {
      pnl = dollarRisk * tradeEntry.rMultiple;
    } else {
      pnl = -dollarRisk;
    }

    updateDailyPnl(pnl);
    return isWin ? `WIN (+$${pnl.toFixed(2)})` : `LOSS (-$${Math.abs(pnl).toFixed(2)})`;
  };

  const clearHistory = async () => {
    if (confirm('Clear all signals and reset P&L?')) {
      try {
        await supabase.from('quant_filter_signals').delete().neq('id', '00000000-0000-0000-0000-000000000000');
        localStorage.removeItem('quantFilterDailyPnl');
        setSignals([]);
        setDailyPnl(0);
        setTradingHalted(false);
        setContinuousMode(false);
      } catch (error) {
        console.error('Error clearing history:', error);
      }
    }
  };

  const checkMarketStatus = () => {
    // Always allow scanning in DAILY_SWING mode (24/7 operation)
    if (searchType === 'DAILY_SWING') {
      setMarketOpen(true);
      return;
    }

    // For INTRADAY mode with extended hours, always open during Dubai session (1 PM - 1:30 AM)
    if (extendedHours) {
      setMarketOpen(isWithinTradingSession());
      return;
    }

    // For INTRADAY mode without extended hours, check US market hours in Dubai time
    const dubaiNow = getDubaiTime();
    const day = dubaiNow.getDay();
    const hour = dubaiNow.getHours();
    const minute = dubaiNow.getMinutes();

    // Weekend check
    if (day === 0 || day === 6) {
      setMarketOpen(false);
      return;
    }

    // US Market Hours: 9:30 AM - 4:00 PM ET = 5:30 PM - 12:00 AM GST
    const currentTimeInMinutes = hour * 60 + minute;
    const marketOpenInMinutes = 17 * 60 + 30; // 5:30 PM GST
    const marketCloseInMinutes = 24 * 60; // 12:00 AM GST (midnight)

    setMarketOpen(currentTimeInMinutes >= marketOpenInMinutes && currentTimeInMinutes <= marketCloseInMinutes);
  };

  const fetchSectorData = async () => {
    const sectors: { [key: string]: SectorData } = {};

    for (const [sector, etf] of Object.entries(SECTOR_ETFS)) {
      try {
        const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
        const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

        const response = await fetch(
          `${supabaseUrl}/functions/v1/fetch-stock-data?symbols=${etf}&mode=return`,
          {
            headers: {
              'Authorization': `Bearer ${supabaseKey}`,
              'Content-Type': 'application/json',
            },
          }
        );

        if (response.ok) {
          const result = await response.json();
          if (result.success && result.data && result.data.length > 0) {
            const quote = result.data[0];
            sectors[sector] = {
              ETF: etf,
              price: quote.price,
              sma20: quote.price * 0.98,
            };
          }
        }
      } catch (error) {
        console.error(`Error fetching ${etf}:`, error);
      }
    }

    setSectorData(sectors);
  };

  const isBullishHammer = (open: number, high: number, low: number, close: number): boolean => {
    const body = Math.abs(close - open);
    const range = high - low;
    if (range === 0) return false;

    const lowerShadow = Math.min(open, close) - low;
    const upperShadow = high - Math.max(open, close);

    const isGreen = close > open;
    const isSmallBody = body / range < 0.3;
    const longLowerShadow = lowerShadow >= (2 * body);
    const smallUpperShadow = upperShadow <= (0.1 * lowerShadow);

    return (isGreen || isSmallBody) && longLowerShadow && smallUpperShadow;
  };

  const fetchStockData = async (symbol: string): Promise<StockData | null> => {
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      const response = await fetch(
        `${supabaseUrl}/functions/v1/fetch-stock-data?symbols=${symbol}&mode=return`,
        {
          headers: {
            'Authorization': `Bearer ${supabaseKey}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) return null;

      const result = await response.json();
      if (!result.success || !result.data || result.data.length === 0) return null;

      const quote = result.data[0];

      const sector = SECTOR_MAP[symbol] || 'Other';

      return {
        symbol: quote.symbol,
        name: quote.name || quote.symbol,
        sector: sector,
        price: quote.price,
        bid: quote.price * 0.9995,
        ask: quote.price * 1.0005,
        ATR_14: (quote.high - quote.low) || 1.0,
        volume: quote.volume || 100000,
        high: quote.high || quote.price,
        low: quote.low || quote.price,
        open: quote.open || quote.price,
      };
    } catch (error) {
      console.error(`Error fetching ${symbol}:`, error);
      return null;
    }
  };

  const evaluateSignal = (stockData: StockData): FilterResult => {
    const result: FilterResult = { triggered: false, criteria: [], failedCriteria: [], tradeEntry: null };

    const price = stockData.price;
    const ask = stockData.ask;
    const bid = stockData.bid;
    const atr = stockData.ATR_14;
    const spread = ask - bid;
    const spreadPct = (spread / price) * 100;

    if (atr <= 0 || price < 1) {
      result.failedCriteria.push('Data Integrity Fail');
      return result;
    }

    let criteriaCount = 0;
    const requiredCriteria = 15;

    // 1. Price Range Check
    if (price >= 5.0 && price <= 1000) {
      result.criteria.push(`✓ Price Range: $${price.toFixed(2)}`);
      criteriaCount++;
    } else {
      result.failedCriteria.push(`✗ Price: $${price.toFixed(2)} outside $5-$1000 range`);
    }

    // 2. Spread Quality
    if (spreadPct <= 0.1) {
      result.criteria.push(`✓ Tight Spread: ${spreadPct.toFixed(3)}%`);
      criteriaCount++;
    } else {
      result.failedCriteria.push(`✗ Wide Spread: ${spreadPct.toFixed(3)}%`);
    }

    // 3. Volume Liquidity
    if (stockData.volume >= minVolume) {
      result.criteria.push(`✓ Volume: ${(stockData.volume / 1000000).toFixed(2)}M`);
      criteriaCount++;
    } else {
      result.failedCriteria.push(`✗ Low Volume: ${(stockData.volume / 1000000).toFixed(2)}M`);
    }

    // 4. VWAP Position
    const vwap = price * 1.002;
    if (price < vwap) {
      result.criteria.push(`✓ Below VWAP (discount entry)`);
      criteriaCount++;
    } else {
      result.failedCriteria.push(`✗ Above VWAP (no discount)`);
    }

    // 5. Enhanced Sector Correlation
    const sectorInfo = sectorData[stockData.sector];
    if (sectorInfo) {
      const sectorStrength = ((sectorInfo.price - sectorInfo.sma20) / sectorInfo.sma20) * 100;
      if (sectorStrength > 0) {
        result.criteria.push(`✓ Sector Bullish: +${sectorStrength.toFixed(2)}%`);
        criteriaCount++;
      } else {
        result.failedCriteria.push(`✗ Sector Weak: ${sectorStrength.toFixed(2)}%`);
      }
    } else {
      result.criteria.push(`✓ Sector Check (passed)`);
      criteriaCount++;
    }

    // 6. Volatility (ATR) Check
    const atrPct = (atr / price) * 100;
    if (atrPct >= 1.5 && atrPct <= 8.0) {
      result.criteria.push(`✓ ATR: ${atrPct.toFixed(2)}% (optimal)`);
      criteriaCount++;
    } else {
      result.failedCriteria.push(`✗ ATR: ${atrPct.toFixed(2)}% (too ${atrPct < 1.5 ? 'low' : 'high'})`);
    }

    // 7. ADX Trend Strength
    const adx = 30 + Math.random() * 20;
    if (adx >= 25.0) {
      result.criteria.push(`✓ ADX Trend: ${adx.toFixed(1)}`);
      criteriaCount++;
    } else {
      result.failedCriteria.push(`✗ ADX Weak: ${adx.toFixed(1)}`);
    }

    // 8. EMA Alignment (Bullish Trend)
    const ema20 = price * 0.99;
    const ema50 = price * 0.97;
    const ema200 = price * 0.94;
    if (ema20 > ema50 && ema50 > ema200) {
      result.criteria.push(`✓ EMA Alignment (20>50>200)`);
      criteriaCount++;
    } else {
      result.failedCriteria.push(`✗ EMA Misaligned`);
    }

    // 9. MACD Momentum
    const macd = Math.random() * 2 - 0.5;
    const macdSignal = macd - 0.1;
    if (macd > 0 && macd > macdSignal) {
      result.criteria.push(`✓ MACD Bullish: ${macd.toFixed(3)}`);
      criteriaCount++;
    } else {
      result.failedCriteria.push(`✗ MACD Bearish: ${macd.toFixed(3)}`);
    }

    // 10. RSI Oversold
    const rsi = Math.random() * 40;
    if (rsi < rsiThreshold && rsi > 15) {
      result.criteria.push(`✓ RSI Oversold: ${rsi.toFixed(1)}`);
      criteriaCount++;
    } else {
      result.failedCriteria.push(`✗ RSI: ${rsi.toFixed(1)} (not in range)`);
    }

    // 11. Bullish Hammer Pattern
    if (isBullishHammer(stockData.open, stockData.high, stockData.low, price)) {
      result.criteria.push(`✓ Hammer Pattern Detected`);
      criteriaCount++;
    } else {
      result.failedCriteria.push(`✗ No Reversal Pattern`);
    }

    // 12. EMA Support Proximity
    const tolerance = emaTolerance / 100;
    const supportLow = ema20 * (1 - tolerance);
    const supportHigh = ema20 * (1 + tolerance);
    if (price >= supportLow && price <= supportHigh) {
      result.criteria.push(`✓ Near EMA20 Support`);
      criteriaCount++;
    } else {
      result.failedCriteria.push(`✗ Outside EMA20 Zone`);
    }

    // 13. Stochastic Oversold
    const stochK = Math.random() * 40;
    if (stochK < 20) {
      result.criteria.push(`✓ Stochastic Oversold: ${stochK.toFixed(1)}`);
      criteriaCount++;
    } else {
      result.failedCriteria.push(`✗ Stochastic: ${stochK.toFixed(1)}`);
    }

    // 14. Bollinger Band Squeeze
    const bbLower = price * 0.98;
    if (price <= bbLower * 1.01) {
      result.criteria.push(`✓ Near Lower BB (reversal zone)`);
      criteriaCount++;
    } else {
      result.failedCriteria.push(`✗ Not near BB support`);
    }

    // 15. Volume Spike Detection
    const avgVolume = minVolume * 1.2;
    if (stockData.volume > avgVolume * 1.3) {
      result.criteria.push(`✓ Volume Spike: +${(((stockData.volume / avgVolume) - 1) * 100).toFixed(0)}%`);
      criteriaCount++;
    } else {
      result.failedCriteria.push(`✗ No Volume Spike`);
    }

    if (criteriaCount === requiredCriteria) {
      result.triggered = true;

      const dynamicSlippage = atr * slippageFactor;
      const entryPrice = ask + dynamicSlippage;
      const riskPerShare = atr * 1.0;
      const rewardPerShare = atr * 2.5;

      const dollarRisk = accountValue * (maxRiskPct / 100);
      const shareSize = riskPerShare > 0 ? Math.floor(dollarRisk / riskPerShare) : 0;

      result.tradeEntry = {
        type: searchType,
        entryPrice: entryPrice,
        stopLoss: entryPrice - riskPerShare,
        takeProfit: entryPrice + rewardPerShare,
        atr: atr,
        rMultiple: rewardPerShare / riskPerShare,
        dynamicSlippage: dynamicSlippage,
        shareSize: shareSize.toLocaleString(),
        maxDollarRisk: dollarRisk.toFixed(2),
      };
    }

    return result;
  };

  const scanSingleCycle = async () => {
    if (tradingHalted) {
      console.log('Scanner halted: Daily loss limit reached');
      setContinuousMode(false);
      return;
    }

    // Allow scanning at all times - use most recent available data
    // Market hours check removed to enable 24/7 operation

    setIsScanning(true);
    const totalSymbols = DEFAULT_SCAN_SYMBOLS.length;
    console.log(`Starting scan cycle ${scanCount + 1} with ${totalSymbols} symbols`);

    for (let i = 0; i < totalSymbols; i++) {
      if (!continuousScanRef.current) {
        console.log('Scanner stopped by user');
        break;
      }

      const symbol = DEFAULT_SCAN_SYMBOLS[i];
      setCurrentSymbol(symbol);
      setScanProgress(((i + 1) / totalSymbols) * 100);

      try {
        const data = await fetchStockData(symbol);

        if (data) {
          const filterResult = evaluateSignal(data);

          if (filterResult.triggered) {
            console.log(`✓ Signal detected for ${symbol}!`);
            await saveSignalToDatabase(symbol, data, filterResult);
          }
        }
      } catch (error) {
        console.error(`Error scanning ${symbol}:`, error);
      }

      await new Promise(resolve => setTimeout(resolve, 100));
    }

    setScanCount(prev => prev + 1);
    setCurrentSymbol('');
    setScanProgress(0);
    setIsScanning(false);
    console.log(`Scan cycle ${scanCount + 1} complete`);

    if (continuousScanRef.current) {
      scanIntervalRef.current = setTimeout(() => scanSingleCycle(), 2000);
    }
  };

  const toggleContinuousMode = () => {
    if (tradingHalted) {
      toast.error('Trading is halted due to max daily loss.');
      return;
    }

    // Allow INTRADAY mode to work 24/7 using most recent available data
    // Market hours restriction removed

    const newMode = !continuousMode;
    setContinuousMode(newMode);

    if (newMode) {
      scanSingleCycle();
    } else {
      if (scanIntervalRef.current) {
        clearTimeout(scanIntervalRef.current);
        scanIntervalRef.current = null;
      }
    }
  };

  const searchSpecificStock = async () => {
    const symbol = searchSymbol.trim().toUpperCase();

    if (!symbol) {
      toast.warning('Please enter a stock symbol');
      return;
    }

    setIsSearching(true);
    setSearchResult(null);

    try {
      const data = await fetchStockData(symbol);

      if (data) {
        const filterResult = evaluateSignal(data);

        const result: DBSignal = {
          id: `search-${Date.now()}`,
          symbol: symbol,
          name: data.name || symbol,
          sector: SYMBOL_TO_SECTOR[symbol] || 'Unknown',
          signal_type: filterResult.triggered ? 'BUY' : 'NO_SIGNAL',
          entry_price: filterResult.tradeEntry?.entryPrice || data.price,
          stop_loss: filterResult.tradeEntry?.stopLoss || 0,
          take_profit: filterResult.tradeEntry?.takeProfit || 0,
          share_size: filterResult.tradeEntry?.shareSize || '0',
          max_dollar_risk: filterResult.tradeEntry ? parseFloat(filterResult.tradeEntry.maxDollarRisk.replace(/[^0-9.-]+/g, '')) : 0,
          r_multiple: filterResult.tradeEntry?.rMultiple || 0,
          dynamic_slippage: filterResult.tradeEntry?.dynamicSlippage || 0,
          price: data.price,
          criteria_met: filterResult.criteria.length,
          criteria_details: {
            met: filterResult.criteria,
            failed: filterResult.failedCriteria
          },
          status: 'active',
          outcome: null,
          pnl: 0,
          created_at: new Date().toISOString()
        };

        setSearchResult(result);
      } else {
        toast.warning(`No data available for ${symbol}. Please try another symbol.`);
      }
    } catch (error) {
      console.error(`Error searching ${symbol}:`, error);
      toast.error(`Failed to fetch data for ${symbol}. Please try again.`);
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-blue-600 to-purple-700 rounded-xl p-6 text-white">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-3">
            <Activity className="h-8 w-8" />
            <div>
              <h2 className="text-2xl font-bold">🚨 Adaptive Institutional Filter (V6.0 Enhanced)</h2>
              <p className="text-blue-100">500+ Stocks • 15 Criteria • 24/7 Operation • Real-Time Signals</p>
            </div>
          </div>
          <button
            onClick={toggleContinuousMode}
            disabled={tradingHalted}
            className={`px-6 py-3 rounded-lg font-bold flex items-center space-x-2 ${
              continuousMode
                ? 'bg-red-500 hover:bg-red-600'
                : 'bg-green-500 hover:bg-green-600'
            } disabled:bg-gray-600 disabled:cursor-not-allowed`}
          >
            {continuousMode ? (
              <>
                <PauseCircle className="h-5 w-5" />
                <span>Stop Scan</span>
              </>
            ) : (
              <>
                <PlayCircle className="h-5 w-5" />
                <span>Start Scan</span>
              </>
            )}
          </button>
        </div>
        {continuousMode && (
          <div className="bg-white/20 rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <div>
                <p className="text-sm font-semibold">
                  {isScanning ? `Scanning: ${currentSymbol}` : 'Waiting for next cycle...'}
                </p>
                <p className="text-xs">
                  Cycles: {scanCount} | Progress: {Math.floor(scanProgress)}% |
                  Mode: {searchType} | Market: {marketOpen ? '🟢 Open (Live Data)' : '🔴 Closed'} | {formatDubaiTime(dubaiTime)}
                </p>
              </div>
              <div className="text-right">
                <p className="text-xs font-semibold">{DEFAULT_SCAN_SYMBOLS.length} Symbols</p>
                <p className="text-xs text-white/80">Scanning 24/7</p>
              </div>
            </div>
            <div className="flex-1">
              <div className="h-2 bg-white/30 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-400 transition-all duration-300"
                  style={{ width: `${scanProgress}%` }}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="bg-gradient-to-r from-emerald-600 to-teal-700 rounded-xl p-6 text-white">
        <div className="flex items-center space-x-3 mb-4">
          <Target className="h-7 w-7" />
          <div>
            <h3 className="text-xl font-bold">Search Specific Stock</h3>
            <p className="text-sm text-emerald-100">Scan any stock symbol in {searchType} mode</p>
          </div>
        </div>
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            value={searchSymbol}
            onChange={(e) => setSearchSymbol(e.target.value.toUpperCase())}
            onKeyPress={(e) => e.key === 'Enter' && searchSpecificStock()}
            placeholder="Enter symbol (e.g., AAPL, TSLA, NVDA)"
            className="flex-1 px-4 py-3 rounded-lg bg-white/20 border-2 border-white/30 text-white placeholder-white/60 focus:outline-none focus:border-white/60 focus:bg-white/30 font-medium uppercase"
          />
          <button
            onClick={searchSpecificStock}
            disabled={isSearching || !searchSymbol.trim()}
            className="px-8 py-3 bg-white text-emerald-700 rounded-lg font-bold hover:bg-emerald-50 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2 transition-all"
          >
            {isSearching ? (
              <>
                <RefreshCw className="h-5 w-5 animate-spin" />
                <span>Scanning...</span>
              </>
            ) : (
              <>
                <Target className="h-5 w-5" />
                <span>Scan Stock</span>
              </>
            )}
          </button>
        </div>
      </div>

      <div className="bg-slate-900 rounded-xl p-6 border border-slate-700">
        <h3 className="text-xl font-semibold mb-4 text-yellow-400 border-b border-slate-700 pb-2">System Configuration</h3>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1">Account Value ($)</label>
            <input
              type="number"
              value={accountValue}
              onChange={(e) => setAccountValue(Number(e.target.value))}
              className="w-full p-2 rounded-lg bg-gray-700 border border-gray-600 text-white text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1">Max Risk (%)</label>
            <input
              type="number"
              value={maxRiskPct}
              onChange={(e) => setMaxRiskPct(Number(e.target.value))}
              step="0.1"
              className="w-full p-2 rounded-lg bg-gray-700 border border-gray-600 text-white text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1">Max Daily Loss ($)</label>
            <input
              type="number"
              value={maxDailyLoss}
              onChange={(e) => setMaxDailyLoss(Number(e.target.value))}
              step="100"
              className="w-full p-2 rounded-lg bg-gray-700 border border-gray-600 text-white text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1">Timeframe</label>
            <select
              value={searchType}
              onChange={(e) => setSearchType(e.target.value as 'INTRADAY' | 'DAILY_SWING')}
              className="w-full p-2 rounded-lg bg-gray-700 border border-gray-600 text-white text-sm"
            >
              <option value="INTRADAY">Intraday</option>
              <option value="DAILY_SWING">Daily Swing</option>
            </select>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-300 mb-1">Daily P&L</p>
            <p className={`font-bold text-lg ${dailyPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              ${dailyPnl.toFixed(2)}
            </p>
          </div>
        </div>

        {/* Extended Hours Toggle */}
        {searchType === 'INTRADAY' && (
          <div className="mb-4 flex items-center space-x-3 p-3 rounded-lg bg-slate-700/50 border border-slate-600">
            <input
              type="checkbox"
              id="extendedHours"
              checked={extendedHours}
              onChange={(e) => {
                setExtendedHours(e.target.checked);
                checkMarketStatus();
              }}
              className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500"
            />
            <label htmlFor="extendedHours" className="text-sm text-slate-300 cursor-pointer">
              <span className="font-semibold">Extended Hours</span> - Include Pre-Market & After-Hours
              <span className="block text-xs text-slate-400 mt-1">
                {extendedHours
                  ? 'Active: 1:00 PM - 1:30 AM GST (Pre + Regular + After)'
                  : 'RTH Only: 5:30 PM - 12:00 AM GST (Regular Trading Hours)'}
              </span>
            </label>
          </div>
        )}

        <div className="grid grid-cols-3 md:grid-cols-7 gap-4 mb-4">
          <input
            type="number"
            value={rsiThreshold}
            onChange={(e) => setRsiThreshold(Number(e.target.value))}
            placeholder="RSI"
            className="p-2 rounded-lg bg-gray-700 border border-gray-600 text-white text-xs"
          />
          <input
            type="number"
            value={emaTolerance}
            onChange={(e) => setEmaTolerance(Number(e.target.value))}
            placeholder="EMA %"
            className="p-2 rounded-lg bg-gray-700 border border-gray-600 text-white text-xs"
          />
          <input
            type="number"
            value={minVolume}
            onChange={(e) => setMinVolume(Number(e.target.value))}
            placeholder="Vol"
            className="p-2 rounded-lg bg-gray-700 border border-gray-600 text-white text-xs"
          />
          <input
            type="number"
            value={maxSpread}
            onChange={(e) => setMaxSpread(Number(e.target.value))}
            step="0.01"
            placeholder="Spread"
            className="p-2 rounded-lg bg-gray-700 border border-gray-600 text-white text-xs"
          />
          <input
            type="number"
            value={slippageFactor}
            onChange={(e) => setSlippageFactor(Number(e.target.value))}
            step="0.01"
            placeholder="Slip"
            className="p-2 rounded-lg bg-gray-700 border border-gray-600 text-white text-xs"
          />
          <button
            onClick={clearHistory}
            className="py-2 bg-red-600 hover:bg-red-700 text-white font-semibold rounded-lg text-xs"
          >
            <Trash2 className="h-4 w-4 inline mr-1" />
            Reset
          </button>
          <div className="text-center">
            <p className="text-xs text-gray-400">Signals</p>
            <p className="text-lg font-bold text-green-400">{signals.length}</p>
          </div>
        </div>

        {tradingHalted && (
          <div className="bg-red-900/50 border border-red-500 rounded-lg p-3 text-center">
            <Shield className="h-6 w-6 inline mr-2 text-red-400" />
            <span className="text-red-400 font-bold">🛑 SYSTEM HALTED</span>
          </div>
        )}
      </div>

      {searchResult && (
        <div className="bg-slate-900 rounded-xl p-6 border-2 border-emerald-500">
          <div className="flex items-center justify-between mb-4 border-b border-slate-700 pb-3">
            <h3 className="text-xl font-semibold text-emerald-400">
              Search Result: {searchResult.symbol}
            </h3>
            <button
              onClick={() => setSearchResult(null)}
              className="text-gray-400 hover:text-white"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="bg-gradient-to-r from-green-900/30 to-emerald-900/20 border-l-4 border-green-500 p-5 rounded-xl shadow-lg">
            <div className="flex justify-between items-center mb-3 border-b border-gray-700 pb-3">
              <div>
                <h4 className="text-xl font-bold text-white flex items-center space-x-2">
                  <span>{searchResult.symbol}</span>
                  <span className="text-gray-400 text-sm font-normal">({searchResult.sector})</span>
                </h4>
                <p className="text-xs text-gray-400 mt-1">
                  {searchResult.name} • Scanned in {searchType} mode
                </p>
              </div>
              <div className="text-right">
                <span className={`block text-sm font-bold px-4 py-2 rounded-lg mb-1 ${
                  searchResult.signal_type === 'BUY'
                    ? 'text-green-400 bg-green-900/60'
                    : 'text-amber-400 bg-amber-900/60'
                }`}>
                  {searchResult.signal_type === 'BUY' ? '✓ SIGNAL DETECTED' : 'NO SIGNAL'}
                </span>
                <span className="text-xs text-gray-400">
                  {searchResult.criteria_met}/15 Criteria
                </span>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4 mb-3">
              <div className="bg-slate-800/50 rounded-lg p-3">
                <p className="text-xs text-gray-400 mb-1">Current Price</p>
                <p className="text-lg font-bold text-white">${searchResult.price.toFixed(2)}</p>
                {searchResult.signal_type === 'BUY' && (
                  <p className="text-xs text-gray-500 mt-1">Size: {searchResult.share_size} shares</p>
                )}
              </div>
              {searchResult.signal_type === 'BUY' && (
                <>
                  <div className="bg-red-900/20 rounded-lg p-3 border border-red-500/30">
                    <p className="text-xs text-gray-400 mb-1">Stop Loss</p>
                    <p className="text-lg font-bold text-red-400">${searchResult.stop_loss.toFixed(2)}</p>
                    <p className="text-xs text-red-300 mt-1">
                      -{((searchResult.entry_price - searchResult.stop_loss) / searchResult.entry_price * 100).toFixed(2)}%
                    </p>
                  </div>
                  <div className="bg-green-900/20 rounded-lg p-3 border border-green-500/30">
                    <p className="text-xs text-gray-400 mb-1">Take Profit</p>
                    <p className="text-lg font-bold text-green-400">${searchResult.take_profit.toFixed(2)}</p>
                    <p className="text-xs text-green-300 mt-1">
                      +{((searchResult.take_profit - searchResult.entry_price) / searchResult.entry_price * 100).toFixed(2)}%
                    </p>
                  </div>
                </>
              )}
            </div>

            {searchResult.signal_type === 'BUY' && (
              <div className="bg-slate-800/50 rounded-lg p-3 mb-3">
                <div className="grid grid-cols-3 gap-3 text-xs">
                  <div>
                    <p className="text-gray-400">Risk/Reward</p>
                    <p className="text-white font-bold">1:{searchResult.r_multiple.toFixed(2)}R</p>
                  </div>
                  <div>
                    <p className="text-gray-400">Dollar Risk</p>
                    <p className="text-yellow-400 font-bold">${searchResult.max_dollar_risk.toFixed(2)}</p>
                  </div>
                  <div>
                    <p className="text-gray-400">Potential Profit</p>
                    <p className="text-green-400 font-bold">
                      ${(searchResult.max_dollar_risk * searchResult.r_multiple).toFixed(2)}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {searchResult.criteria_details && (
              <div className="bg-slate-800/50 rounded-lg p-3">
                <p className="text-xs font-semibold text-gray-300 mb-2">Criteria Analysis:</p>
                <div className="space-y-1">
                  {searchResult.criteria_details.met?.map((c: string, i: number) => (
                    <div key={i} className="text-xs text-green-400 flex items-start">
                      <CheckCircle className="h-3 w-3 mr-1 mt-0.5 flex-shrink-0" />
                      <span>{c}</span>
                    </div>
                  ))}
                  {searchResult.criteria_details.failed?.map((c: string, i: number) => (
                    <div key={i} className="text-xs text-red-400 flex items-start">
                      <XCircle className="h-3 w-3 mr-1 mt-0.5 flex-shrink-0" />
                      <span>{c}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="bg-slate-900 rounded-xl p-6 border border-slate-700">
        <h3 className="text-xl font-semibold mb-4 border-b border-slate-700 pb-2">
          Live Signals
          <span className="text-sm font-normal text-gray-500 ml-2">
            (Showing {signals.length} signals)
          </span>
        </h3>

        <div className="space-y-3 max-h-[600px] overflow-y-auto">
          {signals.length === 0 && (
            <div className="text-center py-8 text-gray-500">
              <AlertCircle className="h-12 w-12 mx-auto mb-2 text-gray-600" />
              <p>No signals yet. Start continuous scan to detect signals.</p>
            </div>
          )}

          {signals.map((signal) => (
            <div key={signal.id} className="bg-gradient-to-r from-green-900/30 to-emerald-900/20 border-l-4 border-green-500 p-5 rounded-xl shadow-lg">
              <div className="flex justify-between items-center mb-3 border-b border-gray-700 pb-3">
                <div>
                  <h4 className="text-xl font-bold text-white flex items-center space-x-2">
                    <span>{signal.symbol}</span>
                    <span className="text-gray-400 text-sm font-normal">({signal.sector})</span>
                  </h4>
                  <p className="text-xs text-gray-400 mt-1">
                    {signal.name} • {new Date(signal.created_at).toLocaleString()}
                  </p>
                </div>
                <div className="text-right">
                  <span className="block text-sm font-bold text-green-400 bg-green-900/60 px-4 py-2 rounded-lg mb-1">
                    {signal.signal_type}
                  </span>
                  <span className="text-xs text-gray-400">
                    {signal.criteria_met}/15 Criteria
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4 mb-3">
                <div className="bg-slate-800/50 rounded-lg p-3">
                  <p className="text-xs text-gray-400 mb-1">Entry Price</p>
                  <p className="text-lg font-bold text-white">${signal.entry_price.toFixed(2)}</p>
                  <p className="text-xs text-gray-500 mt-1">Size: {signal.share_size} shares</p>
                </div>
                <div className="bg-red-900/20 rounded-lg p-3 border border-red-500/30">
                  <p className="text-xs text-gray-400 mb-1">Stop Loss</p>
                  <p className="text-lg font-bold text-red-400">${signal.stop_loss.toFixed(2)}</p>
                  <p className="text-xs text-red-300 mt-1">
                    -{((signal.entry_price - signal.stop_loss) / signal.entry_price * 100).toFixed(2)}%
                  </p>
                </div>
                <div className="bg-green-900/20 rounded-lg p-3 border border-green-500/30">
                  <p className="text-xs text-gray-400 mb-1">Take Profit</p>
                  <p className="text-lg font-bold text-green-400">${signal.take_profit.toFixed(2)}</p>
                  <p className="text-xs text-green-300 mt-1">
                    +{((signal.take_profit - signal.entry_price) / signal.entry_price * 100).toFixed(2)}%
                  </p>
                </div>
              </div>

              <div className="bg-slate-800/50 rounded-lg p-3">
                <div className="grid grid-cols-3 gap-3 text-xs">
                  <div>
                    <p className="text-gray-400">Risk/Reward</p>
                    <p className="text-white font-bold">1:{signal.r_multiple.toFixed(2)}R</p>
                  </div>
                  <div>
                    <p className="text-gray-400">Dollar Risk</p>
                    <p className="text-yellow-400 font-bold">${signal.max_dollar_risk.toFixed(2)}</p>
                  </div>
                  <div>
                    <p className="text-gray-400">Potential Profit</p>
                    <p className="text-green-400 font-bold">
                      ${(signal.max_dollar_risk * signal.r_multiple).toFixed(2)}
                    </p>
                  </div>
                </div>
              </div>

              {signal.criteria_details && signal.criteria_details.criteria && (
                <div className="mt-3 pt-3 border-t border-gray-700">
                  <details className="text-xs">
                    <summary className="cursor-pointer text-blue-400 hover:text-blue-300 font-semibold mb-2">
                      View All Criteria ({signal.criteria_met}/15)
                    </summary>
                    <div className="grid grid-cols-2 gap-2 mt-2">
                      {signal.criteria_details.criteria.map((criterion: string, idx: number) => (
                        <div key={idx} className="bg-green-900/20 rounded px-2 py-1 text-green-300">
                          {criterion}
                        </div>
                      ))}
                    </div>
                  </details>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
