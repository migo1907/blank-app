import { ReactNode } from 'react';
import { useScrollReveal } from '../hooks/useScrollReveal';

interface RevealProps {
  children: ReactNode;
  className?: string;
  /** Stagger delay in ms — handy when revealing a list/grid of items. */
  delay?: number;
}

/**
 * Wraps content and fades + slides it into view on scroll.
 * Purely additive: no colors or layout of the children are changed.
 * Honors prefers-reduced-motion via the global CSS rule in index.css.
 */
export default function Reveal({ children, className = '', delay = 0 }: RevealProps) {
  const { ref, visible } = useScrollReveal<HTMLDivElement>();

  return (
    <div
      ref={ref}
      style={{ transitionDelay: `${delay}ms` }}
      className={`transition-all duration-700 ease-out motion-reduce:transition-none ${
        visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'
      } ${className}`}
    >
      {children}
    </div>
  );
}
