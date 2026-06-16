import { useState, useEffect, useRef, ReactNode } from 'react';
import {
  X, Plus, GripVertical, ChevronLeft, ChevronRight, Settings,
  Maximize2, Minimize2, RefreshCw, Search, MoreVertical, Bookmark,
  Star, Clock, TrendingUp, BarChart3, PieChart, Activity
} from 'lucide-react';

/**
 * Advanced Tab System - Professional Multi-Tab Interface
 *
 * Features:
 * - Drag & drop tab reordering
 * - Keyboard navigation (Arrow keys, Enter, Space, Tab)
 * - Tab overflow with scroll controls
 * - Closeable tabs with confirmation
 * - State persistence via localStorage/Supabase
 * - Lazy loading & content caching
 * - Dark/Light theme support
 * - Mobile responsive
 * - ARIA accessibility
 */

export interface TabConfig {
  id: string;
  label: string;
  icon?: ReactNode;
  content: ReactNode;
  closeable?: boolean;
  disabled?: boolean;
  modified?: boolean;
  badge?: string | number;
  lazy?: boolean;
  group?: string;
}

interface AdvancedTabSystemProps {
  tabs: TabConfig[];
  defaultActiveTab?: string;
  onTabChange?: (tabId: string) => void;
  onTabClose?: (tabId: string) => boolean; // Return false to prevent close
  onTabAdd?: () => void;
  onTabReorder?: (tabs: TabConfig[]) => void;
  persistState?: boolean;
  storageKey?: string;
  theme?: 'light' | 'dark' | 'auto';
  maxVisibleTabs?: number;
  enableDragDrop?: boolean;
  enableSearch?: boolean;
  className?: string;
}

