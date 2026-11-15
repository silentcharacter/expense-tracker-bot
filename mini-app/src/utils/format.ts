/** Formatting helpers for amounts, dates, and percentages. */

import { formatYmd, toLocalDateStr, todayInTz, yesterdayInTz } from "./dates";

/**
 * Single amount-formatting helper. Every JSX currency render should go through
 * this function (or `CurrencyContext.format`) — never hardcode `$` or `฿`.
 */
export function fmt(amount: number, currency: string, decimals = 2): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      currencyDisplay: "narrowSymbol",
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(amount);
  } catch {
    // Fallback for non-ISO codes: show the code after the number.
    return `${amount.toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })} ${currency}`;
  }
}

/** @deprecated Use `fmt()` or `CurrencyContext.format()` instead. */
export function formatAmount(amount: number, currency: string, decimals = 2): string {
  return fmt(amount, currency, decimals);
}

export function formatAmountCompact(amount: number, currency: string): string {
  if (amount >= 1_000_000) {
    return `${fmt(amount / 1_000_000, currency, 1)}M`;
  }
  if (amount >= 1_000) {
    return `${fmt(amount / 1_000, currency, 1)}K`;
  }
  return fmt(amount, currency);
}

export function formatPercent(value: number, showSign = false, decimals = 1): string {
  const sign = showSign && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(decimals)}%`;
}

/** Absolute date (e.g. "Jan 5, 2026") of an instant, in the user's timezone. */
export function formatDate(isoString: string, tz: string): string {
  return new Date(isoString).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: tz,
  });
}

/**
 * "Today" / "Yesterday" / weekday-date label, relative to the user's today
 * (`todayYmd`, defaults to now in `tz`) rather than the device clock.
 */
export function formatDateRelative(isoString: string, tz: string, todayYmd?: string): string {
  const day = toLocalDateStr(isoString, tz);
  const today = todayYmd ?? todayInTz(tz);
  if (day === today) return "Today";
  if (day === yesterdayInTz(tz, today)) return "Yesterday";
  return formatYmd(day, { weekday: "long", month: "long", day: "numeric" });
}

/** Time of day of an instant in the user's timezone. */
export function formatTime(isoString: string, tz: string): string {
  return new Date(isoString).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    timeZone: tz,
  });
}

