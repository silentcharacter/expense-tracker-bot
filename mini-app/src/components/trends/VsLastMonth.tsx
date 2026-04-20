/** Per-category current-vs-previous month comparison with dual horizontal bars. */

import type { CategorySummary, SummaryResponse } from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";
import { getCategoryColor, getCategoryEmoji, getCategoryLabel } from "../../utils/categories";
import { formatPercent } from "../../utils/format";

interface VsLastMonthProps {
  summary: SummaryResponse;
}

function previousMonthName(dateRange: { start: string }): string {
  const d = new Date(dateRange.start + "T12:00:00");
  d.setMonth(d.getMonth() - 1);
  return d.toLocaleDateString(undefined, { month: "long" });
}

export function VsLastMonth({ summary }: VsLastMonthProps) {
  const { formatLive: format } = useCurrency();
  const categories = summary.by_category.filter(
    (c) => c.previous_amount_base !== undefined,
  );

  if (categories.length === 0) return null;

  const sorted = [...categories].sort((a, b) => b.amount_base - a.amount_base);
  const prevLabel = previousMonthName(summary.date_range);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <p
          className="text-xs font-semibold tracking-widest"
          style={{ color: "var(--app-text-secondary)" }}
        >
          VS LAST MONTH
        </p>
        <div className="flex items-center gap-3 text-[10px]" style={{ color: "var(--app-text-secondary)" }}>
          <span className="flex items-center gap-1">
            <span
              style={{
                width: 10,
                height: 4,
                borderRadius: 2,
                backgroundColor: "var(--app-text-primary)",
              }}
            />
            Current
          </span>
          <span className="flex items-center gap-1">
            <span
              style={{
                width: 10,
                height: 4,
                borderRadius: 2,
                backgroundColor: "var(--app-text-primary)",
                opacity: 0.4,
              }}
            />
            {prevLabel}
          </span>
        </div>
      </div>

      <div className="flex flex-col">
        {sorted.map((cat) => (
          <CategoryComparisonRow key={cat.category} category={cat} format={format} />
        ))}
      </div>
    </div>
  );
}

interface CategoryComparisonRowProps {
  category: CategorySummary;
  format: (amountBase: number, decimals?: number) => string;
}

function CategoryComparisonRow({ category, format }: CategoryComparisonRowProps) {
  const color = getCategoryColor(category.category);
  const changePercent = category.change_percent ?? 0;
  const prev = category.previous_amount_base ?? 0;
  const curr = category.amount_base;
  const max = Math.max(curr, prev, 1);

  const badgeColor = changePercent <= 0 ? "#34d399" : "#fb923c";
  const badgeLabel =
    changePercent === 0 ? "0%" : formatPercent(changePercent, true, 0);

  return (
    <div
      className="py-2.5"
      style={{ borderBottom: "1px solid var(--app-border)" }}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm flex items-center gap-1.5" style={{ color: "var(--app-text-primary)" }}>
          <span>{getCategoryEmoji(category.category)}</span>
          <span className="truncate">{getCategoryLabel(category.category)}</span>
        </span>
        <span
          className="text-xs font-semibold px-2 py-0.5 rounded-full"
          style={{ backgroundColor: `${badgeColor}22`, color: badgeColor }}
        >
          {badgeLabel}
        </span>
      </div>

      <div className="flex flex-col gap-1 mb-1">
        <div
          className="h-1.5 rounded-full overflow-hidden"
          style={{ backgroundColor: "var(--app-secondary-bg)" }}
        >
          <div
            className="h-full rounded-full"
            style={{ width: `${(curr / max) * 100}%`, backgroundColor: color }}
          />
        </div>
        <div
          className="h-1.5 rounded-full overflow-hidden"
          style={{ backgroundColor: "var(--app-secondary-bg)" }}
        >
          <div
            className="h-full rounded-full opacity-40"
            style={{ width: `${(prev / max) * 100}%`, backgroundColor: color }}
          />
        </div>
      </div>

      <div className="flex items-center justify-between text-[11px]" style={{ color: "var(--app-text-secondary)" }}>
        <span>
          Now{" "}
          <span className="amount" style={{ color: "var(--app-text-primary)" }}>
            {format(curr, 0)}
          </span>
        </span>
        <span>
          Prev{" "}
          <span className="amount">{format(prev, 0)}</span>
        </span>
      </div>
    </div>
  );
}
