import { useEffect, useState } from 'react';
import { useScrollReveal } from '../hooks/useScrollReveal';

interface AnimatedCounterProps {
  /** Target number to count up to. */
  value: number;
  prefix?: string;
  suffix?: string;
  /** Animation duration in ms. */
  duration?: number;
  /** Decimal places to render. */
  decimals?: number;
  className?: string;
}

/**
 * Counts from 0 up to `value` the first time it scrolls into view.
 * Respects reduced-motion by snapping straight to the final value.
 */
export default function AnimatedCounter({
  value,
  prefix = '',
  suffix = '',
  duration = 1500,
  decimals = 0,
  className = '',
}: AnimatedCounterProps) {
  const { ref, visible } = useScrollReveal<HTMLSpanElement>();
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (!visible) return;

    const prefersReduced =
      typeof window !== 'undefined' &&
      window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (prefersReduced) {
      setDisplay(value);
      return;
    }

    let raf = 0;
    let start: number | null = null;
    const step = (ts: number) => {
      if (start === null) start = ts;
      const progress = Math.min((ts - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
      setDisplay(value * eased);
      if (progress < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [visible, value, duration]);

  const formatted = display.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

  return (
    <span ref={ref} className={className}>
      {prefix}
      {formatted}
      {suffix}
    </span>
  );
}
