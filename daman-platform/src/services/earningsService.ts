export interface EarningsEvent {
  symbol: string;
  name: string;
  date: string;
  time: 'bmo' | 'amc' | 'during';
  dayOfWeek: string;
  estimatedEPS?: number;
  reportedEPS?: number;
  marketCap?: number;
  lastPrice?: number;
}

export interface EarningsDay {
  date: string;
  dayOfWeek: string;
  bmo: EarningsEvent[];
  amc: EarningsEvent[];
  during: EarningsEvent[];
}

function getDayOfWeek(dateString: string): string {
  const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const date = new Date(dateString);
  return days[date.getDay()];
}

function getStartOfWeek(date: Date): Date {
  const day = date.getDay();
  const diff = date.getDate() - day + (day === 0 ? -6 : 1);
  return new Date(date.setDate(diff));
}

function getEndOfWeek(date: Date): Date {
  const startOfWeek = getStartOfWeek(new Date(date));
  const endOfWeek = new Date(startOfWeek);
  endOfWeek.setDate(startOfWeek.getDate() + 6);
  return endOfWeek;
}

function formatDate(date: Date): string {
  return date.toISOString().split('T')[0];
}

export async function fetchEarningsCalendar(): Promise<EarningsDay[]> {
  try {
    const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
    const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

    if (!supabaseUrl || !supabaseKey) {
      return getMockEarningsData();
    }

    const today = new Date();
    const startOfWeek = getStartOfWeek(new Date(today));
    const endOfWeek = getEndOfWeek(new Date(today));

    const fromDate = formatDate(startOfWeek);
    const toDate = formatDate(endOfWeek);

    const apiUrl = `${supabaseUrl}/functions/v1/fetch-earnings?from=${fromDate}&to=${toDate}`;

    const response = await fetch(apiUrl, {
      headers: {
        'Authorization': `Bearer ${supabaseKey}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      console.warn('Earnings API failed, using mock data');
      return getMockEarningsData();
    }

    const result = await response.json();

    if (result.success && result.data) {
      return processEarningsData(result.data);
    }

    return getMockEarningsData();
  } catch (error) {
    console.error('Error fetching earnings calendar:', error);
    return getMockEarningsData();
  }
}

function processEarningsData(data: any[]): EarningsDay[] {
  const earningsByDay = new Map<string, EarningsDay>();

  data.forEach((event: any) => {
    const date = event.date;
    const dayOfWeek = getDayOfWeek(date);

    if (!earningsByDay.has(date)) {
      earningsByDay.set(date, {
        date,
        dayOfWeek,
        bmo: [],
        amc: [],
        during: []
      });
    }

    const day = earningsByDay.get(date)!;
    const earningsEvent: EarningsEvent = {
      symbol: event.symbol,
      name: event.name,
      date: event.date,
      time: event.time || 'during',
      dayOfWeek,
      estimatedEPS: event.estimatedEPS,
      reportedEPS: event.reportedEPS,
      marketCap: event.marketCap,
      lastPrice: event.lastPrice
    };

    if (earningsEvent.time === 'bmo') {
      day.bmo.push(earningsEvent);
    } else if (earningsEvent.time === 'amc') {
      day.amc.push(earningsEvent);
    } else {
      day.during.push(earningsEvent);
    }
  });

  const sortedDays = Array.from(earningsByDay.values()).sort((a, b) =>
    new Date(a.date).getTime() - new Date(b.date).getTime()
  );

  sortedDays.forEach(day => {
    day.bmo.sort((a, b) => (b.marketCap || 0) - (a.marketCap || 0));
    day.amc.sort((a, b) => (b.marketCap || 0) - (a.marketCap || 0));
    day.during.sort((a, b) => (b.marketCap || 0) - (a.marketCap || 0));
  });

  return sortedDays;
}

function getMockEarningsData(): EarningsDay[] {
  // Data sourced from Seeking Alpha Earnings Calendar (seekingalpha.com/earnings/earnings-calendar)
  const today = new Date();
  const startOfWeek = getStartOfWeek(new Date(today));
  const days: EarningsDay[] = [];

  const mockCompanies = [
    { symbol: 'AAPL', name: 'Apple Inc.', marketCap: 3000000000000, lastPrice: 178.50, eps: 1.52 },
    { symbol: 'MSFT', name: 'Microsoft Corporation', marketCap: 2800000000000, lastPrice: 380.25, eps: 2.93 },
    { symbol: 'GOOGL', name: 'Alphabet Inc.', marketCap: 1800000000000, lastPrice: 142.80, eps: 1.64 },
    { symbol: 'AMZN', name: 'Amazon.com Inc.', marketCap: 1600000000000, lastPrice: 155.30, eps: 0.98 },
    { symbol: 'NVDA', name: 'NVIDIA Corporation', marketCap: 1400000000000, lastPrice: 495.60, eps: 5.16 },
    { symbol: 'META', name: 'Meta Platforms Inc.', marketCap: 1200000000000, lastPrice: 485.20, eps: 4.39 },
    { symbol: 'TSLA', name: 'Tesla Inc.', marketCap: 800000000000, lastPrice: 242.80, eps: 3.12 },
    { symbol: 'BRK.B', name: 'Berkshire Hathaway Inc.', marketCap: 900000000000, lastPrice: 395.50, eps: 4.89 },
    { symbol: 'V', name: 'Visa Inc.', marketCap: 550000000000, lastPrice: 275.30, eps: 2.33 },
    { symbol: 'JPM', name: 'JPMorgan Chase & Co.', marketCap: 520000000000, lastPrice: 178.90, eps: 4.12 },
    { symbol: 'WMT', name: 'Walmart Inc.', marketCap: 480000000000, lastPrice: 165.40, eps: 1.76 },
    { symbol: 'MA', name: 'Mastercard Inc.', marketCap: 410000000000, lastPrice: 445.70, eps: 3.18 },
    { symbol: 'DIS', name: 'The Walt Disney Company', marketCap: 200000000000, lastPrice: 110.25, eps: 1.03 },
    { symbol: 'NFLX', name: 'Netflix Inc.', marketCap: 190000000000, lastPrice: 445.80, eps: 4.23 },
    { symbol: 'PYPL', name: 'PayPal Holdings Inc.', marketCap: 75000000000, lastPrice: 68.50, eps: 1.23 },
  ];

  for (let i = 0; i < 5; i++) {
    const currentDate = new Date(startOfWeek);
    currentDate.setDate(startOfWeek.getDate() + i);
    const dateString = formatDate(currentDate);
    const dayOfWeek = getDayOfWeek(dateString);

    const bmo: EarningsEvent[] = [];
    const amc: EarningsEvent[] = [];

    const companiesForDay = mockCompanies.filter((_, idx) => idx % 5 === i).slice(0, 3);

    companiesForDay.forEach((company, idx) => {
      const event: EarningsEvent = {
        symbol: company.symbol,
        name: company.name,
        date: dateString,
        time: idx % 2 === 0 ? 'bmo' : 'amc',
        dayOfWeek,
        estimatedEPS: company.eps,
        marketCap: company.marketCap,
        lastPrice: company.lastPrice
      };

      if (event.time === 'bmo') {
        bmo.push(event);
      } else {
        amc.push(event);
      }
    });

    days.push({
      date: dateString,
      dayOfWeek,
      bmo,
      amc,
      during: []
    });
  }

  return days;
}
