import { createClient } from 'npm:@supabase/supabase-js@2.57.4';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Client-Info, Apikey',
};

interface NewsAPIArticle {
  title: string;
  description: string;
  content: string;
  url: string;
  source: { id?: string; name: string };
  author: string;
  publishedAt: string;
  urlToImage: string;
}

interface NewsAPIResponse {
  status: string;
  totalResults: number;
  articles: NewsAPIArticle[];
}

const PREMIUM_NEWS_SOURCES = [
  'bloomberg',
  'cnbc',
];

// Breaking news keywords - sourced from Financial Juice (financialjuice.com/home)
// Breaking news marked in red will be displayed for 30 minutes
const BREAKING_NEWS_KEYWORDS = [
  'breaking',
  'just in',
  'alert',
  'urgent',
  'developing',
  'live',
];

const SECTOR_KEYWORDS: Record<string, string[]> = {
  'Technology': ['tech', 'ai', 'artificial intelligence', 'software', 'cloud', 'cyber', 'semiconductor', 'chip', 'apple', 'microsoft', 'google', 'meta', 'amazon'],
  'Healthcare': ['health', 'pharma', 'biotech', 'medical', 'drug', 'vaccine', 'hospital', 'clinical', 'fda'],
  'Finance': ['bank', 'banking', 'loan', 'credit', 'fintech', 'payment', 'jpmorgan', 'goldman', 'morgan stanley'],
  'Energy': ['energy', 'oil', 'gas', 'renewable', 'solar', 'wind', 'exxon', 'chevron', 'electric vehicle', 'ev'],
  'Consumer': ['retail', 'consumer', 'ecommerce', 'walmart', 'target', 'nike', 'starbucks', 'mcdonald'],
  'Automotive': ['auto', 'car', 'vehicle', 'tesla', 'ford', 'gm', 'electric vehicle', 'autonomous'],
  'Real Estate': ['real estate', 'property', 'housing', 'mortgage', 'reit'],
  'Industrials': ['industrial', 'manufacturing', 'aerospace', 'defense', 'boeing', 'construction'],
  'Materials': ['commodity', 'gold', 'silver', 'copper', 'mining', 'steel'],
  'Utilities': ['utility', 'power', 'electricity', 'water', 'infrastructure'],
  'Crypto': ['crypto', 'bitcoin', 'ethereum', 'blockchain', 'defi', 'nft', 'coinbase'],
  'Markets': ['stock market', 'nasdaq', 'dow jones', 's&p 500', 'trading', 'wall street', 'fed', 'interest rate', 'inflation'],
  'Economy': ['economy', 'gdp', 'unemployment', 'jobs', 'recession', 'growth', 'monetary policy', 'fiscal'],
};

