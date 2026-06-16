export const TICK_COLORS = {
  POSITIVE: {
    bg: 'bg-green-50',
    bgDark: 'bg-green-100',
    bgSolid: 'bg-green-600',
    text: 'text-green-800',
    textBold: 'text-green-700',
    border: 'border-green-500',
    hex: '#00A651',
    hexLight: '#dcfce7',
    hexDark: '#15803d',
    hexVibrant: '#00A651',
    hexPrice: '#16a34a'
  },
  NEGATIVE: {
    bg: 'bg-red-50',
    bgDark: 'bg-red-100',
    bgSolid: 'bg-red-600',
    text: 'text-red-800',
    textBold: 'text-red-700',
    border: 'border-red-500',
    hex: '#DC143C',
    hexLight: '#fee2e2',
    hexDark: '#b91c1c',
    hexVibrant: '#DC143C',
    hexPrice: '#dc2626'
  },
  NEUTRAL: {
    bg: 'bg-slate-50',
    bgDark: 'bg-slate-100',
    bgSolid: 'bg-slate-500',
    text: 'text-slate-700',
    textBold: 'text-slate-600',
    border: 'border-slate-300',
    hex: '#64748b',
    hexLight: '#f1f5f9',
    hexDark: '#475569',
    hexVibrant: '#64748b',
    hexPrice: '#64748b'
  }
};

export const getTickColorClasses = (value: number) => {
  if (value > 0) return TICK_COLORS.POSITIVE;
  if (value < 0) return TICK_COLORS.NEGATIVE;
  return TICK_COLORS.NEUTRAL;
};

export const getTickBackgroundColor = (value: number): string => {
  if (value > 0) return TICK_COLORS.POSITIVE.hexLight;
  if (value < 0) return TICK_COLORS.NEGATIVE.hexLight;
  return TICK_COLORS.NEUTRAL.hexLight;
};

export const getTickTextColor = (value: number): string => {
  if (value > 0) return TICK_COLORS.POSITIVE.hexVibrant;
  if (value < 0) return TICK_COLORS.NEGATIVE.hexVibrant;
  return TICK_COLORS.NEUTRAL.hexDark;
};

export const getTickBorderColor = (value: number): string => {
  if (value > 0) return TICK_COLORS.POSITIVE.hexVibrant;
  if (value < 0) return TICK_COLORS.NEGATIVE.hexVibrant;
  return TICK_COLORS.NEUTRAL.hex;
};

export const getTickPriceColor = (value: number): string => {
  if (value > 0) return TICK_COLORS.POSITIVE.hexPrice;
  if (value < 0) return TICK_COLORS.NEGATIVE.hexPrice;
  return TICK_COLORS.NEUTRAL.hexPrice;
};

export const getTickClasses = (value: number) => {
  const colors = getTickColorClasses(value);
  return {
    background: colors.bg,
    backgroundDark: colors.bgDark,
    text: colors.text,
    textBold: colors.textBold,
    border: colors.border
  };
};
