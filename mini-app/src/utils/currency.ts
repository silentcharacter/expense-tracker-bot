/** Currency display helpers. */

/** Common ISO 4217 currency symbols. Falls back to the code itself. */
const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: "$",
  EUR: "€",
  GBP: "£",
  JPY: "¥",
  CNY: "¥",
  THB: "฿",
  SGD: "S$",
  HKD: "HK$",
  AUD: "A$",
  CAD: "C$",
  CHF: "Fr",
  RUB: "₽",
  KRW: "₩",
  INR: "₹",
  MXN: "MX$",
  BRL: "R$",
  IDR: "Rp",
  MYR: "RM",
  PHP: "₱",
  VND: "₫",
};

export function getCurrencySymbol(code: string): string {
  return CURRENCY_SYMBOLS[code.toUpperCase()] ?? code;
}

export function formatLocalAmount(amount: number, currency: string): string {
  return `${amount.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${currency}`;
}
