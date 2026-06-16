import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Activity, DollarSign, BarChart3, RefreshCw } from 'lucide-react';
import MarketDataTable from '../components/MarketDataTable';
import { getTickColorClasses, getTickPriceColor } from '../utils/tickColorUtils';

export default function TradingDashboard() {
  const [lastUpdate, setLastUpdate] = useState(new Date());
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = () => {
    setRefreshing(true);
    setTimeout(() => {
      setLastUpdate(new Date());
      setRefreshing(false);
    }, 1000);
  };

  useEffect(() => {
    const interval = setInterval(() => {
      setLastUpdate(new Date());
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  const portfolioStats = [
    {
      label: 'Portfolio Value',
      value: '$142,567.89',
      change: '+2.34%',
      isPositive: true,
      icon: DollarSign,
    },
    {
      label: 'Today\'s Gain/Loss',
      value: '+$3,245.12',
      change: '+2.34%',
      isPositive: true,
      icon: TrendingUp,
    },
    {
      label: 'Buying Power',
      value: '$87,432.11',
      change: 'Available',
      isPositive: true,
      icon: Activity,
    },
    {
      label: 'Total Return',
      value: '+$22,567.89',
      change: '+18.76%',
      isPositive: true,
      icon: BarChart3,
    },
  ];

  const positions = [
    { symbol: 'AAPL', shares: 150, avgCost: 175.50, currentPrice: 182.30, change: 3.87 },
    { symbol: 'MSFT', shares: 85, avgCost: 340.20, currentPrice: 352.10, change: 3.50 },
    { symbol: 'GOOGL', shares: 50, avgCost: 138.75, currentPrice: 142.90, change: 2.99 },
    { symbol: 'TSLA', shares: 75, avgCost: 245.80, currentPrice: 238.50, change: -2.97 },
    { symbol: 'AMZN', shares: 45, avgCost: 148.30, currentPrice: 153.20, change: 3.30 },
  ];

  const recentOrders = [
    { type: 'BUY', symbol: 'NVDA', shares: 25, price: 485.50, time: '10:23 AM', status: 'Filled' },
    { type: 'SELL', symbol: 'META', shares: 30, price: 312.75, time: '09:45 AM', status: 'Filled' },
    { type: 'BUY', symbol: 'AMD', shares: 100, price: 142.30, time: '09:12 AM', status: 'Filled' },
  ];

  return (
    <div className="min-h-screen bg-slate-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold text-slate-900 mb-2">Trading Dashboard</h1>
            <p className="text-slate-600">
              Last updated: {lastUpdate.toLocaleTimeString()}
            </p>
          </div>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="mt-4 sm:mt-0 flex items-center space-x-2 bg-daman-blue-600 text-white px-4 py-2 rounded-lg hover:bg-daman-blue-700 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            <span>Refresh Data</span>
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {portfolioStats.map((stat, index) => {
            const Icon = stat.icon;
            const changeValue = parseFloat(stat.change.replace(/[^0-9.-]/g, ''));
            const tickColors = getTickColorClasses(changeValue);

            return (
              <div key={index} className="bg-white rounded-xl p-6 shadow-md border border-slate-200 transition-all duration-300 hover:shadow-lg">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-sm font-medium text-slate-600">{stat.label}</span>
                  <div className={`p-2 rounded-lg ${tickColors.bgDark}`}>
                    <Icon className={`h-5 w-5 ${tickColors.textBold}`} />
                  </div>
                </div>
                <div className="text-2xl font-bold text-slate-900 mb-1">{stat.value}</div>
                <div className={`text-sm font-bold ${tickColors.textBold}`}>
                  {stat.change}
                </div>
              </div>
            );
          })}
        </div>

        <div className="mb-8">
          <MarketDataTable />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
          <div className="bg-white rounded-xl shadow-md border border-slate-200">
            <div className="p-6 border-b border-slate-200">
              <h2 className="text-xl font-bold text-slate-900">Current Positions</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-slate-600 uppercase tracking-wider">Symbol</th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-slate-600 uppercase tracking-wider">Shares</th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-slate-600 uppercase tracking-wider">Current</th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-slate-600 uppercase tracking-wider">Change</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {positions.map((position, index) => {
                    const tickColors = getTickColorClasses(position.change);
                    const priceColor = getTickPriceColor(position.change);

                    return (
                      <tr key={index} className="bg-white hover:bg-slate-50 transition-all duration-300">
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="font-semibold text-slate-900">{position.symbol}</div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-slate-700">
                          {position.shares}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right">
                          <div className="font-extrabold text-lg" style={{ color: priceColor }}>
                            ${position.currentPrice.toFixed(2)}
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right">
                          <div className={`inline-flex items-center space-x-1 px-3 py-1.5 rounded-lg font-bold ${tickColors.bgDark} ${tickColors.text} ${tickColors.border} border-2`}>
                            {position.change >= 0 ? (
                              <TrendingUp className="h-4 w-4" />
                            ) : (
                              <TrendingDown className="h-4 w-4" />
                            )}
                            <span>{position.change >= 0 ? '+' : ''}{position.change.toFixed(2)}%</span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-md border border-slate-200">
            <div className="p-6 border-b border-slate-200">
              <h2 className="text-xl font-bold text-slate-900">Recent Orders</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-slate-600 uppercase tracking-wider">Type</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-slate-600 uppercase tracking-wider">Symbol</th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-slate-600 uppercase tracking-wider">Shares</th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-slate-600 uppercase tracking-wider">Price</th>
                    <th className="px-6 py-3 text-center text-xs font-medium text-slate-600 uppercase tracking-wider">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {recentOrders.map((order, index) => (
                    <tr key={index} className="hover:bg-slate-50 transition-colors">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`px-2 py-1 text-xs font-semibold rounded ${
                          order.type === 'BUY' ? 'bg-daman-blue-100 text-daman-blue-700' : 'bg-red-100 text-red-700'
                        }`}>
                          {order.type}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="font-semibold text-slate-900">{order.symbol}</div>
                        <div className="text-xs text-slate-500">{order.time}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-slate-700">
                        {order.shares}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right font-medium text-slate-900">
                        ${order.price.toFixed(2)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-center">
                        <span className="px-2 py-1 text-xs font-semibold rounded bg-daman-blue-100 text-daman-blue-700">
                          {order.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="bg-gradient-to-br from-daman-blue-600 to-daman-blue-700 rounded-xl p-8 text-white">
          <div className="flex flex-col md:flex-row items-center justify-between">
            <div className="mb-4 md:mb-0">
              <h3 className="text-2xl font-bold mb-2">Ready to Place a Trade?</h3>
              <p className="text-white opacity-95">Execute trades instantly with our advanced order types</p>
            </div>
            <button className="bg-white text-daman-blue-700 px-8 py-3 rounded-lg font-semibold hover:bg-slate-100 transition-colors">
              New Order
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
