/** Purple gradient summary card: total spent + comparison + 3 stats.
 *
 * In the new MainPage layout this always shows the current month and pulls
 * its formatting from CurrencyContext (so amounts follow the base/default
 * toggle). Legacy DashboardPage still passes `currency`, `period`, and
 * `dateRange` explicitly — those remain supported as a fallback so the old
 * page compiles until it is removed in Phase 7.
 */

import type { PeriodComparison } from "../../api/types";
import { useCurrencyOptional } from "../../context/CurrencyContext";
import { fmt, formatPercent } from "../../utils/format";

interface TotalCardProps {
  total: number;
  totalDefault?: number;
  transactionCount: number;
  dailyAverage: number;
  budgetUsedPercent?: number;
  comparison?: PeriodComparison;
  /** Legacy DashboardPage only — ignored when CurrencyProvider is mounted. */
  currency?: string;
  /** Legacy DashboardPage only — when omitted, the card shows the current month. */
  period?: string;
  /** Legacy DashboardPage only. */
  dateRange?: { start: string; end: string };
  /** Legacy DashboardPage only — count of excluded categories, if any. */
  excludedCount?: number;
}

function periodLabel(period?: string, dateRange?: { start: string; end: string }): string {
  if (!period || !dateRange) {
    return "Total Spent";
  }
  const start = new Date(dateRange.start + "T12:00:00");
  if (period === "month") {
    return `Total · ${start.toLocaleDateString(undefined, { month: "long", year: "numeric" })}`;
  }
  if (period === "year") {
    return `Total · ${start.getFullYear()}`;
  }
  if (period === "today") {
    return "Total · Today";
  }
  return "Total · This week";
}

function previousPeriodName(period?: string, dateRange?: { start: string; end: string }): string {
  if (dateRange && (!period || period === "month")) {
    const start = new Date(dateRange.start + "T12:00:00");
    const prev = new Date(start);
    prev.setMonth(prev.getMonth() - 1);
    return prev.toLocaleDateString(undefined, { month: "long" });
  }
  if (!period || !dateRange) {
    const now = new Date();
    const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    return prev.toLocaleDateString(undefined, { month: "long" });
  }
  const start = new Date(dateRange.start + "T12:00:00");
  if (period === "today") return "yesterday";
  if (period === "year") return String(start.getFullYear() - 1);
  return "last week";
}

export function TotalCard({
  total,
  totalDefault,
  transactionCount,
  dailyAverage,
  budgetUsedPercent,
  comparison,
  currency,
  period,
  dateRange,
  excludedCount,
}: TotalCardProps) {
  const currencyCtx = useCurrencyOptional();

  // Format an amount that has both base and default values (from the backend).
  const formatMoney = (amountBase: number, amountDefault?: number, decimals = 2): string => {
    if (currencyCtx && amountDefault != null) {
      return currencyCtx.format({ base: amountBase, default: amountDefault }, decimals);
    }
    if (currencyCtx) return currencyCtx.formatLive(amountBase, decimals);
    return fmt(amountBase, currency ?? "USD", decimals);
  };

  const comparisonText = comparison
    ? `${formatPercent(Math.abs(comparison.change_percent), false, 0)} ${
        comparison.direction === "up" ? "more" : "less"
      } than ${previousPeriodName(period, dateRange)}`
    : null;

  return (
    <div
      className="rounded-xl p-4 mb-3"
      style={{
        background: "linear-gradient(135deg, #6c3fc5 0%, #4a1fa0 100%)",
        color: "#ffffff",
      }}
    >
      <p className="text-xs opacity-80 mb-1">
        {periodLabel(period, dateRange)}
        {excludedCount ? (
          <span className="opacity-60">
            {" "}
            · excl. {excludedCount} {excludedCount === 1 ? "category" : "categories"}
          </span>
        ) : null}
      </p>
      <p className="amount text-3xl font-bold mb-1">{formatMoney(total, totalDefault, 0)}</p>
      {comparisonText && (
        <p className="text-xs opacity-70 mb-3">
          {comparison!.direction === "up" ? "↑" : "↓"} {comparisonText}
        </p>
      )}
      {!comparisonText && <div className="mb-3" />}

      <div className="flex justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-wide opacity-60">Daily avg</p>
          <p className="amount text-sm font-semibold">{formatMoney(dailyAverage)}</p>
        </div>
        <div className="text-center">
          <p className="text-[10px] uppercase tracking-wide opacity-60">Transactions</p>
          <p className="text-sm font-semibold">{transactionCount}</p>
        </div>
        <div className="text-right">
          <p className="text-[10px] uppercase tracking-wide opacity-60">Budget used</p>
          <p className="text-sm font-semibold">
            {budgetUsedPercent != null ? `${Math.round(budgetUsedPercent)}%` : "—"}
          </p>
        </div>
      </div>
    </div>
  );
}
