import { useEffect, useState } from 'react';
import { ArrowUp } from 'lucide-react';

/**
 * Floating "scroll to top" button. Appears after the user scrolls down,
 * hidden otherwise. Uses the brand's daman-blue so it stays on-theme.
 */
export default function BackToTop() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const onScroll = () => setShow(window.scrollY > 500);
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const scrollTop = () =>
    window.scrollTo({ top: 0, behavior: 'smooth' });

  return (
    <button
      onClick={scrollTop}
      aria-label="Back to top"
      className={`fixed bottom-20 md:bottom-6 right-4 md:right-6 z-50 h-12 w-12 rounded-full bg-daman-blue-600 hover:bg-daman-blue-700 text-white shadow-lg flex items-center justify-center transition-all duration-300 hover:-translate-y-1 focus:outline-none focus:ring-2 focus:ring-daman-blue-500 focus:ring-offset-2 ${
        show ? 'opacity-100 translate-y-0 pointer-events-auto' : 'opacity-0 translate-y-3 pointer-events-none'
      }`}
    >
      <ArrowUp className="h-5 w-5" />
    </button>
  );
}
