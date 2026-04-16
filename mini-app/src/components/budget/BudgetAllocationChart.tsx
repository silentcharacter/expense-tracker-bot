/** Donut chart showing how the total budget is split across categories. */

import { useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import type { BudgetEntry } from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";
import { getCategoryColor, getCategoryEmoji, getCategoryLabel } from "../../utils/categories";
import { formatPercent } from "../../utils/format";

interface BudgetAllocationChartProps {
  budgets: BudgetEntry[];
}

interface Entry {
  key: string;
  label: string;
  budget: number;
  percentage: number;
  color: string;
}

export function BudgetAllocationChart({ budgets }: BudgetAllocationChartProps) {
  const { format } = useCurrency();
  const [activeKey, setActiveKey] = useState<string | null>(null);

  const total = budgets.reduce((s, b) => s + b.budget, 0);
  if (total === 0) return null;

  const data: Entry[] = budgets
    .filter((b) => b.budget > 0)
    .sort((a, b) => b.budget - a.budget)
    .map((b) => ({
      key: b.category,
      label: getCategoryLabel(b.category),
      budget: b.budget,
      percentage: (b.budget / total) * 100,
      color: getCategoryColor(b.category),
    }));

  if (data.length === 0) return null;

  const activeEntry = activeKey ? data.find((d) => d.key === activeKey) ?? null : null;

  return (
    <div className="card">
      <p
        className="text-[11px] font-semibold uppercase tracking-wider mb-3"
        style={{ color: "var(--app-text-secondary)" }}
      >
        Allocation
      </p>
      <div className="flex items-center gap-3">
        <div className="relative flex-shrink-0" style={{ width: 160, height: 160 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="budget"
                nameKey="key"
                innerRadius="60%"
                outerRadius="90%"
                paddingAngle={2}
                stroke="none"
                isAnimationActive={false}
                onMouseEnter={(_, index) => setActiveKey(data[index]?.key ?? null)}
                onMouseLeave={() => setActiveKey(null)}
              >
                {data.map((entry) => (
                  <Cell
                    key={entry.key}
                    fill={entry.color}
                    fillOpacity={activeKey && activeKey !== entry.key ? 0.35 : 1}
                  />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none px-2 text-center">
            {activeEntry ? (
              <>
                <span
                  className="text-[10px] font-medium leading-tight truncate max-w-full"
                  style={{ color: "var(--app-text-secondary)" }}
                >
                  {activeEntry.label}
                </span>
                <span
                  className="amount text-[12px] font-bold leading-tight"
                  style={{ color: "var(--app-text-primary)" }}
                >
                  {format(activeEntry.budget, 0)}
                </span>
                <span
                  className="text-[10px] leading-tight"
                  style={{ color: "var(--app-text-secondary)" }}
                >
                  {formatPercent(activeEntry.percentage, false, 0)}
                </span>
              </>
            ) : (
              <>
                <span
                  className="amount text-[13px] font-bold leading-tight"
                  style={{ color: "var(--app-text-primary)" }}
                >
                  {format(total, 0)}
                </span>
                <span className="text-[9px] leading-tight" style={{ color: "var(--app-text-secondary)" }}>
                  budget
                </span>
              </>
            )}
          </div>
        </div>
        <div className="flex flex-col gap-1.5 flex-1 min-w-0">
          {data.map((entry) => (
            <div key={entry.key} className="flex items-center gap-2">
              <span
                className="w-2 h-2 rounded-full flex-shrink-0"
                style={{ backgroundColor: entry.color }}
              />
              <span className="text-xs truncate flex-1" style={{ color: "var(--app-text-primary)" }}>
                {getCategoryEmoji(entry.key)} {entry.label}
              </span>
              <span
                className="text-[11px] w-9 text-right flex-shrink-0"
                style={{ color: "var(--app-text-secondary)" }}
              >
                {formatPercent(entry.percentage, false, 0)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
