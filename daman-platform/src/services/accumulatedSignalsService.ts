import { supabase } from '../lib/supabase';
import { getTradingSessionDate } from '../utils/dubaiTimeUtils';

export interface AccumulatedSignal {
  id: string;
  scanner_type: 'fusion' | 'sniper' | 'options';
  ticker: string;
  side: string;
  entry: number;
  stop: number;
  target: number;
  target2?: number;
  rr: number;
  position_size?: number;
  atr?: number;
  rsi?: number;
  macd_hist?: number;
  vwap?: number;
  signal_data: any;
  triggered_at: string;
  scan_session: string;
  created_at: string;
}

/**
 * Save a signal to the database
 */
export async function saveSignal(
  scannerType: 'fusion' | 'sniper' | 'options',
  signal: any
): Promise<void> {
  const sessionDate = getTradingSessionDate();

  const signalData = {
    scanner_type: scannerType,
    ticker: signal.ticker,
    side: signal.side || signal.signal,
    entry: signal.entry || signal.price || 0,
    stop: signal.stop || signal.stop_loss || signal.stopLoss || 0,
    target: signal.target || signal.target1 || 0,
    target2: signal.target2 || 0,
    rr: signal.rr || signal.riskReward || signal.risk_reward || 0,
    position_size: signal.positionSize || signal.position_size || 0,
    atr: signal.atr || 0,
    rsi: signal.rsi || 0,
    macd_hist: signal.macdHist || signal.macd_hist || 0,
    vwap: signal.vwap || 0,
    signal_data: signal,
    triggered_at: signal.generatedAt || signal.triggered_at || new Date().toISOString(),
    scan_session: sessionDate,
  };

  try {
    // Check if similar signal already exists (same ticker, scanner, side, session, and close entry price)
    const { data: existingSignals } = await supabase
      .from('accumulated_signals')
      .select('*')
      .eq('scanner_type', scannerType)
      .eq('ticker', signal.ticker)
      .eq('side', signalData.side)
      .eq('scan_session', sessionDate);

    // Only save if no duplicate found with similar entry price (within 0.5%)
    const isDuplicate = existingSignals?.some(existing =>
      Math.abs(existing.entry - signalData.entry) / signalData.entry < 0.005
    );

    if (!isDuplicate) {
      const { error } = await supabase
        .from('accumulated_signals')
        .insert(signalData);

      if (error) {
        console.error('Error saving signal:', error);
      }
    }
  } catch (err) {
    console.error('Error saving signal:', err);
  }
}

/**
 * Get all signals for current trading session
 */
export async function getSessionSignals(
  scannerType: 'fusion' | 'sniper' | 'options'
): Promise<AccumulatedSignal[]> {
  const sessionDate = getTradingSessionDate();

  try {
    const { data, error } = await supabase
      .from('accumulated_signals')
      .select('*')
      .eq('scanner_type', scannerType)
      .eq('scan_session', sessionDate)
      .order('triggered_at', { ascending: false });

    if (error) {
      console.error('Error fetching signals:', error);
      return [];
    }

    return data || [];
  } catch (err) {
    console.error('Error fetching signals:', err);
    return [];
  }
}

/**
 * Clear signals for a specific session (called at 1:31 AM reset)
 */
export async function clearSessionSignals(
  scannerType: 'fusion' | 'sniper' | 'options',
  sessionDate: string
): Promise<void> {
  try {
    const { error } = await supabase
      .from('accumulated_signals')
      .delete()
      .eq('scanner_type', scannerType)
      .eq('scan_session', sessionDate);

    if (error) {
      console.error('Error clearing signals:', error);
    }
  } catch (err) {
    console.error('Error clearing signals:', err);
  }
}

/**
 * Clear old signals (older than 7 days)
 */
export async function clearOldSignals(): Promise<void> {
  const sevenDaysAgo = new Date();
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
  const cutoffDate = sevenDaysAgo.toISOString().split('T')[0];

  try {
    const { error } = await supabase
      .from('accumulated_signals')
      .delete()
      .lt('scan_session', cutoffDate);

    if (error) {
      console.error('Error clearing old signals:', error);
    }
  } catch (err) {
    console.error('Error clearing old signals:', err);
  }
}

/**
 * Convert database signal to display format
 */
export function convertSignalToDisplayFormat(dbSignal: AccumulatedSignal): any {
  return {
    id: dbSignal.id,
    ticker: dbSignal.ticker,
    side: dbSignal.side,
    signal: dbSignal.side,
    price: dbSignal.entry,
    entry: dbSignal.entry,
    stop: dbSignal.stop,
    stopLoss: dbSignal.stop,
    stop_loss: dbSignal.stop,
    target: dbSignal.target,
    target1: dbSignal.target,
    target2: dbSignal.target2,
    rr: dbSignal.rr,
    riskReward: dbSignal.rr,
    risk_reward: dbSignal.rr,
    positionSize: dbSignal.position_size,
    position_size: dbSignal.position_size,
    atr: dbSignal.atr || 0,
    rsi: dbSignal.rsi || 0,
    adx: dbSignal.signal_data?.adx || 0,
    macdHist: dbSignal.macd_hist,
    macd_hist: dbSignal.macd_hist,
    vwap: dbSignal.vwap || 0,
    superTrend: dbSignal.signal_data?.superTrend || 0,
    ema200: dbSignal.signal_data?.ema200 || 0,
    volume: dbSignal.signal_data?.volume || 0,
    avgVolume: dbSignal.signal_data?.avgVolume || 0,
    generatedAt: dbSignal.triggered_at,
    triggered_at: dbSignal.triggered_at,
    timeNY: dbSignal.signal_data?.timeNY || dbSignal.triggered_at,
    timeDubai: dbSignal.signal_data?.timeDubai || dbSignal.triggered_at,
    ...dbSignal.signal_data,
  };
}
