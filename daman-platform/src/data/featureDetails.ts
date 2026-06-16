export interface FeatureDetail {
  title: string;
  description: string;
  benefits: string[];
  specifications: { label: string; value: string }[];
  source: string;
}

export const featureDetails: Record<string, FeatureDetail> = {
  'Global Market Access': {
    title: 'Global Market Access',
    description:
      'Access markets worldwide with DAMAN Securities. Trade on 90+ market centers across 36 countries, including major exchanges like NYSE, NASDAQ, LSE, Euronext, Tokyo Stock Exchange, and Hong Kong Stock Exchange. Experience seamless execution across time zones with 24-hour trading support.',
    benefits: [
      'Access to 90+ market centers globally across North America, Europe, Asia-Pacific, and emerging markets',
      'Trade on 36+ country exchanges including US, UK, Germany, Japan, Hong Kong, Singapore, and Australia',
      'Multi-currency support with automatic conversion and competitive foreign exchange rates',
      'Extended trading hours for US markets with pre-market and after-hours sessions',
      'Single platform access to international stocks, ADRs, and foreign securities',
      'Real-time market data feeds from all major global exchanges',
    ],
    specifications: [
      { label: 'Market Centers', value: '90+' },
      { label: 'Countries', value: '36+' },
      { label: 'Currencies Supported', value: '23' },
      { label: 'Trading Hours', value: '24/5' },
      { label: 'Settlement', value: 'T+2' },
      { label: 'Execution Speed', value: '<50ms' },
    ],
    source: 'https://www.interactivebrokers.com/en/trading/products.php',
  },
  'Multi-Asset Trading': {
    title: 'Multi-Asset Trading',
    description:
      'Diversify your portfolio with access to multiple asset classes from a single platform. Trade stocks, ETFs, options, futures, bonds, currencies, commodities, and more. Execute complex multi-leg strategies with advanced order types and institutional-grade execution quality.',
    benefits: [
      'Stocks and ETFs from 90+ global exchanges with fractional share trading available',
      'Options trading with spreads, straddles, strangles, and custom multi-leg strategies',
      'Futures and options on futures covering commodities, indices, currencies, and interest rates',
      'Foreign exchange (FX) trading with 100+ currency pairs and competitive spreads',
      'Fixed income securities including corporate bonds, treasuries, and municipal bonds',
      'Commodities including precious metals, energy, and agricultural products',
      'Mutual funds access to thousands of no-load and load-waived funds',
      'Cryptocurrencies through regulated exchanges (where available)',
    ],
    specifications: [
      { label: 'Asset Classes', value: '8+' },
      { label: 'Stock Exchanges', value: '90+' },
      { label: 'Options Contracts', value: '1.2M+' },
      { label: 'Futures Products', value: '500+' },
      { label: 'FX Pairs', value: '100+' },
      { label: 'ETFs Available', value: '9,000+' },
    ],
    source: 'https://www.interactivebrokers.com/en/trading/products.php',
  },
  'Real-Time Data': {
    title: 'Real-Time Data',
    description:
      'Stay ahead of the market with professional-grade real-time data feeds. Access live quotes, Level II market depth, time and sales, and streaming charts. Our low-latency infrastructure ensures you receive market data with minimal delay, giving you the edge in fast-moving markets.',
    benefits: [
      'Real-time streaming quotes from all major exchanges with sub-second latency',
      'Level II market depth showing full order book with bid/ask sizes',
      'Time and sales data with every trade executed in real-time',
      'Advanced charting with 100+ technical indicators and drawing tools',
      'News feeds integrated from Reuters, Dow Jones, and other premium sources',
      'Customizable watchlists with real-time updates and alerts',
      'Market scanners to identify opportunities based on technical and fundamental criteria',
      'Economic calendar with real-time event updates and consensus estimates',
    ],
    specifications: [
      { label: 'Data Latency', value: '<50ms' },
      { label: 'Quote Updates/sec', value: '10,000+' },
      { label: 'Chart Timeframes', value: '15+' },
      { label: 'Technical Indicators', value: '100+' },
      { label: 'News Sources', value: '25+' },
      { label: 'Market Scanners', value: '50+' },
    ],
    source: 'https://www.interactivebrokers.com/en/trading/products.php',
  },
  'Secure & Regulated': {
    title: 'Secure & Regulated',
    description:
      'Your security is our top priority. DAMAN Securities is regulated by the Securities and Commodities Authority (SCA) and employs bank-level security measures. All customer accounts are protected by SIPC insurance up to $500,000, with additional coverage available. We use 256-bit encryption and multi-factor authentication to protect your data.',
    benefits: [
      'SEC and SCA regulated with strict compliance and oversight',
      'SIPC insurance protection up to $500,000 (including $250,000 cash)',
      'Additional excess SIPC insurance up to $30 million per account',
      '256-bit SSL encryption for all data transmission',
      'Two-factor authentication (2FA) with multiple verification methods',
      'Biometric login support (fingerprint and face recognition)',
      'Account activity monitoring with real-time fraud detection',
      'Segregated customer accounts with tier-1 banks',
      'Regular third-party security audits and penetration testing',
    ],
    specifications: [
      { label: 'Regulatory Bodies', value: 'SEC, SCA' },
      { label: 'SIPC Coverage', value: '$500K' },
      { label: 'Excess Coverage', value: '$30M' },
      { label: 'Encryption', value: '256-bit SSL' },
      { label: 'Authentication', value: '2FA/MFA' },
      { label: 'Uptime SLA', value: '99.9%' },
    ],
    source: 'https://www.interactivebrokers.com/en/general/about/security.php',
  },
  'Advanced Analytics': {
    title: 'Advanced Analytics',
    description:
      'Make informed trading decisions with institutional-grade analytics tools. Access professional charting, fundamental data, risk analytics, portfolio analysis, and market screening tools. Our advanced analytics suite includes backtesting, strategy optimization, and real-time performance tracking.',
    benefits: [
      'Professional charting with 100+ technical indicators and pattern recognition',
      'Fundamental analysis tools with 10+ years of historical financial data',
      'Risk Navigator for portfolio risk assessment and scenario analysis',
      'Option analytics with Greeks, probability calculators, and strategy analyzers',
      'Market scanners with customizable filters for stocks, options, and futures',
      'Backtesting engine to test strategies against historical data',
      'Portfolio analytics with performance attribution and risk metrics',
      'Earnings calendar and analyst ratings with consensus estimates',
      'Heat maps and market sentiment indicators',
    ],
    specifications: [
      { label: 'Technical Indicators', value: '100+' },
      { label: 'Chart Types', value: '15+' },
      { label: 'Fundamental Metrics', value: '200+' },
      { label: 'Scanning Criteria', value: '500+' },
      { label: 'Backtesting Years', value: '20+' },
      { label: 'Portfolio Reports', value: '30+' },
    ],
    source: 'https://www.interactivebrokers.com/en/trading/products.php',
  },
  'Protected Accounts': {
    title: 'Protected Accounts',
    description:
      'Trade with confidence knowing your account is fully protected. All accounts are SIPC insured and backed by additional excess coverage. We offer multiple account types including individual, joint, retirement (IRA), and corporate accounts. Each account comes with comprehensive fraud protection and 24/7 monitoring.',
    benefits: [
      'SIPC protection up to $500,000 per customer (including $250,000 cash)',
      'Excess SIPC coverage providing up to $30 million additional protection',
      'Multiple account types: Individual, Joint, IRA, Roth IRA, Corporate, Trust',
      '24/7 account monitoring with real-time fraud detection systems',
      'Two-factor authentication required for all account access',
      'Secure message center for sensitive communications',
      'Account statements with detailed transaction history and tax reporting',
      'Immediate alerts for account activity via email, SMS, and push notifications',
      'Paper trading accounts for risk-free strategy testing',
    ],
    specifications: [
      { label: 'SIPC Insurance', value: '$500K' },
      { label: 'Excess SIPC', value: '$30M' },
      { label: 'Account Types', value: '10+' },
      { label: 'Security Features', value: '2FA/MFA' },
      { label: 'Monitoring', value: '24/7' },
      { label: 'Statement Access', value: '7 years' },
    ],
    source: 'https://www.interactivebrokers.com/en/general/about/security.php',
  },
};
