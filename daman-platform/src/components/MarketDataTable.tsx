import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, RefreshCw } from 'lucide-react';
import { getTickColorClasses, getTickPriceColor } from '../utils/tickColorUtils';
import StockChart from './StockChart';
import { stockDataService } from '../services/stockDataService';

interface Stock {
  symbol: string;
  company: string;
  price: number;
  change: number;
  percentChange: number;
  volume: string;
}

export default function MarketDataTable() {
  const [topGainers, setTopGainers] = useState<Stock[]>([]);
  const [topLosers, setTopLosers] = useState<Stock[]>([]);
  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchLiveStockData = async () => {
    try {
      setIsLoading(true);
      const [gainersData, losersData] = await Promise.all([
        stockDataService.fetchTopGainers(5),
        stockDataService.fetchTopLosers(5),
      ]);

      const formatStock = (stock: any): Stock => ({
        symbol: stock.symbol,
        company: stock.name,
        price: stock.price,
        change: stock.change,
        percentChange: stock.changePercent,
        volume: `${(stock.volume / 1000000).toFixed(1)}M`,
      });

      if (gainersData.length > 0) {
        setTopGainers(gainersData.map(formatStock));
      }
      if (losersData.length > 0) {
        setTopLosers(losersData.map(formatStock));
      }
    } catch (error) {
      console.error('Error fetching live stock data:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchLiveStockData();

    const interval = setInterval(() => {
      fetchLiveStockData();
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  const handleStockClick = (stock: Stock) => {
    setSelectedStock(stock);
  };

  useEffect(() => {
    if (topGainers.length > 0 && !selectedStock) {
      setSelectedStock(topGainers[0]);
    }
  }, [topGainers, selectedStock]);

  useEffect(() => {
    if (!selectedStock) return;

    const updateInterval = setInterval(() => {
      setSelectedStock(prevStock => {
        if (!prevStock) return null;

        const allStocks = [...topGainers, ...topLosers];
        const currentStock = allStocks.find(s => s.symbol === prevStock.symbol);

        return currentStock || prevStock;
      });
    }, 3000);

    return () => clearInterval(updateInterval);
  }, [selectedStock, topGainers, topLosers]);

  const renderTable = (stocks: Stock[], isGainers: boolean) => (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead className="bg-slate-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-slate-600 uppercase tracking-wider">Symbol</th>
            <th className="px-4 py-3 text-right text-xs font-medium text-slate-600 uppercase tracking-wider">Price</th>
            <th className="px-4 py-3 text-right text-xs font-medium text-slate-600 uppercase tracking-wider">Change</th>
            <th className="px-4 py-3 text-right text-xs font-medium text-slate-600 uppercase tracking-wider">% Change</th>
            <th className="px-4 py-3 text-right text-xs font-medium text-slate-600 uppercase tracking-wider">Volume</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200">
          {stocks.map((stock, index) => {
            const tickColors = getTickColorClasses(stock.change);
            const priceColor = getTickPriceColor(stock.change);

            const isSelected = selectedStock?.symbol === stock.symbol;

            return (
              <tr
                key={index}
                className={`transition-all duration-300 cursor-pointer ${
                  isSelected
                    ? 'bg-daman-blue-50 hover:bg-daman-blue-100 border-l-4 border-daman-blue-600'
                    : 'bg-white hover:bg-slate-50'
                }`}
                onClick={() => handleStockClick(stock)}
              >
                <td className="px-4 py-3 whitespace-nowrap">
                  <div className="flex items-center">
                    <div
                      className="w-2.5 h-2.5 rounded-full mr-2 shadow-sm"
                      style={{ backgroundColor: stock.change > 0 ? '#00A651' : '#DC143C' }}
                    ></div>
                    <span className={`font-semibold text-sm ${
                      isSelected ? 'text-daman-blue-900' : 'text-slate-900'
                    }`}>{stock.symbol}</span>
                  </div>
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right">
                  <span className="font-bold text-base" style={{ color: priceColor }}>
                    ${stock.price.toFixed(2)}
                  </span>
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right">
                  <span className="font-extrabold text-sm" style={{ color: priceColor }}>
                    {stock.change > 0 ? '+' : ''}{stock.change.toFixed(2)}
                  </span>
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right">
                  <div className={`inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg font-semibold transition-all ${tickColors.bgDark} ${tickColors.text} ${tickColors.border} border-2`}>
                    {stock.change > 0 ? (
                      <TrendingUp className="h-3.5 w-3.5" />
                    ) : (
                      <TrendingDown className="h-3.5 w-3.5" />
                    )}
                    <span className="text-xs">
                      {stock.change > 0 ? '+' : ''}{stock.percentChange.toFixed(2)}%
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right text-slate-600 text-sm">
                  {stock.volume}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  if (isLoading && topGainers.length === 0) {
    return (
      <div className="flex justify-center items-center py-20">
        <div className="text-center">
          <RefreshCw className="h-12 w-12 text-daman-blue-600 animate-spin mx-auto mb-4" />
          <p className="text-slate-600">Loading live stock data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-white rounded-xl shadow-md border border-slate-200">
        <div className="p-5 border-b border-slate-200">
          <div className="flex items-center space-x-2">
            <TrendingUp className="h-5 w-5 text-daman-blue-600" />
            <h2 className="text-lg font-bold text-slate-900">Top 5 Gainers</h2>
          </div>
          <p className="text-xs text-slate-600 mt-1">Best performing stocks in US markets today</p>
        </div>
        {renderTable(topGainers, true)}
      </div>

      <div className="bg-white rounded-xl shadow-md border border-slate-200">
        <div className="p-5 border-b border-slate-200">
          <div className="flex items-center space-x-2">
            <TrendingDown className="h-5 w-5 text-red-600" />
            <h2 className="text-lg font-bold text-slate-900">Top 5 Losers</h2>
          </div>
          <p className="text-xs text-slate-600 mt-1">Worst performing stocks in US markets today</p>
        </div>
        {renderTable(topLosers, false)}
      </div>
    </div>

    {selectedStock && (
      <div className="mt-6">
        <StockChart
          symbol={selectedStock.symbol}
          currentPrice={selectedStock.price}
          change={selectedStock.change}
          percentChange={selectedStock.percentChange}
        />
      </div>
    )}
    </div>
  );
}
