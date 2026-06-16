import { useEffect, useRef, useMemo } from 'react';

interface MiniSparklineChartProps {
  data: number[];
  color: string;
  width?: number;
  height?: number;
}

export default function MiniSparklineChart({
  data,
  color,
  width = 120,
  height = 40
}: MiniSparklineChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const { min, max } = useMemo(() => {
    const min = Math.min(...data);
    const max = Math.max(...data);
    return { min, max };
  }, [data]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, width, height);

    if (data.length < 2) return;

    const padding = 2;
    const chartWidth = width - padding * 2;
    const chartHeight = height - padding * 2;
    const range = max - min || 1;
    const stepX = chartWidth / (data.length - 1);

    const points = data.map((value, index) => ({
      x: padding + index * stepX,
      y: padding + chartHeight - ((value - min) / range) * chartHeight
    }));

    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);

    for (let i = 1; i < points.length; i++) {
      ctx.lineTo(points[i].x, points[i].y);
    }

    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.stroke();

    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, color + '40');
    gradient.addColorStop(1, color + '00');

    ctx.lineTo(points[points.length - 1].x, height);
    ctx.lineTo(points[0].x, height);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

  }, [data, color, width, height, min, max]);

  return (
    <canvas
      ref={canvasRef}
      className="inline-block"
      aria-label="Price trend sparkline chart"
    />
  );
}
