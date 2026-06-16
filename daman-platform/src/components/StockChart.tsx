import { useEffect, useRef, useState } from 'react';
import { TrendingUp, TrendingDown, RefreshCw } from 'lucide-react';

interface StockChartProps {
  symbol: string;
  currentPrice: number;
  change: number;
  percentChange: number;
}

interface ChartDataPoint {
  time: string;
  price: number;
}

export default function StockChart({ symbol, currentPrice, change, percentChange }: StockChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [chartData, setChartData] = useState<ChartDataPoint[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hoveredPoint, setHoveredPoint] = useState<{ price: number; time: string } | null>(null);

  useEffect(() => {
    setIsLoading(true);

    // Generate historical data for the chart (simulated)
    const generateChartData = () => {
      const points: ChartDataPoint[] = [];
      const numPoints = 50;
      let basePrice = currentPrice - change;

      for (let i = 0; i < numPoints; i++) {
        const progress = i / (numPoints - 1);
        const randomWalk = (Math.random() - 0.5) * (Math.abs(change) * 0.3);
        const trendComponent = change * progress;
        const price = basePrice + trendComponent + randomWalk;

        const now = new Date();
        const time = new Date(now.getTime() - (numPoints - i) * 60000);
        const timeStr = time.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

        points.push({ time: timeStr, price });
      }

      return points;
    };

    const data = generateChartData();
    setChartData(data);

    setTimeout(() => setIsLoading(false), 500);
  }, [symbol, currentPrice, change]);

  useEffect(() => {
    if (!canvasRef.current || chartData.length === 0 || isLoading) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;

    ctx.scale(dpr, dpr);
    canvas.style.width = rect.width + 'px';
    canvas.style.height = rect.height + 'px';

    const padding = { top: 20, right: 20, bottom: 40, left: 60 };
    const chartWidth = rect.width - padding.left - padding.right;
    const chartHeight = rect.height - padding.top - padding.bottom;

    const prices = chartData.map(d => d.price);
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const priceRange = maxPrice - minPrice || 1;

    ctx.clearRect(0, 0, rect.width, rect.height);

    // Draw grid lines
    ctx.strokeStyle = '#e2e8f0';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 5; i++) {
      const y = padding.top + (chartHeight / 5) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(padding.left + chartWidth, y);
      ctx.stroke();

      const price = maxPrice - (priceRange / 5) * i;
      ctx.fillStyle = '#64748b';
      ctx.font = '11px system-ui';
      ctx.textAlign = 'right';
      ctx.fillText(`$${price.toFixed(2)}`, padding.left - 8, y + 4);
    }

    // Draw gradient fill
    const gradient = ctx.createLinearGradient(0, padding.top, 0, padding.top + chartHeight);
    if (change >= 0) {
      gradient.addColorStop(0, 'rgba(0, 166, 81, 0.2)');
      gradient.addColorStop(1, 'rgba(0, 166, 81, 0.01)');
    } else {
      gradient.addColorStop(0, 'rgba(220, 20, 60, 0.2)');
      gradient.addColorStop(1, 'rgba(220, 20, 60, 0.01)');
    }

    ctx.beginPath();
    chartData.forEach((point, index) => {
      const x = padding.left + (chartWidth / (chartData.length - 1)) * index;
      const y = padding.top + chartHeight - ((point.price - minPrice) / priceRange) * chartHeight;

      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });

    ctx.lineTo(padding.left + chartWidth, padding.top + chartHeight);
    ctx.lineTo(padding.left, padding.top + chartHeight);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Draw line
    ctx.beginPath();
    chartData.forEach((point, index) => {
      const x = padding.left + (chartWidth / (chartData.length - 1)) * index;
      const y = padding.top + chartHeight - ((point.price - minPrice) / priceRange) * chartHeight;

      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });

    ctx.strokeStyle = change >= 0 ? '#00A651' : '#DC143C';
    ctx.lineWidth = 2.5;
    ctx.stroke();

    // Draw time labels
    const timeLabels = [0, Math.floor(chartData.length / 2), chartData.length - 1];
    ctx.fillStyle = '#64748b';
    ctx.font = '11px system-ui';
    ctx.textAlign = 'center';

    timeLabels.forEach(index => {
      const x = padding.left + (chartWidth / (chartData.length - 1)) * index;
      ctx.fillText(chartData[index].time, x, rect.height - 15);
    });

  }, [chartData, change, isLoading]);

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current || chartData.length === 0) return;

    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;

    const padding = { left: 60, right: 20 };
    const chartWidth = rect.width - padding.left - padding.right;

    if (x >= padding.left && x <= rect.width - padding.right) {
      const index = Math.round(((x - padding.left) / chartWidth) * (chartData.length - 1));
      const point = chartData[index];
      if (point) {
        setHoveredPoint({ price: point.price, time: point.time });
      }
    } else {
      setHoveredPoint(null);
    }
  };

  const handleMouseLeave = () => {
    setHoveredPoint(null);
  };

  return (
    <div className="bg-white rounded-xl shadow-md border border-slate-200 overflow-hidden">
      <div className="p-5 border-b border-slate-200">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center space-x-3">
              <h3 className="text-2xl font-bold text-slate-900">{symbol}</h3>
              <div className={`flex items-center space-x-1 px-3 py-1 rounded-lg ${
                change >= 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
              }`}>
                {change >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                <span className="text-sm font-semibold">
                  {change >= 0 ? '+' : ''}{percentChange.toFixed(2)}%
                </span>
              </div>
            </div>
            <div className="mt-2">
              <span className="text-3xl font-bold" style={{ color: change >= 0 ? '#00A651' : '#DC143C' }}>
                ${hoveredPoint ? hoveredPoint.price.toFixed(2) : currentPrice.toFixed(2)}
              </span>
              <span className="ml-3 text-sm font-semibold" style={{ color: change >= 0 ? '#00A651' : '#DC143C' }}>
                {change >= 0 ? '+' : ''}{change.toFixed(2)}
              </span>
            </div>
            {hoveredPoint && (
              <div className="mt-1 text-xs text-slate-600">
                Time: {hoveredPoint.time}
              </div>
            )}
          </div>
          <div className="text-right">
            <div className="text-xs text-slate-500 uppercase tracking-wide mb-1">Live Updates</div>
            <div className="flex items-center space-x-1 text-green-600">
              <div className="w-2 h-2 bg-green-600 rounded-full animate-pulse"></div>
              <span className="text-xs font-medium">Active</span>
            </div>
          </div>
        </div>
      </div>

      <div className="p-6 bg-slate-50">
        {isLoading ? (
          <div className="flex items-center justify-center" style={{ height: '300px' }}>
            <div className="text-center">
              <RefreshCw className="h-10 w-10 text-daman-blue-600 animate-spin mx-auto mb-3" />
              <p className="text-sm text-slate-600">Loading chart data...</p>
            </div>
          </div>
        ) : (
          <div className="relative">
            <canvas
              ref={canvasRef}
              className="w-full cursor-crosshair"
              style={{ height: '300px' }}
              onMouseMove={handleMouseMove}
              onMouseLeave={handleMouseLeave}
            />
          </div>
        )}
      </div>
    </div>
  );
}
