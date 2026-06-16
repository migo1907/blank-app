/**
 * Comprehensive ticker lists for market scanners
 */

export const MEGA_LIQUID_TICKERS = [
  // Major Indices ETFs
  'SPY', 'QQQ', 'IWM', 'DIA',

  // Tech Giants (FAANG+)
  'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA', 'NFLX',

  // Major Tech
  'AMD', 'INTC', 'AVGO', 'ORCL', 'ADBE', 'CRM', 'QCOM', 'TXN', 'AMAT', 'LRCX',
  'KLAC', 'SNPS', 'CDNS', 'ASML', 'TSM',

  // Semiconductors
  'MU', 'MRVL', 'ON', 'MPWR', 'SWKS', 'NXPI', 'ARM',

  // Finance
  'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'BLK', 'SCHW', 'AXP', 'V', 'MA', 'PYPL',

  // Healthcare
  'UNH', 'JNJ', 'PFE', 'ABBV', 'TMO', 'LLY', 'MRK', 'ABT', 'DHR', 'BMY',

  // Consumer
  'AMGN', 'COST', 'WMT', 'HD', 'NKE', 'MCD', 'SBUX', 'DIS', 'CMCSA', 'BKNG',

  // Energy
  'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX',

  // Industrial
  'BA', 'CAT', 'HON', 'UPS', 'GE', 'MMM', 'DE', 'LMT', 'RTX',

  // Communication
  'T', 'VZ', 'TMUS',

  // Retail/E-commerce
  'TGT', 'LOW', 'TJX', 'EBAY', 'SHOP',

  // Automotive
  'F', 'GM', 'RIVN', 'LCID',

  // Other Popular
  'COIN', 'SQ', 'ROKU', 'ZM', 'UBER', 'LYFT', 'ABNB', 'PLTR', 'SNOW', 'NET'
];

export const HIGH_VOLUME_TICKERS = [
  // 3x Leveraged ETFs
  'TQQQ', 'SQQQ', 'SPXU', 'UPRO', 'SPXS', 'UDOW', 'SDOW', 'TNA', 'TZA',
  'SOXL', 'SOXS', 'TECL', 'TECS', 'FAS', 'FAZ', 'NUGT', 'DUST', 'JNUG', 'JDST',
  'LABU', 'LABD', 'YINN', 'YANG', 'ERX', 'ERY', 'TMF', 'TMV', 'CURE', 'DIRX',

  // 2x Leveraged ETFs
  'SSO', 'SDS', 'QLD', 'QID', 'UWM', 'TWM', 'UCO', 'SCO', 'USO', 'DIG', 'DUG',

  // Inverse ETFs
  'SH', 'PSQ', 'DOG', 'RWM', 'EUM', 'EEV',

  // Volatility
  'VXX', 'UVXY', 'SVXY', 'VIXY', 'VIXM',

  // Sector ETFs
  'XLF', 'XLK', 'XLE', 'XLV', 'XLI', 'XLY', 'XLP', 'XLU', 'XLB', 'XLRE',
  'XME', 'XRT', 'XHB', 'XBI', 'XOP', 'XTL', 'XPH', 'XSD',

  // Major Index ETFs
  'SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'VOO', 'IVV', 'VEA', 'VWO', 'EEM', 'EFA',

  // Tech Giants (FAANG+)
  'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA', 'NFLX',

  // Major Tech
  'AMD', 'INTC', 'AVGO', 'ORCL', 'ADBE', 'CRM', 'QCOM', 'TXN', 'AMAT', 'LRCX',
  'KLAC', 'SNPS', 'CDNS', 'ASML', 'TSM', 'NOW', 'INTU', 'PANW', 'FTNT',

  // Semiconductors
  'MU', 'MRVL', 'ON', 'MPWR', 'SWKS', 'NXPI', 'ARM', 'MCHP', 'ADI', 'ALGM',

  // AI & Cloud
  'PLTR', 'AI', 'SNOW', 'NET', 'DDOG', 'CRWD', 'ZS', 'MDB', 'OKTA', 'S',

  // Finance
  'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'BLK', 'SCHW', 'AXP', 'V', 'MA', 'PYPL',
  'SQ', 'COIN', 'AFRM', 'SOFI', 'NU', 'UPST',

  // Healthcare & Biotech
  'UNH', 'JNJ', 'PFE', 'ABBV', 'TMO', 'LLY', 'MRK', 'ABT', 'DHR', 'BMY',
  'AMGN', 'GILD', 'VRTX', 'REGN', 'MRNA', 'BNTX', 'ISRG', 'SYK', 'ELV',

  // Consumer & Retail
  'COST', 'WMT', 'HD', 'NKE', 'MCD', 'SBUX', 'DIS', 'CMCSA', 'BKNG', 'ABNB',
  'TGT', 'LOW', 'TJX', 'EBAY', 'SHOP', 'DASH', 'UBER', 'LYFT', 'SE',

  // Energy
  'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'OXY', 'HAL', 'VLO',

  // Industrial & Aerospace
  'BA', 'CAT', 'HON', 'UPS', 'GE', 'MMM', 'DE', 'LMT', 'RTX', 'GD', 'NOC',

  // Communication
  'T', 'VZ', 'TMUS', 'CHTR', 'DIS',

  // Automotive & EV
  'F', 'GM', 'RIVN', 'LCID', 'NIO', 'XPEV', 'LI',

  // High Beta / Crypto Related
  'MARA', 'RIOT', 'MSTR', 'HUT', 'BITF', 'BTBT', 'CLSK',

  // Meme Stocks (High Volume)
  'AMC', 'GME', 'BBBY', 'BB', 'NOK', 'WISH', 'CLOV',

  // China Stocks
  'BABA', 'JD', 'PDD', 'BIDU', 'NIO', 'XPEV', 'LI', 'TME', 'BILI',

  // High Momentum / Growth
  'HOOD', 'RBLX', 'U', 'PATH', 'PLUG', 'FSLR', 'ENPH', 'SEDG',
  'ROKU', 'ZM', 'PINS', 'SNAP', 'TWLO', 'DOCU', 'SQ', 'AFRM'
];

export const CRYPTO_RELATED_TICKERS = [
  'COIN', 'MARA', 'RIOT', 'MSTR', 'HUT', 'BITF', 'BTBT', 'CAN', 'CLSK',
  'GBTC', 'ETHE', 'BITO', 'BITI'
];

export const PENNY_MOMENTUM_TICKERS = [
  'SIRI', 'SOFI', 'PLUG', 'NIO', 'LCID', 'RIVN', 'F', 'NOK', 'BB', 'WISH',
  'CLOV', 'SKLZ', 'OPEN', 'RKT', 'UWMC', 'PLTR'
];

export const ALL_SCANNER_TICKERS = [
  ...new Set([
    ...MEGA_LIQUID_TICKERS,
    ...HIGH_VOLUME_TICKERS,
    ...CRYPTO_RELATED_TICKERS,
    ...PENNY_MOMENTUM_TICKERS
  ])
];

// Preset configurations
export const SCANNER_PRESETS = {
  'Mega Liquids': MEGA_LIQUID_TICKERS,
  'High Volume': HIGH_VOLUME_TICKERS,
  'Crypto Related': CRYPTO_RELATED_TICKERS,
  'Penny Momentum': PENNY_MOMENTUM_TICKERS,
  'All Tickers': ALL_SCANNER_TICKERS,
};

export function getTickersByPreset(preset: keyof typeof SCANNER_PRESETS): string[] {
  return SCANNER_PRESETS[preset] || MEGA_LIQUID_TICKERS;
}
