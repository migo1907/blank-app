import { Newspaper } from 'lucide-react';
import { useEffect, useState, useMemo } from 'react';
import { supabase } from '../lib/supabase';

interface NewsItem {
  id: string;
  source: string;
  headline: string;
  url: string;
  time: string;
  published_at?: string;
}

export default function NewsTicker() {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [isPaused, setIsPaused] = useState(false);

  const initialNews: NewsItem[] = useMemo(() => [
    {
      id: '1',
      source: 'CNBC',
      headline: 'Federal Reserve signals pause in rate hikes as inflation cools',
      url: 'https://www.cnbc.com/economy/',
      time: '15m ago'
    },
    {
      id: '2',
      source: 'CNBC',
      headline: 'Tech stocks rally as earnings exceed Wall Street expectations',
      url: 'https://www.cnbc.com/technology/',
      time: '28m ago'
    },
    {
      id: '3',
      source: 'CNBC',
      headline: 'Oil prices surge on Middle East supply concerns',
      url: 'https://www.cnbc.com/energy/',
      time: '42m ago'
    },
    {
      id: '4',
      source: 'CNBC',
      headline: 'Dollar strengthens against major currencies on economic data',
      url: 'https://www.cnbc.com/markets/',
      time: '1h ago'
    },
    {
      id: '5',
      source: 'CNBC',
      headline: 'Major merger announcement shakes healthcare sector',
      url: 'https://www.cnbc.com/healthcare/',
      time: '1h ago'
    },
    {
      id: '6',
      source: 'CNBC',
      headline: 'European markets climb on positive GDP growth figures',
      url: 'https://www.cnbc.com/world-markets/',
      time: '2h ago'
    },
    {
      id: '7',
      source: 'CNBC',
      headline: 'Semiconductor shortage easing as production ramps up globally',
      url: 'https://www.cnbc.com/technology/',
      time: '2h ago'
    },
    {
      id: '8',
      source: 'CNBC',
      headline: 'Treasury yields fall amid flight to safety',
      url: 'https://www.cnbc.com/bonds/',
      time: '3h ago'
    },
    {
      id: '9',
      source: 'CNBC',
      headline: 'Consumer confidence index reaches highest level in 18 months',
      url: 'https://www.cnbc.com/consumer/',
      time: '3h ago'
    },
    {
      id: '10',
      source: 'CNBC',
      headline: 'Crypto markets surge as institutional adoption accelerates',
      url: 'https://www.cnbc.com/cryptocurrency/',
      time: '4h ago'
    },
    {
      id: '11',
      source: 'CNBC',
      headline: 'Retail sales data surprises to upside as consumer spending remains robust',
      url: 'https://www.cnbc.com/retail/',
      time: '4h ago'
    },
    {
      id: '12',
      source: 'CNBC',
      headline: 'Wall Street analysts upgrade multiple tech giants ahead of earnings',
      url: 'https://www.cnbc.com/investing/',
      time: '5h ago'
    }
  ], []);

  const fetchLiveNews = async () => {
    try {
      // First, try to fetch fresh news via the edge function
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      if (supabaseUrl && supabaseKey) {
        try {
          const response = await fetch(`${supabaseUrl}/functions/v1/fetch-news?mode=headlines&pageSize=30`, {
            headers: {
              'Authorization': `Bearer ${supabaseKey}`,
              'Content-Type': 'application/json',
            },
          });

          if (response.ok) {
            const result = await response.json();
            if (result.success && result.articles && result.articles.length > 0) {
              // News was just fetched, wait a moment and then query the database
              await new Promise(resolve => setTimeout(resolve, 1000));
            }
          }
        } catch (fetchError) {
          console.error('Error triggering news fetch:', fetchError);
        }
      }

      // Now fetch from database (should have fresh data)
      const oneDayAgo = new Date();
      oneDayAgo.setDate(oneDayAgo.getDate() - 1);

      const { data, error } = await supabase
        .from('news_articles')
        .select('id, title, url, source, published_at, is_breaking')
        .gte('published_at', oneDayAgo.toISOString())
        .order('published_at', { ascending: false })
        .limit(50);

      if (error) {
        console.error('Error fetching news:', error);
        setNews(initialNews);
        return;
      }

      if (!data || data.length === 0) {
        setNews(initialNews);
        return;
      }

      if (data && data.length > 0) {
        // Filter for major financial news sources
        const financialNews = data.filter((article: any) => {
          const source = (article.source || '').toLowerCase();
          return source.includes('cnbc') ||
                 source.includes('bloomberg') ||
                 source.includes('reuters') ||
                 source.includes('wall street') ||
                 source.includes('wsj') ||
                 source.includes('financial times') ||
                 source.includes('marketwatch') ||
                 source.includes('seeking alpha');
        });

        // Get top 20 latest financial news articles for variety
        const articlesToUse = financialNews.slice(0, 20);

        if (articlesToUse.length === 0) {
          setNews(initialNews);
          return;
        }

        const formattedNews: NewsItem[] = articlesToUse.map((article: any) => {
          const publishedDate = new Date(article.published_at);
          const now = new Date();
          const diffMs = now.getTime() - publishedDate.getTime();
          const diffMins = Math.floor(diffMs / 60000);

          let timeAgo: string;
          if (diffMins < 1) timeAgo = 'Just now';
          else if (diffMins < 60) timeAgo = `${diffMins}m ago`;
          else if (diffMins < 1440) timeAgo = `${Math.floor(diffMins / 60)}h ago`;
          else timeAgo = `${Math.floor(diffMins / 1440)}d ago`;

          return {
            id: article.id.toString(),
            source: article.source || 'Financial News',
            headline: article.title,
            url: article.url,
            time: timeAgo,
            published_at: article.published_at,
          };
        });

        setNews(formattedNews);
      } else {
        setNews(initialNews);
      }
    } catch (error) {
      console.error('Error in fetchLiveNews:', error);
      setNews(initialNews);
    }
  };

  useEffect(() => {
    fetchLiveNews();

    // Refresh every 5 minutes for fresh headlines
    const interval = setInterval(() => {
      fetchLiveNews();
    }, 300000);

    return () => clearInterval(interval);
  }, [initialNews]);

  const duplicatedNews = useMemo(() => [...news, ...news], [news]);

  return (
    <div
      className="bg-daman-blue-900 border-b border-daman-blue-800 overflow-hidden py-3"
      role="region"
      aria-label="News Headlines Ticker"
    >
      <div className="flex items-center">
        <div className="flex-shrink-0 px-4 bg-daman-blue-800 py-2 border-r border-daman-blue-700 flex items-center gap-2">
          <Newspaper className="h-4 w-4 text-white" aria-hidden="true" />
          <span className="text-white font-semibold text-sm uppercase tracking-wide">Market News</span>
        </div>
        <div
          className="flex-1 overflow-hidden"
          onMouseEnter={() => setIsPaused(true)}
          onMouseLeave={() => setIsPaused(false)}
        >
          <div
            className={`flex gap-0 ${isPaused ? '' : 'animate-scroll-left'}`}
            style={{ animationDuration: '20s' }}
          >
            {duplicatedNews.map((item, index) => (
              <a
                key={`${item.id}-${index}`}
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 flex-shrink-0 px-6 py-1 hover:bg-daman-blue-800/50 transition-colors focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-daman-blue-900"
                tabIndex={0}
                onClick={(e) => {
                  try {
                    if (!item.url || item.url === '#') {
                      e.preventDefault();
                      console.warn('Invalid news URL:', item.url);
                    }
                  } catch (error) {
                    console.error('Error opening news link:', error);
                  }
                }}
              >
                <span className="font-bold text-xs px-2 py-1 rounded bg-red-600 text-white">
                  {item.source}
                </span>
                <span className="text-white text-sm">{item.headline}</span>
                <span className="text-daman-blue-200 text-xs flex-shrink-0 font-medium">{item.time}</span>
              </a>
            ))}
          </div>
        </div>
      </div>
      <style>{`
        @keyframes scroll-left {
          0% {
            transform: translateX(0);
          }
          100% {
            transform: translateX(-50%);
          }
        }
        .animate-scroll-left {
          animation: scroll-left linear infinite;
        }
      `}</style>
    </div>
  );
}
