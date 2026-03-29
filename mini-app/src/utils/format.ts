/** Formatting helpers for amounts, dates, and percentages. */

export function formatAmount(amount: number, currency: string, decimals = 2): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    currencyDisplay: "narrowSymbol",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(amount);
}

export function formatAmountCompact(amount: number, currency: string): string {
  if (amount >= 1_000_000) {
    return `${formatAmount(amount / 1_000_000, currency, 1)}M`;
  }
  if (amount >= 1_000) {
    return `${formatAmount(amount / 1_000, currency, 1)}K`;
  }
  return formatAmount(amount, currency);
}

export function formatPercent(value: number, showSign = false): string {
  const sign = showSign && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

export function formatDate(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function formatDateRelative(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  const dateOnly = new Date(date.getFullYear(), date.getMonth(), date.getDate());

  if (dateOnly.getTime() === today.getTime()) {
    return "Today";
  }
  if (dateOnly.getTime() === yesterday.getTime()) {
    return "Yesterday";
  }

  return date.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

export function formatTime(isoString: string): string {
  return new Date(isoString).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}
