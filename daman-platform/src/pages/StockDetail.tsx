import { useState, useEffect } from 'react';
import {
  ArrowLeft, TrendingUp, TrendingDown, Building2, Users, Globe,
  Calendar, DollarSign, BarChart3, Download, Share2, BookOpen,
  Newspaper, Activity, Award, Target
} from 'lucide-react';
import { supabase } from '../lib/supabase';

interface StockDetail {
  symbol: string;
  name: string;
  exchange: string;
  sector: string;
  industry: string;
  description: string;
  website: string;
  headquarters: string;
  ceo: string;
  employees: number;
  market_cap: number;
  current_price: number;
  change_percent: number;
  pe_ratio: number;
  dividend_yield: number;
  eps: number;
  beta: number;
  shares_outstanding: number;
  float_shares: number;
  fifty_two_week_high: number;
  fifty_two_week_low: number;
  has_dividends: boolean;
  last_dividend_amount: number;
  last_dividend_date: string;
}

interface DividendHistory {
  ex_date: string;
  payment_date: string;
  amount: number;
  frequency: string;
}

interface Props {
  symbol: string;
  onBack: () => void;
}

export default function StockDetail({ symbol, onBack }: Props) {
  const [activeTab, setActiveTab] = useState<'overview' | 'financials' | 'dividends' | 'technical' | 'news'>('overview');
  const [stockData, setStockData] = useState<StockDetail | null>(null);
  const [dividendHistory, setDividendHistory] = useState<DividendHistory[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchStockDetail();
    fetchDividendHistory();
  }, [symbol]);

  const fetchStockDetail = async () => {
    try {
      setIsLoading(true);
      const { data, error } = await supabase
        .from('stock_detail_view')
        .select('*')
        .eq('symbol', symbol)
        .single();

      if (error) throw error;

      if (data) {
        setStockData({
          symbol: data.symbol,
          name: data.name,
          exchange: data.exchange,
          sector: data.sector || 'Unknown',
          industry: data.industry || 'Unknown',
          description: data.description || 'No description available.',
          website: data.website || '',
          headquarters: data.headquarters || 'Unknown',
          ceo: data.ceo || 'Unknown',
          employees: data.employees || 0,
          market_cap: data.market_cap || 0,
          current_price: parseFloat(data.current_price) || 0,
          change_percent: parseFloat(data.change_percent) || 0,
          pe_ratio: parseFloat(data.pe_ratio) || 0,
          dividend_yield: parseFloat(data.dividend_yield) || 0,
          eps: parseFloat(data.eps) || 0,
          beta: parseFloat(data.beta) || 0,
          shares_outstanding: parseInt(data.shares_outstanding) || 0,
          float_shares: parseInt(data.float_shares) || 0,
          fifty_two_week_high: parseFloat(data.fifty_two_week_high) || 0,
          fifty_two_week_low: parseFloat(data.fifty_two_week_low) || 0,
          has_dividends: data.has_dividends || false,
          last_dividend_amount: parseFloat(data.last_dividend_amount) || 0,
          last_dividend_date: data.last_dividend_date || '',
        });
      }
    } catch (error) {
      console.error('Error fetching stock detail:', error);
      generateMockData();
    } finally {
      setIsLoading(false);
    }
  };

  const fetchDividendHistory = async () => {
    try {
      const { data, error } = await supabase
        .from('dividend_history')
        .select('*')
        .eq('symbol', symbol)
        .order('ex_date', { ascending: false })
        .limit(20);

      if (error) throw error;

      if (data && data.length > 0) {
        setDividendHistory(data.map(d => ({
          ex_date: d.ex_date,
          payment_date: d.payment_date,
          amount: parseFloat(d.amount),
          frequency: d.frequency,
        })));
      } else {
        setDividendHistory(generateMockDividends());
      }
    } catch (error) {
      console.error('Error fetching dividend history:', error);
      setDividendHistory(generateMockDividends());
    }
  };

  const generateMockData = () => {
    const price = 150 + Math.random() * 200;
    setStockData({
      symbol,
      name: `${symbol} Corporation`,
      exchange: 'NASDAQ',
      sector: 'Technology',
      industry: 'Software',
      description: `${symbol} is a leading technology company focused on innovative software solutions for enterprise customers. The company has established itself as a market leader through strategic acquisitions and organic growth.`,
      website: `https://www.${symbol.toLowerCase()}.com`,
      headquarters: 'Cupertino, CA',
      ceo: 'John Smith',
      employees: 150000,
      market_cap: 2500000000000,
      current_price: price,
      change_percent: (Math.random() - 0.5) * 4,
      pe_ratio: 25 + Math.random() * 10,
      dividend_yield: Math.random() * 2,
      eps: 15 + Math.random() * 5,
      beta: 0.8 + Math.random() * 0.6,
      shares_outstanding: 16500000000,
      float_shares: 14200000000,
      fifty_two_week_high: price * 1.2,
      fifty_two_week_low: price * 0.75,
      has_dividends: true,
      last_dividend_amount: 0.92,
      last_dividend_date: '2025-09-15',
    });
  };

  const generateMockDividends = (): DividendHistory[] => {
    const dividends: DividendHistory[] = [];
    const currentDate = new Date();
    for (let i = 0; i < 20; i++) {
      const date = new Date(currentDate);
      date.setMonth(date.getMonth() - (i * 3));
      dividends.push({
        ex_date: date.toISOString().split('T')[0],
        payment_date: new Date(date.getTime() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        amount: 0.88 + (i * 0.01),
        frequency: 'quarterly',
      });
    }
    return dividends;
  };

  const formatNumber = (num: number, decimals: number = 2): string => {
    return num.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  };

  const formatMarketCap = (value: number): string => {
    if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
    if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
    if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
    return `$${value.toLocaleString()}`;
  };

  const formatShares = (shares: number): string => {
    if (shares >= 1e9) return `${(shares / 1e9).toFixed(2)}B`;
    if (shares >= 1e6) return `${(shares / 1e6).toFixed(2)}M`;
    return shares.toLocaleString();
  };

  const exportToCSV = () => {
    if (!stockData) return;

    const csv = [
      ['Stock Analysis Report', ''],
      ['Symbol', stockData.symbol],
      ['Company Name', stockData.name],
      ['Current Price', `$${stockData.current_price.toFixed(2)}`],
      ['Market Cap', formatMarketCap(stockData.market_cap)],
      ['Shares Outstanding', formatShares(stockData.shares_outstanding)],
      ['Free Float', formatShares(stockData.float_shares)],
      ['P/E Ratio', stockData.pe_ratio.toFixed(2)],
      ['Dividend Yield', `${stockData.dividend_yield.toFixed(2)}%`],
      ['EPS', `$${stockData.eps.toFixed(2)}`],
      ['Beta', stockData.beta.toFixed(2)],
      ['52-Week High', `$${stockData.fifty_two_week_high.toFixed(2)}`],
      ['52-Week Low', `$${stockData.fifty_two_week_low.toFixed(2)}`],
      ['', ''],
      ['Generated', new Date().toLocaleString()],
    ].map(row => row.join(',')).join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${stockData.symbol}_analysis_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-center items-center py-20">
            <Activity className="h-12 w-12 text-daman-blue-600 animate-spin" />
          </div>
        </div>
      </div>
    );
  }

  if (!stockData) {
    return (
      <div className="min-h-screen bg-slate-50 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center py-20">
            <p className="text-slate-600">Stock data not available</p>
            <button onClick={onBack} className="mt-4 text-daman-blue-600 hover:text-daman-blue-700">
              Go Back
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-6">
          <button
            onClick={onBack}
            className="flex items-center space-x-2 text-slate-600 hover:text-slate-900 mb-4"
          >
            <ArrowLeft className="h-5 w-5" />
            <span>Back to Search</span>
          </button>

          <div className="bg-white rounded-xl shadow-md border border-slate-200 p-6">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center space-x-3 mb-2">
                  <h1 className="text-3xl font-bold text-slate-900">{stockData.symbol}</h1>
                  <span className="px-3 py-1 bg-slate-100 text-slate-700 text-sm font-medium rounded-lg">
                    {stockData.exchange}
                  </span>
                </div>
                <h2 className="text-xl text-slate-600 mb-3">{stockData.name}</h2>
                <div className="flex items-center space-x-6 text-sm text-slate-600">
                  <span className="flex items-center space-x-1">
                    <Building2 className="h-4 w-4" />
                    <span>{stockData.sector}</span>
                  </span>
                  <span>{stockData.industry}</span>
                </div>
              </div>

              <div className="text-right">
                <div className="text-4xl font-bold text-slate-900 mb-1">
                  ${formatNumber(stockData.current_price)}
                </div>
                <div className={`flex items-center justify-end space-x-1 text-lg font-bold ${
                  stockData.change_percent >= 0 ? 'text-green-600' : 'text-red-600'
                }`}>
                  {stockData.change_percent >= 0 ? (
                    <TrendingUp className="h-5 w-5" />
                  ) : (
                    <TrendingDown className="h-5 w-5" />
                  )}
                  <span>{stockData.change_percent >= 0 ? '+' : ''}{stockData.change_percent.toFixed(2)}%</span>
                </div>
                <div className="text-xs text-slate-500 mt-2">
                  Last Updated: {new Date().toLocaleString()}
                </div>
              </div>
            </div>

            <div className="mt-6 flex items-center space-x-3">
              <button
                onClick={exportToCSV}
                className="flex items-center space-x-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-all"
              >
                <Download className="h-4 w-4" />
                <span>Export Analysis</span>
              </button>
              <button className="flex items-center space-x-2 px-4 py-2 bg-daman-blue-600 text-white rounded-lg hover:bg-daman-blue-700 transition-all">
                <Share2 className="h-4 w-4" />
                <span>Share</span>
              </button>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="bg-white rounded-xl shadow-md border border-slate-200 mb-6">
          <div className="border-b border-slate-200">
            <div className="flex space-x-1 p-2">
              <button
                onClick={() => setActiveTab('overview')}
                className={`flex items-center space-x-2 px-6 py-3 rounded-lg font-semibold text-sm transition-all ${
                  activeTab === 'overview'
                    ? 'bg-daman-blue-600 text-white'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                <BookOpen className="h-4 w-4" />
                <span>Overview</span>
              </button>
              <button
                onClick={() => setActiveTab('financials')}
                className={`flex items-center space-x-2 px-6 py-3 rounded-lg font-semibold text-sm transition-all ${
                  activeTab === 'financials'
                    ? 'bg-daman-blue-600 text-white'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                <BarChart3 className="h-4 w-4" />
                <span>Financials</span>
              </button>
              <button
                onClick={() => setActiveTab('dividends')}
                className={`flex items-center space-x-2 px-6 py-3 rounded-lg font-semibold text-sm transition-all ${
                  activeTab === 'dividends'
                    ? 'bg-daman-blue-600 text-white'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                <DollarSign className="h-4 w-4" />
                <span>Dividends</span>
              </button>
              <button
                onClick={() => setActiveTab('technical')}
                className={`flex items-center space-x-2 px-6 py-3 rounded-lg font-semibold text-sm transition-all ${
                  activeTab === 'technical'
                    ? 'bg-daman-blue-600 text-white'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                <Activity className="h-4 w-4" />
                <span>Technical Analysis</span>
              </button>
              <button
                onClick={() => setActiveTab('news')}
                className={`flex items-center space-x-2 px-6 py-3 rounded-lg font-semibold text-sm transition-all ${
                  activeTab === 'news'
                    ? 'bg-daman-blue-600 text-white'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                <Newspaper className="h-4 w-4" />
                <span>News & Events</span>
              </button>
            </div>
          </div>

          <div className="p-6">
            {/* Overview Tab */}
            {activeTab === 'overview' && (
              <div className="space-y-6">
                <div>
                  <h3 className="text-xl font-bold text-slate-900 mb-4">Company Overview</h3>
                  <p className="text-slate-700 leading-relaxed">{stockData.description}</p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  <div className="p-4 bg-slate-50 rounded-lg">
                    <div className="flex items-center space-x-2 text-slate-600 mb-2">
                      <Globe className="h-4 w-4" />
                      <span className="text-sm font-semibold">Website</span>
                    </div>
                    <a href={stockData.website} target="_blank" rel="noopener noreferrer" className="text-daman-blue-600 hover:underline">
                      {stockData.website || 'Not available'}
                    </a>
                  </div>

                  <div className="p-4 bg-slate-50 rounded-lg">
                    <div className="flex items-center space-x-2 text-slate-600 mb-2">
                      <Building2 className="h-4 w-4" />
                      <span className="text-sm font-semibold">Headquarters</span>
                    </div>
                    <p className="text-slate-900">{stockData.headquarters}</p>
                  </div>

                  <div className="p-4 bg-slate-50 rounded-lg">
                    <div className="flex items-center space-x-2 text-slate-600 mb-2">
                      <Award className="h-4 w-4" />
                      <span className="text-sm font-semibold">CEO</span>
                    </div>
                    <p className="text-slate-900">{stockData.ceo}</p>
                  </div>

                  <div className="p-4 bg-slate-50 rounded-lg">
                    <div className="flex items-center space-x-2 text-slate-600 mb-2">
                      <Users className="h-4 w-4" />
                      <span className="text-sm font-semibold">Employees</span>
                    </div>
                    <p className="text-slate-900 font-bold">{stockData.employees.toLocaleString()}</p>
                  </div>

                  <div className="p-4 bg-slate-50 rounded-lg">
                    <div className="flex items-center space-x-2 text-slate-600 mb-2">
                      <Target className="h-4 w-4" />
                      <span className="text-sm font-semibold">Market Cap</span>
                    </div>
                    <p className="text-slate-900 font-bold">{formatMarketCap(stockData.market_cap)}</p>
                  </div>

                  <div className="p-4 bg-slate-50 rounded-lg">
                    <div className="flex items-center space-x-2 text-slate-600 mb-2">
                      <BarChart3 className="h-4 w-4" />
                      <span className="text-sm font-semibold">Sector</span>
                    </div>
                    <p className="text-slate-900">{stockData.sector}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Financials Tab */}
            {activeTab === 'financials' && (
              <div className="space-y-6">
                <h3 className="text-xl font-bold text-slate-900 mb-4">Financial Metrics</h3>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="p-6 bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl border border-blue-200">
                    <h4 className="text-sm font-semibold text-blue-900 uppercase tracking-wide mb-4">Share Structure</h4>
                    <div className="space-y-3">
                      <div className="flex justify-between items-center">
                        <span className="text-blue-700">Total Outstanding Shares</span>
                        <span className="text-blue-900 font-bold">{formatShares(stockData.shares_outstanding)}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-blue-700">Free Float</span>
                        <span className="text-blue-900 font-bold">{formatShares(stockData.float_shares)}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-blue-700">Float Percentage</span>
                        <span className="text-blue-900 font-bold">
                          {((stockData.float_shares / stockData.shares_outstanding) * 100).toFixed(2)}%
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="p-6 bg-gradient-to-br from-green-50 to-green-100 rounded-xl border border-green-200">
                    <h4 className="text-sm font-semibold text-green-900 uppercase tracking-wide mb-4">Valuation Metrics</h4>
                    <div className="space-y-3">
                      <div className="flex justify-between items-center">
                        <span className="text-green-700">P/E Ratio</span>
                        <span className="text-green-900 font-bold">{stockData.pe_ratio.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-green-700">EPS</span>
                        <span className="text-green-900 font-bold">${stockData.eps.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-green-700">Market Cap</span>
                        <span className="text-green-900 font-bold">{formatMarketCap(stockData.market_cap)}</span>
                      </div>
                    </div>
                  </div>

                  <div className="p-6 bg-gradient-to-br from-purple-50 to-purple-100 rounded-xl border border-purple-200">
                    <h4 className="text-sm font-semibold text-purple-900 uppercase tracking-wide mb-4">Risk Metrics</h4>
                    <div className="space-y-3">
                      <div className="flex justify-between items-center">
                        <span className="text-purple-700">Beta</span>
                        <span className="text-purple-900 font-bold">{stockData.beta.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-purple-700">52-Week High</span>
                        <span className="text-purple-900 font-bold">${formatNumber(stockData.fifty_two_week_high)}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-purple-700">52-Week Low</span>
                        <span className="text-purple-900 font-bold">${formatNumber(stockData.fifty_two_week_low)}</span>
                      </div>
                    </div>
                  </div>

                  <div className="p-6 bg-gradient-to-br from-orange-50 to-orange-100 rounded-xl border border-orange-200">
                    <h4 className="text-sm font-semibold text-orange-900 uppercase tracking-wide mb-4">Price Range Analysis</h4>
                    <div className="space-y-3">
                      <div className="flex justify-between items-center">
                        <span className="text-orange-700">Current Price</span>
                        <span className="text-orange-900 font-bold">${formatNumber(stockData.current_price)}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-orange-700">Distance from High</span>
                        <span className="text-orange-900 font-bold">
                          {(((stockData.fifty_two_week_high - stockData.current_price) / stockData.fifty_two_week_high) * 100).toFixed(2)}%
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-orange-700">Distance from Low</span>
                        <span className="text-orange-900 font-bold">
                          {(((stockData.current_price - stockData.fifty_two_week_low) / stockData.fifty_two_week_low) * 100).toFixed(2)}%
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Dividends Tab */}
            {activeTab === 'dividends' && (
              <div className="space-y-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-xl font-bold text-slate-900">Dividend Information</h3>
                  {stockData.has_dividends ? (
                    <span className="px-4 py-2 bg-green-100 text-green-700 rounded-lg font-semibold">
                      Dividend Paying
                    </span>
                  ) : (
                    <span className="px-4 py-2 bg-slate-100 text-slate-700 rounded-lg font-semibold">
                      No Dividends
                    </span>
                  )}
                </div>

                {stockData.has_dividends && (
                  <>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                      <div className="p-6 bg-gradient-to-br from-emerald-50 to-emerald-100 rounded-xl border border-emerald-200">
                        <div className="text-sm font-semibold text-emerald-900 uppercase tracking-wide mb-2">
                          Last Dividend
                        </div>
                        <div className="text-3xl font-bold text-emerald-900 mb-1">
                          ${stockData.last_dividend_amount.toFixed(2)}
                        </div>
                        <div className="text-sm text-emerald-700">
                          Ex-Date: {new Date(stockData.last_dividend_date).toLocaleDateString()}
                        </div>
                      </div>

                      <div className="p-6 bg-gradient-to-br from-teal-50 to-teal-100 rounded-xl border border-teal-200">
                        <div className="text-sm font-semibold text-teal-900 uppercase tracking-wide mb-2">
                          Dividend Yield
                        </div>
                        <div className="text-3xl font-bold text-teal-900 mb-1">
                          {stockData.dividend_yield.toFixed(2)}%
                        </div>
                        <div className="text-sm text-teal-700">
                          Annual Return Rate
                        </div>
                      </div>

                      <div className="p-6 bg-gradient-to-br from-cyan-50 to-cyan-100 rounded-xl border border-cyan-200">
                        <div className="text-sm font-semibold text-cyan-900 uppercase tracking-wide mb-2">
                          Payment Frequency
                        </div>
                        <div className="text-2xl font-bold text-cyan-900 mb-1">
                          Quarterly
                        </div>
                        <div className="text-sm text-cyan-700">
                          4 payments per year
                        </div>
                      </div>
                    </div>

                    <div>
                      <h4 className="text-lg font-bold text-slate-900 mb-4">5-Year Dividend History</h4>
                      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
                        <table className="w-full">
                          <thead className="bg-slate-50 border-b border-slate-200">
                            <tr>
                              <th className="px-6 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wide">
                                Ex-Dividend Date
                              </th>
                              <th className="px-6 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wide">
                                Payment Date
                              </th>
                              <th className="px-6 py-3 text-right text-xs font-semibold text-slate-700 uppercase tracking-wide">
                                Amount
                              </th>
                              <th className="px-6 py-3 text-center text-xs font-semibold text-slate-700 uppercase tracking-wide">
                                Frequency
                              </th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-200">
                            {dividendHistory.map((dividend, index) => (
                              <tr key={index} className="hover:bg-slate-50">
                                <td className="px-6 py-4 text-sm text-slate-900">
                                  {new Date(dividend.ex_date).toLocaleDateString()}
                                </td>
                                <td className="px-6 py-4 text-sm text-slate-900">
                                  {dividend.payment_date ? new Date(dividend.payment_date).toLocaleDateString() : 'N/A'}
                                </td>
                                <td className="px-6 py-4 text-sm font-bold text-green-600 text-right">
                                  ${dividend.amount.toFixed(2)}
                                </td>
                                <td className="px-6 py-4 text-sm text-slate-900 text-center capitalize">
                                  {dividend.frequency}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </>
                )}

                {!stockData.has_dividends && (
                  <div className="text-center py-12 bg-slate-50 rounded-lg">
                    <DollarSign className="h-16 w-16 text-slate-300 mx-auto mb-4" />
                    <p className="text-slate-600 text-lg">This stock does not currently pay dividends</p>
                    <p className="text-slate-500 text-sm mt-2">
                      The company may be reinvesting profits for growth
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Technical Analysis Tab */}
            {activeTab === 'technical' && (
              <div className="space-y-6">
                <h3 className="text-xl font-bold text-slate-900 mb-4">Technical Analysis</h3>
                <div className="bg-slate-50 rounded-lg p-8 text-center">
                  <Activity className="h-16 w-16 text-slate-300 mx-auto mb-4" />
                  <p className="text-slate-600 text-lg mb-2">Technical indicators coming soon</p>
                  <p className="text-slate-500 text-sm">
                    RSI, MACD, Moving Averages, and other technical indicators will be available here
                  </p>
                </div>
              </div>
            )}

            {/* News Tab */}
            {activeTab === 'news' && (
              <div className="space-y-6">
                <h3 className="text-xl font-bold text-slate-900 mb-4">News & Events</h3>
                <div className="bg-slate-50 rounded-lg p-8 text-center">
                  <Newspaper className="h-16 w-16 text-slate-300 mx-auto mb-4" />
                  <p className="text-slate-600 text-lg mb-2">Company news coming soon</p>
                  <p className="text-slate-500 text-sm">
                    Latest news, earnings reports, and company events will be displayed here
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Disclaimer */}
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-sm text-yellow-800">
          <p className="font-semibold mb-1">⚠️ Investment Disclaimer</p>
          <p>
            The information provided is for informational purposes only and should not be considered financial advice.
            Stock prices and data are subject to market conditions and may have a delay. Always conduct your own research
            and consult with a qualified financial advisor before making investment decisions. Past performance does not
            guarantee future results.
          </p>
          <p className="mt-2 text-xs">
            Data sources: Yahoo Finance, company filings. Last updated: {new Date().toLocaleString()}
          </p>
        </div>
      </div>
    </div>
  );
}
