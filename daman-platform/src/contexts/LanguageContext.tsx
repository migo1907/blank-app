import { createContext, useContext, useEffect, useState, ReactNode } from 'react';

type Lang = 'en' | 'ar';

// Minimal i18n dictionary. Covers navigation + key headings; extend as needed.
const DICT: Record<string, { en: string; ar: string }> = {
  'nav.home': { en: 'Home', ar: 'الرئيسية' },
  'nav.market': { en: 'Market Overview', ar: 'نظرة السوق' },
  'nav.ai': { en: 'AI Strategist', ar: 'محلل الذكاء' },
  'nav.portfolio': { en: 'Portfolio', ar: 'المحفظة' },
  'nav.watchlist': { en: 'Watchlist', ar: 'قائمة المتابعة' },
  'nav.settings': { en: 'Settings', ar: 'الإعدادات' },
  'nav.login': { en: 'Login', ar: 'تسجيل الدخول' },
  'common.language': { en: 'العربية', ar: 'English' },
};

interface LanguageContextType {
  lang: Lang;
  toggleLang: () => void;
  t: (key: string) => string;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => (localStorage.getItem('lang') as Lang) || 'en');

  useEffect(() => {
    const root = document.documentElement;
    root.lang = lang;
    root.dir = lang === 'ar' ? 'rtl' : 'ltr';
    localStorage.setItem('lang', lang);
  }, [lang]);

  const toggleLang = () => setLang((prev) => (prev === 'en' ? 'ar' : 'en'));
  const t = (key: string) => DICT[key]?.[lang] ?? key;

  return (
    <LanguageContext.Provider value={{ lang, toggleLang, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) throw new Error('useLanguage must be used within LanguageProvider');
  return context;
}
