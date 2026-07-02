// ── Lightweight i18n (no dependencies) ─────────────────────────────
// Chrome strings only — dynamic market content (headlines, commentary,
// tickers) is intentionally NOT translated.

export const LANGS = { en: 'English', ar: 'العربية' }

export const STR = {
  en: {
    // Bottom nav
    signals: 'Signals',
    markets: 'Markets',
    calendar: 'Calendar',
    portfolio: 'Portfolio',
    news: 'News',
    // Markets sub-tabs
    overview: 'Overview',
    pulseRegime: 'Pulse & Regime',
    sentiment: 'Sentiment',
    wrap: 'Wrap',
    // Signals sub-tabs
    intraday: 'Intraday',
    swing: 'Swing',
    options: 'Options',
    // Portfolio sub-tabs
    holdings: 'Holdings',
    watchlist: 'Watchlist',
    research: 'Research',
    compare: 'Compare',
    // Calendar toggle
    economic: 'Economic',
    earnings: 'Earnings',
    // Side menu
    dailyWrap: 'Daily Wrap-Up',
    nightMode: 'Night Mode',
    dayMode: 'Day Mode',
    notifications: 'Notifications',
    lockSignOut: 'Lock / Sign Out',
    language: 'Language',
    // Common
    refresh: 'Refresh',
    listen: 'Listen',
    stop: 'Stop',
    riskAppetite: 'Risk Appetite',
    stocksToWatch: 'Stocks to Watch',
    breaking: 'BREAKING',
    updated: 'Updated',
    loading: 'Loading…',
  },
  ar: {
    // Bottom nav
    signals: 'الإشارات',
    markets: 'الأسواق',
    calendar: 'التقويم',
    portfolio: 'المحفظة',
    news: 'الأخبار',
    // Markets sub-tabs
    overview: 'نظرة عامة',
    pulseRegime: 'النبض والنظام',
    sentiment: 'المعنويات',
    wrap: 'الملخص',
    // Signals sub-tabs
    intraday: 'اللحظي',
    swing: 'سوينغ',
    options: 'الخيارات',
    // Portfolio sub-tabs
    holdings: 'الحيازات',
    watchlist: 'قائمة المتابعة',
    research: 'البحث',
    compare: 'مقارنة',
    // Calendar toggle
    economic: 'اقتصادي',
    earnings: 'الأرباح',
    // Side menu
    dailyWrap: 'الملخص اليومي',
    nightMode: 'الوضع الليلي',
    dayMode: 'الوضع النهاري',
    notifications: 'الإشعارات',
    lockSignOut: 'قفل / تسجيل الخروج',
    language: 'اللغة',
    // Common
    refresh: 'تحديث',
    listen: 'استماع',
    stop: 'إيقاف',
    riskAppetite: 'شهية المخاطرة',
    stocksToWatch: 'أسهم تحت المراقبة',
    breaking: 'عاجل',
    updated: 'آخر تحديث',
    loading: 'جارٍ التحميل…',
  },
}

export function getLang() {
  try {
    const l = localStorage.getItem('lang')
    return l && LANGS[l] ? l : 'en'
  } catch {
    return 'en'
  }
}

export function setLang(l) {
  const lang = LANGS[l] ? l : 'en'
  try { localStorage.setItem('lang', lang) } catch {}
  try {
    document.documentElement.lang = lang
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr'
  } catch {}
}

export function t(key) {
  const lang = getLang()
  return STR[lang]?.[key] ?? STR.en[key] ?? key
}
