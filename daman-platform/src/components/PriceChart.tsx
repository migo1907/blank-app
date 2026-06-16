// Lightweight, dependency-free price chart (SVG). Renders a line + gradient
// area with an optional moving-average overlay. Also exports a deterministic
// series generator so a stock page can show an illustrative chart without a
// historical-data API.

interface PriceChartProps {
  data: number[];
  ma?: number[];
  positive?: boolean;
  height?: number;
  className?: string;
}

/** Deterministic pseudo-random series seeded by a string, ending near `end`. */
export function genSeries(seed: string, points: number, end: number): number[] {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  const rand = () => {
    h = (h * 1664525 + 1013904223) >>> 0;
    return h / 0xffffffff;
  };
  const out: number[] = [];
  let v = end * (0.82 + rand() * 0.12); // start 12-18% below current
  const drift = (end - v) / points;
  for (let i = 0; i < points; i++) {
    v += drift + (rand() - 0.5) * end * 0.018;
    out.push(Math.max(0.01, v));
  }
  out[out.length - 1] = end; // anchor to current price
  return out;
}

/** Simple moving average; leading values null until the window fills. */
export function sma(data: number[], window: number): number[] {
  return data.map((_, i) => {
    if (i < window - 1) return NaN;
    let s = 0;
    for (let j = i - window + 1; j <= i; j++) s += data[j];
    return s / window;
  });
}

/** Wilder-ish RSI over the series (returns the latest value). */
export function rsi(data: number[], window = 14): number {
  if (data.length <= window) return 50;
  let gain = 0, loss = 0;
  for (let i = data.length - window; i < data.length; i++) {
    const d = data[i] - data[i - 1];
    if (d >= 0) gain += d; else loss -= d;
  }
  if (loss === 0) return 100;
  const rs = gain / loss;
  return Math.round(100 - 100 / (1 + rs));
}

function toPath(values: number[], min: number, range: number, h: number): string {
  const n = values.length;
  return values
    .map((v, i) => {
      if (Number.isNaN(v)) return '';
      const x = (i / (n - 1)) * 100;
      const y = h - ((v - min) / range) * h;
      return `${i === 0 || Number.isNaN(values[i - 1]) ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ')
    .trim();
}

export default function PriceChart({ data, ma, positive = true, height = 220, className = '' }: PriceChartProps) {
  if (!data || data.length < 2) return null;
  const all = ma ? data.concat(ma.filter((v) => !Number.isNaN(v))) : data;
  const min = Math.min(...all);
  const max = Math.max(...all);
  const range = max - min || 1;
  const h = 100;

  const line = toPath(data, min, range, h);
  const area = `${line} L100,${h} L0,${h} Z`;
  const maPath = ma ? toPath(ma, min, range, h) : '';
  const color = positive ? '#10b981' : '#f43f5e';
  const lastY = h - ((data[data.length - 1] - min) / range) * h;

  return (
    <div className={className} style={{ height }}>
      <svg viewBox={`0 0 100 ${h}`} preserveAspectRatio="none" width="100%" height="100%">
        <defs>
          <linearGradient id="pc-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.28" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#pc-fill)" />
        {maPath && (
          <path d={maPath} fill="none" stroke="#94a3b8" strokeWidth="1" strokeDasharray="3 2" vectorEffect="non-scaling-stroke" />
        )}
        <path d={line} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        <circle cx="100" cy={lastY} r="2.5" fill={color} vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}
