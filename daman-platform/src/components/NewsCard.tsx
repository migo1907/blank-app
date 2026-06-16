import { Clock, ExternalLink, Zap } from 'lucide-react';

interface NewsCardProps {
  title: string;
  description: string;
  url: string;
  source: string;
  publishedAt: string;
  category: string;
  imageUrl?: string;
  isBreaking?: boolean;
  breakingNewsTime?: string;
}

export default function NewsCard({
  title,
  description,
  url,
  source,
  publishedAt,
  category,
  imageUrl,
  isBreaking = false,
  breakingNewsTime
}: NewsCardProps) {
  // Check if breaking news is within 30 minutes
  const isRecentBreaking = () => {
    if (!isBreaking || !breakingNewsTime) return false;
    const now = Date.now();
    const breakingTime = new Date(breakingNewsTime).getTime();
    const diffMs = now - breakingTime;
    const diffMins = Math.floor(diffMs / 60000);
    return diffMins <= 30; // Show in red for 30 minutes
  };

  const showAsBreaking = isRecentBreaking();

  const getTimeAgo = (dateString: string) => {
    const now = Date.now();
    const publishedDate = new Date(dateString).getTime();
    const diffMs = now - publishedDate;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);

    if (diffMins < 60) {
      return `${diffMins}m ago`;
    } else if (diffHours < 24) {
      return `${diffHours}h ago`;
    } else {
      return new Date(publishedDate).toLocaleDateString();
    }
  };

  const getSourceBadge = (source: string) => {
    const sourceMap: Record<string, { initials: string; bg: string; text: string }> = {
      'CNBC': { initials: 'CN', bg: 'bg-red-100', text: 'text-red-600' },
      'Bloomberg': { initials: 'BB', bg: 'bg-amber-100', text: 'text-amber-700' },
      'Reuters': { initials: 'RT', bg: 'bg-orange-100', text: 'text-orange-600' },
      'The Wall Street Journal': { initials: 'WSJ', bg: 'bg-slate-100', text: 'text-slate-700' },
      'Financial Times': { initials: 'FT', bg: 'bg-pink-100', text: 'text-pink-700' },
      'Associated Press': { initials: 'AP', bg: 'bg-blue-100', text: 'text-blue-600' },
      'MarketWatch': { initials: 'MW', bg: 'bg-green-100', text: 'text-green-700' },
      'TechCrunch': { initials: 'TC', bg: 'bg-green-100', text: 'text-green-600' },
      'Fortune': { initials: 'FT', bg: 'bg-purple-100', text: 'text-purple-600' },
    };

    return sourceMap[source] || { initials: source.substring(0, 2).toUpperCase(), bg: 'bg-slate-100', text: 'text-slate-600' };
  };

  const sourceBadge = getSourceBadge(source);
  const timeAgo = getTimeAgo(publishedAt);

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className={`bg-white rounded-xl shadow-md border overflow-hidden hover:shadow-xl transition-all duration-200 transform hover:-translate-y-1 group will-change-transform ${
        showAsBreaking ? 'border-red-500 border-2 ring-2 ring-red-200 bg-red-50' : 'border-slate-200'
      }`}
    >
      {imageUrl && (
        <div className="relative h-48 overflow-hidden">
          <img
            src={imageUrl}
            alt={title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            onError={(e) => {
              e.currentTarget.style.display = 'none';
            }}
          />
          {showAsBreaking && (
            <div className="absolute top-2 left-2 bg-red-600 text-white px-3 py-1 rounded-full flex items-center space-x-1 font-bold text-xs shadow-lg">
              <Zap className="h-3 w-3 animate-pulse" />
              <span>BREAKING</span>
            </div>
          )}
        </div>
      )}

      <div className="p-6">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center space-x-2">
            <span className={`px-3 py-1 text-xs font-semibold rounded-full ${
              showAsBreaking ? 'bg-red-100 text-red-800' : 'bg-daman-blue-100 text-daman-blue-800'
            }`}>
              {category}
            </span>
            {showAsBreaking && !imageUrl && (
              <span className="px-2 py-1 bg-red-600 text-white text-xs font-bold rounded flex items-center space-x-1">
                <Zap className="h-3 w-3" />
                <span>BREAKING</span>
              </span>
            )}
          </div>
          <div className="flex items-center text-xs text-slate-600">
            <Clock className="h-3 w-3 mr-1" />
            {timeAgo}
          </div>
        </div>

        <h3 className="text-lg font-bold text-slate-900 mb-3 group-hover:text-daman-blue-700 transition-colors line-clamp-2">
          {title}
        </h3>

        <p className="text-slate-700 text-sm mb-4 line-clamp-3">
          {description}
        </p>

        <div className="flex items-center justify-between pt-4 border-t border-slate-200">
          <div className="flex items-center space-x-2">
            <div className={`w-8 h-8 ${sourceBadge.bg} rounded-full flex items-center justify-center`}>
              <span className={`${sourceBadge.text} font-bold text-xs`}>{sourceBadge.initials}</span>
            </div>
            <span className="text-sm font-medium text-slate-700">{source}</span>
          </div>
          <ExternalLink className="h-4 w-4 text-slate-400 group-hover:text-daman-blue-700 transition-colors" />
        </div>
      </div>
    </a>
  );
}
