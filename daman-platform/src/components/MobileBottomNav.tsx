import { Home, TrendingUp, PieChart, Eye, Menu } from 'lucide-react';

interface MobileBottomNavProps {
  currentPage: string;
  onNavigate: (page: string) => void;
  onMenuClick: () => void;
}

export default function MobileBottomNav({ currentPage, onNavigate, onMenuClick }: MobileBottomNavProps) {
  const navItems = [
    { id: 'home', label: 'Home', icon: Home },
    { id: 'market-overview', label: 'Markets', icon: TrendingUp },
    { id: 'portfolio', label: 'Portfolio', icon: PieChart },
    { id: 'watchlist', label: 'Watchlist', icon: Eye },
  ];

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 bg-white dark:bg-slate-800 border-t border-slate-200 dark:border-slate-700 z-50 safe-area-inset-bottom transition-colors duration-200"
      role="navigation"
      aria-label="Mobile navigation"
    >
      <div className="grid grid-cols-5 h-16">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentPage === item.id;

          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`
                flex flex-col items-center justify-center space-y-1 transition-colors
                min-h-[44px] min-w-[44px] p-2
                ${isActive
                  ? 'text-blue-600 bg-blue-50'
                  : 'text-slate-600 hover:text-blue-600 hover:bg-slate-50'
                }
              `}
              aria-label={item.label}
              aria-current={isActive ? 'page' : undefined}
            >
              <Icon className="h-5 w-5" />
              <span className="text-xs font-medium">{item.label}</span>
              {isActive && (
                <div className="absolute top-0 left-0 right-0 h-0.5 bg-blue-600" />
              )}
            </button>
          );
        })}

        <button
          onClick={onMenuClick}
          className="flex flex-col items-center justify-center space-y-1 text-slate-600 hover:text-blue-600 hover:bg-slate-50 transition-colors min-h-[44px] min-w-[44px] p-2"
          aria-label="Open menu"
        >
          <Menu className="h-5 w-5" />
          <span className="text-xs font-medium">More</span>
        </button>
      </div>
    </nav>
  );
}
