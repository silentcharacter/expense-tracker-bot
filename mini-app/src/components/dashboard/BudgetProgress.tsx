import type { BudgetEntry } from "../../api/types";
import { getCategoryEmoji, getCategoryLabel } from "../../utils/categories";
import { formatAmount } from "../../utils/format";

interface BudgetProgressProps {
  budgets: BudgetEntry[];
  currency: string;
}

function statusColor(status: BudgetEntry["status"]): string {
  switch (status) {
    case "warning":
      return "#fbbf24";
    case "exceeded":
      return "var(--app-danger)";
    default:
      return "var(--app-accent)";
  }
}

export function BudgetProgress({ budgets, currency }: BudgetProgressProps) {
  const active = budgets.filter((b) => b.budget > 0);
  if (!active.length) return null;

  return (
    <div className="card">
      <p className="text-sm font-semibold mb-3" style={{ color: "var(--app-text-primary)" }}>
        Budget
      </p>
      <div className="flex flex-col gap-4">
        {active.map((entry) => {
          const fillPct = Math.min(entry.percentage, 100);
          const color = statusColor(entry.status);

          return (
            <div key={entry.category}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm" style={{ color: "var(--app-text-primary)" }}>
                  {getCategoryEmoji(entry.category)} {getCategoryLabel(entry.category)}
                </span>
                <div className="flex items-center gap-1">
                  <span className="amount text-xs font-medium" style={{ color }}>
                    {formatAmount(entry.spent, currency, 0)}
                  </span>
                  <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
                    / {formatAmount(entry.budget, currency, 0)}
                  </span>
                </div>
              </div>
              <div
                className="h-1.5 rounded-full overflow-hidden"
                style={{ backgroundColor: "var(--app-secondary-bg)" }}
              >
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${fillPct}%`, backgroundColor: color }}
                />
              </div>
              {entry.status === "exceeded" && (
                <p className="text-xs mt-0.5" style={{ color: "var(--app-danger)" }}>
                  Over by {formatAmount(Math.abs(entry.remaining), currency, 0)}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
