interface SkeletonProps {
  className?: string;
  /** Render as a circle (e.g. avatar/icon placeholder). */
  circle?: boolean;
}

/**
 * Theme-aware loading placeholder with a subtle shimmer sweep.
 * Uses the brand's slate palette so it blends in light and dark mode.
 */
export default function Skeleton({ className = '', circle = false }: SkeletonProps) {
  return (
    <div
      className={`relative overflow-hidden bg-slate-200 dark:bg-slate-700 ${
        circle ? 'rounded-full' : 'rounded-md'
      } ${className}`}
      aria-hidden="true"
    >
      <div className="absolute inset-0 -translate-x-full animate-[skeletonSweep_1.6s_infinite] bg-gradient-to-r from-transparent via-white/40 dark:via-white/10 to-transparent" />
    </div>
  );
}
