/**
 * IST Date Formatting Utilities
 * All dates on the portal are displayed in Indian Standard Time (Asia/Kolkata)
 */

const IST_TIMEZONE = 'Asia/Kolkata';
const IST_LOCALE = 'en-IN';

/**
 * Format a date/timestamp to IST with date + time
 * Example: "6 Apr 2026, 02:30 PM"
 */
export function formatDateTimeIST(ts) {
  if (!ts) return '-';
  return new Date(ts).toLocaleDateString(IST_LOCALE, {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
    timeZone: IST_TIMEZONE,
  });
}

/**
 * Format a date/timestamp to IST date only
 * Example: "6 Apr 2026"
 */
export function formatDateIST(ts) {
  if (!ts) return '-';
  return new Date(ts).toLocaleDateString(IST_LOCALE, {
    day: 'numeric', month: 'short', year: 'numeric',
    timeZone: IST_TIMEZONE,
  });
}

/**
 * Format a date/timestamp to IST long date
 * Example: "6 April 2026"
 */
export function formatDateLongIST(ts) {
  if (!ts) return '-';
  return new Date(ts).toLocaleDateString(IST_LOCALE, {
    day: 'numeric', month: 'long', year: 'numeric',
    timeZone: IST_TIMEZONE,
  });
}

/**
 * Format a date/timestamp to IST time only
 * Example: "02:30 PM"
 */
export function formatTimeIST(ts) {
  if (!ts) return '-';
  return new Date(ts).toLocaleTimeString(IST_LOCALE, {
    hour: '2-digit', minute: '2-digit',
    timeZone: IST_TIMEZONE,
  });
}

/**
 * Format a date/timestamp with weekday
 * Example: "Mon, 6 Apr"
 */
export function formatDateWeekdayIST(ts) {
  if (!ts) return '-';
  return new Date(ts).toLocaleDateString(IST_LOCALE, {
    weekday: 'short', day: 'numeric', month: 'short',
    timeZone: IST_TIMEZONE,
  });
}

/**
 * Format a date/timestamp with full weekday and long month
 * Example: "Monday, 6 April 2026"
 */
export function formatDateFullIST(ts) {
  if (!ts) return '-';
  return new Date(ts).toLocaleDateString(IST_LOCALE, {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    timeZone: IST_TIMEZONE,
  });
}

/**
 * Generic IST locale string (date + time, full)
 * Example: "6/4/2026, 2:30:00 pm"
 */
export function toLocaleStringIST(ts) {
  if (!ts) return '-';
  return new Date(ts).toLocaleString(IST_LOCALE, { timeZone: IST_TIMEZONE });
}
