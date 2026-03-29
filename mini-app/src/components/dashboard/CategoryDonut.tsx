import { useState } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import type { CategorySummary } from "../../api/types";
import { getCategoryColor, getCategoryLabel } from "../../utils/categories";
import { formatAmount, formatPercent } from "../../utils/format";

interface CategoryDonutProps {
  data: CategorySummary[];
  currency: string;
  total: number;
}

interface TooltipPayload {
  name: string;
  value: number;
  payload: CategorySummary;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayload[];
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  return (
    <div
      className="px-3 py-2 rounded-lg text-sm shadow-lg"
      style={{
        backgroundColor: "var(--tg-theme-bg-color, #1a1a2e)",
        border: "1px solid var(--app-border)",
        color: "var(--app-text-primary)",
        zIndex: 50,
        position: "relative",
      }}
    >
      <p className="font-medium">{getCategoryLabel(item.category)}</p>
      <p className="amount" style={{ color: "var(--app-text-secondary)" }}>
        {formatAmount(item.amount_base, "USD", 0)} · {formatPercent(item.percentage)}
      </p>
    </div>
  );
}

export function CategoryDonut({ data, currency, total }: CategoryDonutProps) {
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  if (!data.length) return null;

  const sorted = [...data].sort((a, b) => b.amount_base - a.amount_base);

  const centerText = activeCategory
    ? formatAmount(
        sorted.find((e) => e.category === activeCategory)?.amount_base ?? 0,
        currency,
        0
      )
    : formatAmount(total, currency, 0);

  const centerLabel = activeCategory
    ? getCategoryLabel(activeCategory)
    : "total";

  return (
    <div className="card">
      <p
        className="text-[11px] font-semibold uppercase tracking-wider mb-3"
        style={{ color: "var(--app-text-secondary)" }}
      >
        By Category
      </p>
      <div className="flex items-center gap-3">
        {/* Donut chart with centered total */}
        <div className="relative flex-shrink-0" style={{ width: 130, height: 130 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={sorted}
                dataKey="amount_base"
                nameKey="category"
                innerRadius="55%"
                outerRadius="85%"
                paddingAngle={2}
                stroke="none"
                onClick={(entry: CategorySummary) =>
                  setActiveCategory(activeCategory === entry.category ? null : entry.category)
                }
                style={{ cursor: "pointer", outline: "none" }}
              >
                {sorted.map((entry) => (
                  <Cell
                    key={entry.category}
                    fill={getCategoryColor(entry.category)}
                    opacity={activeCategory && activeCategory !== entry.category ? 0.35 : 1}
                  />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} wrapperStyle={{ zIndex: 50 }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <span
              className="amount text-[13px] font-bold leading-tight"
              style={{ color: "var(--app-text-primary)" }}
            >
              {centerText}
            </span>
            <span
              className="text-[9px] leading-tight"
              style={{ color: "var(--app-text-secondary)" }}
            >
              {centerLabel}
            </span>
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-col gap-1.5 flex-1 min-w-0">
          {sorted.map((entry) => (
            <button
              key={entry.category}
              className="flex items-center gap-2 text-left"
              onClick={() =>
                setActiveCategory(activeCategory === entry.category ? null : entry.category)
              }
            >
              <span
                className="w-2 h-2 rounded-full flex-shrink-0"
                style={{ backgroundColor: getCategoryColor(entry.category) }}
              />
              <span
                className="text-xs truncate flex-1"
                style={{
                  color:
                    activeCategory && activeCategory !== entry.category
                      ? "var(--app-text-secondary)"
                      : "var(--app-text-primary)",
                }}
              >
                {getCategoryLabel(entry.category)}
              </span>
              <span
                className="amount text-xs font-medium flex-shrink-0"
                style={{ color: "var(--app-text-primary)" }}
              >
                {formatAmount(entry.amount_base, currency, 0)}
              </span>
              <span
                className="text-[11px] w-9 text-right flex-shrink-0"
                style={{ color: "var(--app-text-secondary)" }}
              >
                {formatPercent(entry.percentage)}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