const MARKET_QUERIES = [
  'stock market',
  'stocks',
  'nasdaq',
  'dow jones',
  'S&P 500',
  'NYSE',
  'federal reserve',
  'interest rates',
  'earnings',
  'trading',
  'market',
  'shares',
  'equities',
  'wall street',
];

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, {
      status: 200,
      headers: corsHeaders,
    });
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const newsApiKey = Deno.env.get('NEWS_API_KEY');

    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    const url = new URL(req.url);
    const fetchMode = url.searchParams.get('mode') || 'all';
    const sector = url.searchParams.get('sector') || '';
    const pageSize = Math.min(parseInt(url.searchParams.get('pageSize') || '100'), 100);

    let allArticles: NewsAPIArticle[] = [];

    if (!newsApiKey) {
      allArticles = await fetchYahooFinanceNews();
    } else if (newsApiKey) {
      try {
        if (fetchMode === 'breaking' || fetchMode === 'all') {
          const breakingQuery = BREAKING_NEWS_KEYWORDS.slice(0, 3).join(' OR ');
          const marketQuery = MARKET_QUERIES.slice(0, 5).join(' OR ');
          const query = `(${breakingQuery}) AND (${marketQuery})`;

          const newsApiUrl = new URL('https://newsapi.org/v2/everything');
          newsApiUrl.searchParams.set('apiKey', newsApiKey);
          newsApiUrl.searchParams.set('q', query);
          newsApiUrl.searchParams.set('language', 'en');
          newsApiUrl.searchParams.set('sortBy', 'publishedAt');
          newsApiUrl.searchParams.set('pageSize', '20');

          const newsResponse = await fetch(newsApiUrl.toString());
          const newsData: NewsAPIResponse = await newsResponse.json();

          if (newsData.status === 'ok' && newsData.articles) {
            allArticles = allArticles.concat(newsData.articles);
          }
        }

        if (fetchMode === 'headlines' || fetchMode === 'all') {
          for (const source of PREMIUM_NEWS_SOURCES) {
            try {
              const newsApiUrl = new URL('https://newsapi.org/v2/top-headlines');
              newsApiUrl.searchParams.set('apiKey', newsApiKey);
              newsApiUrl.searchParams.set('sources', source);
              newsApiUrl.searchParams.set('pageSize', '10');

              const newsResponse = await fetch(newsApiUrl.toString());
              const newsData: NewsAPIResponse = await newsResponse.json();

              if (newsData.status === 'ok' && newsData.articles) {
                allArticles = allArticles.concat(newsData.articles);
              }
            } catch (sourceError) {
              console.error(`Error fetching from ${source}:`, sourceError);
            }
          }
        }

        if (sector && SECTOR_KEYWORDS[sector]) {
          const sectorQuery = SECTOR_KEYWORDS[sector].slice(0, 5).join(' OR ');
          const newsApiUrl = new URL('https://newsapi.org/v2/everything');
          newsApiUrl.searchParams.set('apiKey', newsApiKey);
          newsApiUrl.searchParams.set('q', sectorQuery);
          newsApiUrl.searchParams.set('language', 'en');
          newsApiUrl.searchParams.set('sortBy', 'publishedAt');
          newsApiUrl.searchParams.set('pageSize', '30');

          const newsResponse = await fetch(newsApiUrl.toString());
          const newsData: NewsAPIResponse = await newsResponse.json();

          if (newsData.status === 'ok' && newsData.articles) {
            allArticles = allArticles.concat(newsData.articles);
          }
        }

        if (fetchMode === 'market' || fetchMode === 'all') {
          const randomQuery = MARKET_QUERIES[Math.floor(Math.random() * MARKET_QUERIES.length)];
          const newsApiUrl = new URL('https://newsapi.org/v2/everything');
          newsApiUrl.searchParams.set('apiKey', newsApiKey);
          newsApiUrl.searchParams.set('q', randomQuery);
          newsApiUrl.searchParams.set('language', 'en');
          newsApiUrl.searchParams.set('sortBy', 'publishedAt');
          newsApiUrl.searchParams.set('pageSize', '30');

          const newsResponse = await fetch(newsApiUrl.toString());
          const newsData: NewsAPIResponse = await newsResponse.json();

          if (newsData.status === 'ok' && newsData.articles) {
            allArticles = allArticles.concat(newsData.articles);
          }
        }
      } catch (apiError) {
        console.error('NewsAPI error:', apiError);
      }
    }

    if (allArticles.length === 0) {
      const query = supabase
        .from('news_articles')
        .select('*')
        .order('published_at', { ascending: false });

      if (sector) {
        query.eq('category', sector);
      }

      const { data: existingArticles } = await query.limit(100);

      return new Response(
        JSON.stringify({
          success: true,
          articles: existingArticles || [],
          source: 'database',
          message: 'Fetched from database cache'
        }),
        {
          status: 200,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        }
      );
    }

    const uniqueArticles = Array.from(
      new Map(allArticles.map(article => [article.url, article])).values()
    );

    const categorizeArticle = (article: NewsAPIArticle): string => {
      const title = article.title.toLowerCase();
      const description = (article.description || '').toLowerCase();
      const text = `${title} ${description}`;

      for (const [sector, keywords] of Object.entries(SECTOR_KEYWORDS)) {
        for (const keyword of keywords) {
          if (text.includes(keyword.toLowerCase())) {
            return sector;
          }
        }
      }

      return 'Markets';
    };

    const isBreakingNews = (article: NewsAPIArticle): boolean => {
      const title = article.title.toLowerCase();
      return BREAKING_NEWS_KEYWORDS.some(keyword => title.includes(keyword));
    };

    const articlesToInsert = uniqueArticles
      .filter(article => article.url && article.title)
      .map(article => {
        const breaking = isBreakingNews(article);
        return {
          title: article.title,
          description: article.description || '',
          content: article.content || '',
          url: article.url,
          source: article.source.name || 'Financial News',
          author: article.author || '',
          published_at: article.publishedAt,
          category: categorizeArticle(article),
          image_url: article.urlToImage || '',
          is_breaking: breaking,
          breaking_news_time: breaking ? new Date().toISOString() : null,
        };
      });

    const { data, error } = await supabase
      .from('news_articles')
      .upsert(articlesToInsert, {
        onConflict: 'url',
        ignoreDuplicates: false
      })
      .select();

    if (error) {
      console.error('Database error:', error);
    }

    const finalQuery = supabase
      .from('news_articles')
      .select('*')
      .order('published_at', { ascending: false });

    if (sector) {
      finalQuery.eq('category', sector);
    }

    const { data: latestArticles } = await finalQuery.limit(150);

    return new Response(
      JSON.stringify({
        success: true,
        articles: latestArticles || [],
        totalResults: uniqueArticles.length,
        articlesProcessed: articlesToInsert.length,
        articlesSaved: data?.length || 0,
        message: 'News articles fetched and saved successfully'
      }),
      {
        status: 200,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );
  } catch (error) {
    console.error('Error in fetch-news function:', error);
    return new Response(
      JSON.stringify({
        error: 'Internal server error',
        message: error instanceof Error ? error.message : 'Unknown error'
      }),
      {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );
  }
});

