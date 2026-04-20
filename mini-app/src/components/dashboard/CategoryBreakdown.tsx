import type { CategorySummary } from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";
import { getCategoryColor, getCategoryEmoji, getCategoryLabel } from "../../utils/categories";
import { formatPercent } from "../../utils/format";

interface CategoryBreakdownProps {
  data: CategorySummary[];
}

export function CategoryBreakdown({ data }: CategoryBreakdownProps) {
  const { format } = useCurrency();
  if (!data.length) return null;

  const sorted = [...data].sort((a, b) => b.amount_base - a.amount_base);

  return (
    <div className="card">
      <p className="text-sm font-semibold mb-3" style={{ color: "var(--app-text-primary)" }}>
        Breakdown
      </p>
      <div className="flex flex-col gap-3">
        {sorted.map((entry, i) => (
          <div
            key={entry.category}
            className="stagger-item"
            style={{ animationDelay: `${i * 40}ms` }}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm" style={{ color: "var(--app-text-primary)" }}>
                {getCategoryEmoji(entry.category)} {getCategoryLabel(entry.category)}
              </span>
              <div className="flex items-center gap-2">
                <span className="amount text-sm font-medium" style={{ color: "var(--app-text-primary)" }}>
                  {format({ base: entry.amount_base, default: entry.amount_default }, 0)}
                </span>
                <span className="text-xs w-10 text-right" style={{ color: "var(--app-text-secondary)" }}>
                  {formatPercent(entry.percentage)}
                </span>
              </div>
            </div>
            <div
              className="h-1 rounded-full overflow-hidden"
              style={{ backgroundColor: "var(--app-secondary-bg)" }}
            >
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.min(entry.percentage, 100)}%`,
                  backgroundColor: getCategoryColor(entry.category),
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
