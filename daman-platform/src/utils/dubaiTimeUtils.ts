/**
 * Dubai Time Utilities
 * Handles all Dubai timezone conversions and trading session logic
 */

/**
 * Get current time in Dubai timezone
 */
export function getDubaiTime(): Date {
  const now = new Date();
  const dubaiOffset = 4 * 60; // Dubai is UTC+4
  const localOffset = now.getTimezoneOffset();
  const totalOffset = dubaiOffset + localOffset;

  return new Date(now.getTime() + totalOffset * 60 * 1000);
}

/**
 * Convert any date to Dubai timezone
 */
export function convertToDubaiTime(date: Date | string): Date {
  const inputDate = typeof date === 'string' ? new Date(date) : date;
  const dubaiOffset = 4 * 60; // Dubai is UTC+4
  const localOffset = inputDate.getTimezoneOffset();
  const totalOffset = dubaiOffset + localOffset;

  return new Date(inputDate.getTime() + totalOffset * 60 * 1000);
}

/**
 * Get current Dubai date (for session tracking)
 */
export function getDubaiDate(): string {
  const dubaiTime = getDubaiTime();
  return dubaiTime.toISOString().split('T')[0];
}

/**
 * Check if current Dubai time is within trading session (1:00 PM - 1:30 AM)
 */
export function isWithinTradingSession(): boolean {
  const dubaiTime = getDubaiTime();
  const hours = dubaiTime.getHours();
  const minutes = dubaiTime.getMinutes();

  // Trading session: 13:00 (1 PM) to 01:30 (1:30 AM next day)
  // This means: 13:00-23:59 today OR 00:00-01:30 tomorrow

  if (hours >= 13 && hours <= 23) {
    // Between 1 PM and midnight
    return true;
  }

  if (hours === 0 || (hours === 1 && minutes <= 30)) {
    // Between midnight and 1:30 AM
    return true;
  }

  return false;
}

/**
 * Get the trading session date for signal storage
 * Sessions run from 1 PM to 1:30 AM, so signals after midnight
 * belong to the previous day's session
 */
export function getTradingSessionDate(): string {
  const dubaiTime = getDubaiTime();
  const hours = dubaiTime.getHours();

  // If it's between midnight and 1:30 AM, use previous day's date
  if (hours >= 0 && hours < 2) {
    const sessionDate = new Date(dubaiTime);
    sessionDate.setDate(sessionDate.getDate() - 1);
    return sessionDate.toISOString().split('T')[0];
  }

  // Otherwise use current date
  return dubaiTime.toISOString().split('T')[0];
}

/**
 * Check if it's time to reset the signal list (1:31 AM Dubai time)
 */
export function shouldResetSignals(): boolean {
  const dubaiTime = getDubaiTime();
  const hours = dubaiTime.getHours();
  const minutes = dubaiTime.getMinutes();

  // Reset at 1:31 AM
  return hours === 1 && minutes >= 31;
}

/**
 * Calculate milliseconds until next scan
 * Returns immediate (0) if within trading session, or time until 1 PM
 */
export function getMillisecondsUntilNextScan(): number {
  if (isWithinTradingSession()) {
    return 0; // Scan immediately
  }

  const dubaiTime = getDubaiTime();
  const hours = dubaiTime.getHours();
  const minutes = dubaiTime.getMinutes();

  let hoursUntil13: number;

  if (hours < 13) {
    // Today before 1 PM
    hoursUntil13 = 13 - hours;
  } else {
    // After 1:30 AM, wait until 1 PM today
    hoursUntil13 = (24 - hours) + 13;
  }

  const minutesUntil13 = (hoursUntil13 * 60) - minutes;
  return minutesUntil13 * 60 * 1000;
}

/**
 * Format Dubai time for display
 */
export function formatDubaiTime(date: Date | string): string {
  const dubaiTime = typeof date === 'string' ? convertToDubaiTime(date) : convertToDubaiTime(date);

  const hours = dubaiTime.getHours();
  const minutes = dubaiTime.getMinutes();
  const seconds = dubaiTime.getSeconds();

  const ampm = hours >= 12 ? 'PM' : 'AM';
  const displayHours = hours % 12 || 12;

  const mm = minutes.toString().padStart(2, '0');
  const ss = seconds.toString().padStart(2, '0');

  return `${displayHours}:${mm}:${ss} ${ampm} Dubai`;
}

/**
 * Get scan interval in milliseconds (30 seconds for Fusion, 60 seconds for Sniper)
 */
export function getScanInterval(scannerType: 'fusion' | 'sniper'): number {
  return scannerType === 'fusion' ? 30000 : 60000; // 30s or 60s
}