function isStockMarketRelated(title: string, description: string): boolean {
  const text = `${title} ${description}`.toLowerCase();
  const marketKeywords = [
    'stock', 'market', 'nasdaq', 'dow', 's&p', 'trading', 'shares', 'equity',
    'wall street', 'nyse', 'bull', 'bear', 'rally', 'sell-off', 'investor',
    'earnings', 'ipo', 'merger', 'acquisition', 'fed', 'federal reserve',
    'interest rate', 'inflation', 'portfolio', 'dividend', 'valuation',
    'price target', 'upgrade', 'downgrade', 'analyst', 'outlook'
  ];

  return marketKeywords.some(keyword => text.includes(keyword));
}

function isPreferredSource(sourceName: string): boolean {
  const preferred = ['cnbc', 'bloomberg', 'yahoo finance', 'reuters', 'marketwatch', 'barrons'];
  const lowerSource = sourceName.toLowerCase();
  return preferred.some(source => lowerSource.includes(source));
}

async function fetchYahooFinanceNews(): Promise<NewsAPIArticle[]> {
  try {
    const symbols = ['SPY', 'QQQ', 'DIA', 'IWM', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META'];
    const articles: NewsAPIArticle[] = [];

    for (const symbol of symbols) {
      try {
        const url = `https://query1.finance.yahoo.com/v1/finance/search?q=${symbol}&newsCount=8`;
        const response = await fetch(url, {
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
          },
        });

        if (!response.ok) continue;

        const data = await response.json();

        if (data.news && Array.isArray(data.news)) {
          for (const item of data.news) {
            if (!item.title || !item.link) continue;

            const sourceName = item.publisher || 'Yahoo Finance';
            const title = item.title;
            const description = item.summary || '';

            if (!isStockMarketRelated(title, description)) {
              continue;
            }

            if (!isPreferredSource(sourceName) && Math.random() > 0.3) {
              continue;
            }

            articles.push({
              title: item.title,
              description: item.summary || '',
              content: item.summary || '',
              url: item.link,
              source: { name: sourceName },
              author: item.provider_display_name || '',
              publishedAt: new Date(item.providerPublishTime * 1000).toISOString(),
              urlToImage: item.thumbnail?.resolutions?.[0]?.url || '',
            });
          }
        }
      } catch (symbolError) {
        console.error(`Error fetching news for ${symbol}:`, symbolError);
      }
    }

    const uniqueArticles = Array.from(
      new Map(articles.map(a => [a.url, a])).values()
    );

    const sortedArticles = uniqueArticles.sort((a, b) => {
      const aPreferred = isPreferredSource(a.source.name) ? 1 : 0;
      const bPreferred = isPreferredSource(b.source.name) ? 1 : 0;
      if (aPreferred !== bPreferred) return bPreferred - aPreferred;
      return new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime();
    });

    return sortedArticles.slice(0, 50);
  } catch (error) {
    console.error('Error in fetchYahooFinanceNews:', error);
    return [];
  }
}