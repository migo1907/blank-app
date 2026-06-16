import { TrendingUp, TrendingDown } from 'lucide-react';
import { useEffect, useState } from 'react';
import { getTickTextColor, getTickPriceColor } from '../utils/tickColorUtils';

interface MarketMover {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  isGainer: boolean;
}

export default function MarketMoversTicker() {
  const [movers, setMovers] = useState<MarketMover[]>([]);
  const [isPaused, setIsPaused] = useState(false);

  const fetchLiveMovers = async () => {
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      if (!supabaseUrl || !supabaseKey) {
        loadMockMovers();
        return;
      }

      const symbols = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AMD', 'NFLX', 'DIS',
        'PYPL', 'ADBE', 'CRM', 'INTC', 'CSCO', 'ORCL', 'IBM', 'QCOM', 'TXN', 'AVGO',
        'BA', 'GE', 'CAT', 'MMM', 'HON', 'UPS', 'RTX', 'LMT', 'GD', 'NOC'
      ];

      const apiUrl = `${supabaseUrl}/functions/v1/fetch-market-data`;

      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${supabaseKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ symbols }),
      });

      if (!response.ok) {
        loadMockMovers();
        return;
      }

      const result = await response.json();

      if (result.quotes && result.quotes.length > 0) {
        const allMovers: MarketMover[] = result.quotes.map((stock: any) => ({
          symbol: stock.symbol,
          name: stock.symbol,
          price: stock.price || 0,
          change: stock.change || 0,
          changePercent: stock.changePercent || 0,
          isGainer: (stock.changePercent || 0) >= 0,
        }));

        setMovers(allMovers);
      } else {
        loadMockMovers();
      }
    } catch (error) {
      console.error('Error fetching live movers:', error);
      loadMockMovers();
    }
  };

  const loadMockMovers = () => {
    const mockMovers: MarketMover[] = [
      { symbol: 'AAPL', name: 'Apple', price: 182.91, change: 5.67, changePercent: 3.20, isGainer: true },
      { symbol: 'MSFT', name: 'Microsoft', price: 378.91, change: -8.42, changePercent: -2.17, isGainer: false },
      { symbol: 'GOOGL', name: 'Alphabet', price: 138.76, change: 4.32, changePercent: 3.21, isGainer: true },
      { symbol: 'AMZN', name: 'Amazon', price: 145.23, change: 6.89, changePercent: 4.98, isGainer: true },
      { symbol: 'NVDA', name: 'NVIDIA', price: 485.52, change: 18.43, changePercent: 3.95, isGainer: true },
      { symbol: 'META', name: 'Meta', price: 312.45, change: -15.67, changePercent: -4.78, isGainer: false },
      { symbol: 'TSLA', name: 'Tesla', price: 238.45, change: -12.33, changePercent: -4.92, isGainer: false },
      { symbol: 'AMD', name: 'AMD', price: 118.34, change: 7.23, changePercent: 6.51, isGainer: true },
      { symbol: 'NFLX', name: 'Netflix', price: 445.67, change: -18.92, changePercent: -4.07, isGainer: false },
      { symbol: 'DIS', name: 'Disney', price: 89.43, change: 3.21, changePercent: 3.72, isGainer: true },
      { symbol: 'PYPL', name: 'PayPal', price: 62.34, change: 2.45, changePercent: 4.09, isGainer: true },
      { symbol: 'ADBE', name: 'Adobe', price: 548.76, change: -12.34, changePercent: -2.20, isGainer: false },
      { symbol: 'CRM', name: 'Salesforce', price: 234.56, change: 8.91, changePercent: 3.95, isGainer: true },
      { symbol: 'INTC', name: 'Intel', price: 43.21, change: -1.23, changePercent: -2.77, isGainer: false },
      { symbol: 'CSCO', name: 'Cisco', price: 51.34, change: 1.87, changePercent: 3.78, isGainer: true },
      { symbol: 'ORCL', name: 'Oracle', price: 112.45, change: 3.21, changePercent: 2.94, isGainer: true },
      { symbol: 'IBM', name: 'IBM', price: 167.89, change: -2.45, changePercent: -1.44, isGainer: false },
      { symbol: 'QCOM', name: 'Qualcomm', price: 145.67, change: 5.43, changePercent: 3.87, isGainer: true },
      { symbol: 'TXN', name: 'Texas Instruments', price: 178.34, change: 4.56, changePercent: 2.62, isGainer: true },
      { symbol: 'AVGO', name: 'Broadcom', price: 892.45, change: 23.45, changePercent: 2.70, isGainer: true },
      { symbol: 'BA', name: 'Boeing', price: 187.23, change: -5.67, changePercent: -2.94, isGainer: false },
      { symbol: 'GE', name: 'General Electric', price: 112.34, change: 3.45, changePercent: 3.17, isGainer: true },
      { symbol: 'CAT', name: 'Caterpillar', price: 298.76, change: 7.89, changePercent: 2.71, isGainer: true },
      { symbol: 'MMM', name: '3M', price: 98.45, change: -2.34, changePercent: -2.32, isGainer: false },
      { symbol: 'HON', name: 'Honeywell', price: 204.56, change: 4.23, changePercent: 2.11, isGainer: true },
      { symbol: 'UPS', name: 'United Parcel', price: 156.78, change: -3.21, changePercent: -2.01, isGainer: false },
      { symbol: 'RTX', name: 'Raytheon', price: 89.34, change: 2.12, changePercent: 2.43, isGainer: true },
      { symbol: 'LMT', name: 'Lockheed Martin', price: 478.90, change: 8.76, changePercent: 1.86, isGainer: true },
      { symbol: 'GD', name: 'General Dynamics', price: 267.45, change: -4.56, changePercent: -1.68, isGainer: false },
      { symbol: 'NOC', name: 'Northrop Grumman', price: 456.78, change: 9.34, changePercent: 2.09, isGainer: true },
    ];
    setMovers(mockMovers);
  };

  useEffect(() => {
    fetchLiveMovers();

    const interval = setInterval(() => {
      fetchLiveMovers();
    }, 60000);

    return () => clearInterval(interval);
  }, []);

  const duplicatedMovers = [...movers, ...movers];

  return (
    <div
      className="bg-slate-900 border-b border-slate-700 overflow-hidden py-3"
      role="region"
      aria-label="Market Movers Ticker"
    >
      <div className="flex items-center">
        <div className="flex-shrink-0 px-4 bg-slate-800 py-2 border-r border-slate-700">
          <span className="text-white font-semibold text-sm uppercase tracking-wide">Market Movers - Live</span>
        </div>
        <div
          className="flex-1 overflow-hidden"
          onMouseEnter={() => setIsPaused(true)}
          onMouseLeave={() => setIsPaused(false)}
        >
          <div
            className={`flex gap-8 ${isPaused ? '' : 'animate-scroll-left'}`}
            style={{ animationDuration: '30s' }}
          >
            {duplicatedMovers.map((mover, index) => {
              const priceColor = getTickPriceColor(mover.change);
              const textColor = getTickTextColor(mover.change);

              return (
                <div
                  key={`${mover.symbol}-${index}`}
                  className="flex items-center gap-3 flex-shrink-0 px-4 py-2 rounded-lg border border-slate-200 bg-white transition-all duration-300 shadow-md hover:shadow-lg"
                >
                  <span className="text-slate-900 font-bold text-sm">{mover.symbol}</span>
                  <span className="text-base font-extrabold" style={{ color: priceColor }}>
                    ${mover.price.toFixed(2)}
                  </span>
                  <div className="flex items-center gap-1" style={{ color: textColor }}>
                    {mover.isGainer ? (
                      <TrendingUp className="h-4 w-4" aria-hidden="true" />
                    ) : (
                      <TrendingDown className="h-4 w-4" aria-hidden="true" />
                    )}
                    <span className="text-sm font-extrabold">
                      {mover.isGainer ? '+' : ''}{mover.change.toFixed(2)}
                    </span>
                    <span className="text-sm font-bold">
                      ({mover.isGainer ? '+' : ''}{mover.changePercent.toFixed(2)}%)
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <style>{`
        @keyframes scroll-left {
          0% {
            transform: translateX(0);
          }
          100% {
            transform: translateX(-50%);
          }
        }
        .animate-scroll-left {
          animation: scroll-left linear infinite;
        }
      `}</style>
    </div>
  );
}