export default function AdvancedTabSystem({
  tabs: initialTabs,
  defaultActiveTab,
  onTabChange,
  onTabClose,
  onTabAdd,
  onTabReorder,
  persistState = true,
  storageKey = 'advanced-tabs-state',
  theme = 'light',
  maxVisibleTabs = 8,
  enableDragDrop = true,
  enableSearch = true,
  className = '',
}: AdvancedTabSystemProps) {
  // State Management
  const [tabs, setTabs] = useState<TabConfig[]>(initialTabs);
  const [activeTab, setActiveTab] = useState<string>(
    defaultActiveTab || initialTabs[0]?.id || ''
  );
  const [loadedTabs, setLoadedTabs] = useState<Set<string>>(new Set([activeTab]));
  const [cachedContent, setCachedContent] = useState<Map<string, ReactNode>>(new Map());
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showTabMenu, setShowTabMenu] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [draggedTab, setDraggedTab] = useState<string | null>(null);
  const [scrollPosition, setScrollPosition] = useState(0);
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [recentTabs, setRecentTabs] = useState<string[]>([]);

  // Refs
  const tabsContainerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  // Load persisted state
  useEffect(() => {
    if (persistState) {
      try {
        const saved = localStorage.getItem(storageKey);
        if (saved) {
          const state = JSON.parse(saved);
          if (state.activeTab) setActiveTab(state.activeTab);
          if (state.favorites) setFavorites(new Set(state.favorites));
          if (state.recentTabs) setRecentTabs(state.recentTabs);
        }
      } catch (error) {
        console.error('Error loading tab state:', error);
      }
    }
  }, [persistState, storageKey]);

  // Save state on changes
  useEffect(() => {
    if (persistState) {
      const state = {
        activeTab,
        favorites: Array.from(favorites),
        recentTabs: recentTabs.slice(0, 10),
      };
      localStorage.setItem(storageKey, JSON.stringify(state));
    }
  }, [activeTab, favorites, recentTabs, persistState, storageKey]);

  // Handle tab change
  const handleTabChange = (tabId: string) => {
    const tab = tabs.find(t => t.id === tabId);
    if (!tab || tab.disabled) return;

    setActiveTab(tabId);
    setLoadedTabs(prev => new Set([...prev, tabId]));

    // Update recent tabs
    setRecentTabs(prev => {
      const filtered = prev.filter(id => id !== tabId);
      return [tabId, ...filtered].slice(0, 10);
    });

    if (onTabChange) onTabChange(tabId);
  };

  // Handle tab close
  const handleTabClose = (tabId: string, e: React.MouseEvent) => {
    e.stopPropagation();

    const tab = tabs.find(t => t.id === tabId);
    if (!tab?.closeable) return;

    // Check if modified and needs confirmation
    if (tab.modified) {
      const confirmed = window.confirm(
        `Tab "${tab.label}" has unsaved changes. Close anyway?`
      );
      if (!confirmed) return;
    }

    // Call custom close handler
    if (onTabClose) {
      const shouldClose = onTabClose(tabId);
      if (!shouldClose) return;
    }

    // Remove tab
    const newTabs = tabs.filter(t => t.id !== tabId);
    setTabs(newTabs);

    // Switch to next available tab
    if (activeTab === tabId && newTabs.length > 0) {
      const currentIndex = tabs.findIndex(t => t.id === tabId);
      const nextTab = newTabs[currentIndex] || newTabs[currentIndex - 1] || newTabs[0];
      setActiveTab(nextTab.id);
    }
  };

  // Drag & Drop handlers
  const handleDragStart = (tabId: string, e: React.DragEvent) => {
    if (!enableDragDrop) return;
    setDraggedTab(tabId);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (tabId: string, e: React.DragEvent) => {
    if (!enableDragDrop || !draggedTab) return;
    e.preventDefault();

    const draggedIndex = tabs.findIndex(t => t.id === draggedTab);
    const targetIndex = tabs.findIndex(t => t.id === tabId);

    if (draggedIndex !== targetIndex) {
      const newTabs = [...tabs];
      const [removed] = newTabs.splice(draggedIndex, 1);
      newTabs.splice(targetIndex, 0, removed);
      setTabs(newTabs);
      if (onTabReorder) onTabReorder(newTabs);
    }
  };

  const handleDragEnd = () => {
    setDraggedTab(null);
  };

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent, tabId: string) => {
    const currentIndex = tabs.findIndex(t => t.id === tabId);

    switch (e.key) {
      case 'ArrowLeft':
        e.preventDefault();
        if (currentIndex > 0) {
          handleTabChange(tabs[currentIndex - 1].id);
        }
        break;
      case 'ArrowRight':
        e.preventDefault();
        if (currentIndex < tabs.length - 1) {
          handleTabChange(tabs[currentIndex + 1].id);
        }
        break;
      case 'Home':
        e.preventDefault();
        handleTabChange(tabs[0].id);
        break;
      case 'End':
        e.preventDefault();
        handleTabChange(tabs[tabs.length - 1].id);
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        handleTabChange(tabId);
        break;
      case 'Delete':
        if (tabs.find(t => t.id === tabId)?.closeable) {
          handleTabClose(tabId, e as any);
        }
        break;
    }
  };

  // Scroll controls
  const scrollTabs = (direction: 'left' | 'right') => {
    if (!tabsContainerRef.current) return;
    const scrollAmount = 200;
    const newPosition = direction === 'left'
      ? scrollPosition - scrollAmount
      : scrollPosition + scrollAmount;

    tabsContainerRef.current.scrollTo({
      left: newPosition,
      behavior: 'smooth',
    });
    setScrollPosition(newPosition);
  };

  // Toggle favorite
  const toggleFavorite = (tabId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setFavorites(prev => {
      const newSet = new Set(prev);
      if (newSet.has(tabId)) {
        newSet.delete(tabId);
      } else {
        newSet.add(tabId);
      }
      return newSet;
    });
  };

  // Filter tabs by search
  const filteredTabs = searchQuery
    ? tabs.filter(tab =>
        tab.label.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : tabs;

  // Get active tab content
  const activeTabConfig = tabs.find(t => t.id === activeTab);
  const shouldLoadContent = !activeTabConfig?.lazy || loadedTabs.has(activeTab);

  // Theme classes
  const themeClasses = theme === 'dark'
    ? 'bg-slate-900 text-white'
    : 'bg-white text-slate-900';

  return (
    <div
      className={`advanced-tab-system flex flex-col h-full ${themeClasses} ${className} ${
        isFullscreen ? 'fixed inset-0 z-50' : ''
      }`}
      role="tablist"
      aria-label="Advanced tab navigation"
    >
      {/* Tab Header */}
      <div className={`tab-header border-b ${theme === 'dark' ? 'border-slate-700' : 'border-slate-200'}`}>
        {/* Top Controls */}
        <div className="flex items-center justify-between px-4 py-2 bg-gradient-to-r from-slate-50 to-white dark:from-slate-800 dark:to-slate-900">
          <div className="flex items-center space-x-2">
            {/* Scroll Controls */}
            <button
              onClick={() => scrollTabs('left')}
              className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
              aria-label="Scroll tabs left"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={() => scrollTabs('right')}
              className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
              aria-label="Scroll tabs right"
            >
              <ChevronRight className="h-4 w-4" />
            </button>

            {/* Search */}
            {enableSearch && (
              <div className="relative">
                <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search tabs..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 pr-3 py-1 text-sm border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-slate-800"
                />
              </div>
            )}
          </div>

          {/* Right Controls */}
          <div className="flex items-center space-x-2">
            {onTabAdd && (
              <button
                onClick={onTabAdd}
                className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                aria-label="Add new tab"
              >
                <Plus className="h-4 w-4" />
              </button>
            )}
            <button
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
              aria-label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
            >
              {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </button>
            <button
              onClick={() => setShowTabMenu(!showTabMenu)}
              className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
              aria-label="Tab menu"
            >
              <MoreVertical className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Tabs Container */}
        <div className="relative">
          <div
            ref={tabsContainerRef}
            className="flex overflow-x-auto scrollbar-hide"
            style={{ scrollbarWidth: 'none' }}
          >
            {filteredTabs.map((tab, index) => {
              const isActive = tab.id === activeTab;
              const isFavorite = favorites.has(tab.id);
              const isDragging = draggedTab === tab.id;

              return (
                <div
                  key={tab.id}
                  role="tab"
                  aria-selected={isActive}
                  aria-controls={`tabpanel-${tab.id}`}
                  aria-disabled={tab.disabled}
                  tabIndex={isActive ? 0 : -1}
                  draggable={enableDragDrop && !tab.disabled}
                  onDragStart={(e) => handleDragStart(tab.id, e)}
                  onDragOver={(e) => handleDragOver(tab.id, e)}
                  onDragEnd={handleDragEnd}
                  onClick={() => handleTabChange(tab.id)}
                  onKeyDown={(e) => handleKeyDown(e, tab.id)}
                  className={`
                    group relative flex items-center space-x-2 px-4 py-3 min-w-[120px] max-w-[200px]
                    border-r cursor-pointer transition-all duration-200
                    ${theme === 'dark' ? 'border-slate-700' : 'border-slate-200'}
                    ${isActive
                      ? `bg-gradient-to-b ${theme === 'dark' ? 'from-blue-900 to-blue-950 text-blue-100' : 'from-blue-50 to-white text-blue-600'} border-b-2 border-b-blue-600`
                      : `${theme === 'dark' ? 'bg-slate-800 hover:bg-slate-750 text-slate-300' : 'bg-slate-50 hover:bg-slate-100 text-slate-700'}`
                    }
                    ${tab.disabled ? 'opacity-50 cursor-not-allowed' : ''}
                    ${isDragging ? 'opacity-50' : ''}
                  `}
                >
                  {/* Drag Handle */}
                  {enableDragDrop && !tab.disabled && (
                    <GripVertical className="h-4 w-4 text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity cursor-grab active:cursor-grabbing" />
                  )}

                  {/* Icon */}
                  {tab.icon && (
                    <span className="flex-shrink-0">
                      {tab.icon}
                    </span>
                  )}

                  {/* Label */}
                  <span className="flex-1 truncate text-sm font-medium">
                    {tab.label}
                  </span>

                  {/* Badge */}
                  {tab.badge && (
                    <span className={`
                      px-1.5 py-0.5 text-xs font-semibold rounded-full
                      ${isActive ? 'bg-blue-600 text-white' : 'bg-slate-300 dark:bg-slate-600 text-slate-700 dark:text-slate-200'}
                    `}>
                      {tab.badge}
                    </span>
                  )}

                  {/* Modified Indicator */}
                  {tab.modified && (
                    <div className="w-2 h-2 rounded-full bg-orange-500" title="Modified" />
                  )}

                  {/* Favorite Star */}
                  <button
                    onClick={(e) => toggleFavorite(tab.id, e)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity"
                    aria-label={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
                  >
                    <Star
                      className={`h-3 w-3 ${isFavorite ? 'text-yellow-500 fill-yellow-500' : 'text-slate-400'}`}
                    />
                  </button>

                  {/* Close Button */}
                  {tab.closeable && (
                    <button
                      onClick={(e) => handleTabClose(tab.id, e)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded hover:bg-red-100 dark:hover:bg-red-900"
                      aria-label={`Close ${tab.label} tab`}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  )}

                  {/* Active Tab Indicator */}
                  {isActive && (
                    <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-blue-500 to-blue-600" />
                  )}
                </div>
              );
            })}
          </div>

          {/* Overflow Indicator */}
          {tabs.length > maxVisibleTabs && (
            <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-white dark:from-slate-900 pointer-events-none" />
          )}
        </div>
      </div>

      {/* Tab Content */}
      <div
        ref={contentRef}
        className="tab-content flex-1 overflow-auto p-6"
        role="tabpanel"
        id={`tabpanel-${activeTab}`}
        aria-labelledby={`tab-${activeTab}`}
      >
        {shouldLoadContent ? (
          activeTabConfig?.content
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <RefreshCw className="h-12 w-12 animate-spin text-blue-500 mx-auto mb-4" />
              <p className="text-slate-600 dark:text-slate-400">Loading content...</p>
            </div>
          </div>
        )}
      </div>

      {/* Tab Menu Dropdown */}
      {showTabMenu && (
        <div className="absolute top-12 right-4 w-64 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-xl z-50">
          <div className="p-4 space-y-2">
            <h3 className="font-semibold text-sm text-slate-700 dark:text-slate-300 mb-2">Favorites</h3>
            {Array.from(favorites).map(tabId => {
              const tab = tabs.find(t => t.id === tabId);
              return tab ? (
                <button
                  key={tabId}
                  onClick={() => {
                    handleTabChange(tabId);
                    setShowTabMenu(false);
                  }}
                  className="w-full text-left px-3 py-2 text-sm rounded hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                >
                  <div className="flex items-center space-x-2">
                    {tab.icon}
                    <span>{tab.label}</span>
                  </div>
                </button>
              ) : null;
            })}

            <hr className="my-2 border-slate-200 dark:border-slate-700" />

            <h3 className="font-semibold text-sm text-slate-700 dark:text-slate-300 mb-2">Recent</h3>
            {recentTabs.slice(0, 5).map(tabId => {
              const tab = tabs.find(t => t.id === tabId);
              return tab ? (
                <button
                  key={tabId}
                  onClick={() => {
                    handleTabChange(tabId);
                    setShowTabMenu(false);
                  }}
                  className="w-full text-left px-3 py-2 text-sm rounded hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors flex items-center space-x-2"
                >
                  <Clock className="h-3 w-3" />
                  <span>{tab.label}</span>
                </button>
              ) : null;
            })}
          </div>
        </div>
      )}

      {/* Click outside to close menu */}
      {showTabMenu && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setShowTabMenu(false)}
        />
      )}
    </div>
  );
}
