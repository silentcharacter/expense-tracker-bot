import type { PeriodComparison } from "../../api/types";
import { formatAmount, formatPercent } from "../../utils/format";

interface TotalCardProps {
  total: number;
  currency: string;
  transactionCount: number;
  dailyAverage: number;
  budgetUsedPercent?: number;
  dateRange: { start: string; end: string };
  period: string;
  comparison?: PeriodComparison;
}

function periodLabel(period: string, dateRange: { start: string; end: string }): string {
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

function previousPeriodName(period: string, dateRange: { start: string; end: string }): string {
  const start = new Date(dateRange.start + "T12:00:00");
  if (period === "month") {
    const prev = new Date(start);
    prev.setMonth(prev.getMonth() - 1);
    return prev.toLocaleDateString(undefined, { month: "long" });
  }
  if (period === "year") {
    return String(start.getFullYear() - 1);
  }
  return "last week";
}

export function TotalCard({
  total,
  currency,
  transactionCount,
  dailyAverage,
  budgetUsedPercent,
  dateRange,
  period,
  comparison,
}: TotalCardProps) {
  const comparisonText = comparison
    ? `${formatPercent(Math.abs(comparison.change_percent))} ${comparison.direction === "up" ? "more" : "less"} than ${previousPeriodName(period, dateRange)}`
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
      </p>
      <p className="amount text-3xl font-bold mb-1">
        {formatAmount(total, currency, 0)}
      </p>
      {comparisonText && (
        <p className="text-xs opacity-70 mb-3">
          {comparison!.direction === "up" ? "↑" : "↓"} {comparisonText}
        </p>
      )}
      {!comparisonText && <div className="mb-3" />}

      <div className="flex justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-wide opacity-60">Daily avg</p>
          <p className="amount text-sm font-semibold">{formatAmount(dailyAverage, currency)}</p>
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
