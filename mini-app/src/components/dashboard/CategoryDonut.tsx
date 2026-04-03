import { useMemo, useState } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import type { CategorySummary, Expense, CategoryInfo } from "../../api/types";
import { getCategoryColor, getCategoryEmoji, getCategoryLabel } from "../../utils/categories";
import { formatAmount, formatPercent } from "../../utils/format";

interface CategoryDonutProps {
  data: CategorySummary[];
  allCategories: CategorySummary[];
  expenses: Expense[];
  categories: CategoryInfo[];
  currency: string;
  total: number;
  selectedCategory: string | null;
  onCategoryChange: (category: string | null) => void;
  excludedCategories: Set<string>;
  onToggleExclude: (slug: string) => void;
}

interface ChartEntry {
  key: string;
  displayName: string;
  amount_base: number;
  percentage: number;
  color: string;
}

interface TooltipPayload {
  payload: ChartEntry;
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
      <p className="font-medium">{item.displayName}</p>
      <p className="amount" style={{ color: "var(--app-text-secondary)" }}>
        {formatAmount(item.amount_base, "USD", 0)} · {formatPercent(item.percentage)}
      </p>
    </div>
  );
}

function subcategoryColor(hex: string, index: number, total: number): string {
  const opacity = total === 1 ? 1.0 : 1.0 - (index / (total - 1)) * 0.55;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${opacity.toFixed(2)})`;
}

export function CategoryDonut({ data, allCategories, expenses, categories, currency, total, selectedCategory, onCategoryChange, excludedCategories, onToggleExclude }: CategoryDonutProps) {
  const drillCategory = selectedCategory;
  const [activeSlice, setActiveSlice] = useState<string | null>(null);

  if (!data.length) return null;

  const sorted = useMemo(() => [...data].sort((a, b) => b.amount_base - a.amount_base), [data]);
  const sortedAll = useMemo(() => [...allCategories].sort((a, b) => b.amount_base - a.amount_base), [allCategories]);

  const subcategoryLabelMap = useMemo(() => {
    const map = new Map<string, Map<string, string>>();
    for (const cat of categories) {
      map.set(cat.slug, new Map(cat.subcategories.map((s) => [s.slug, s.label])));
    }
    return map;
  }, [categories]);

  function getSubLabel(catSlug: string, subSlug: string): string {
    return subcategoryLabelMap.get(catSlug)?.get(subSlug) ?? subSlug.replace(/_/g, " ");
  }

  const subcategoryEntries = useMemo(() => {
    if (!drillCategory) return [];
    const filtered = expenses.filter((e) => e.category === drillCategory);
    const catTotal = filtered.reduce((s, e) => s + e.amount_base, 0);
    const buckets = new Map<string, { amount: number; count: number }>();
    for (const e of filtered) {
      const key = e.subcategory?.trim() || "__other__";
      const b = buckets.get(key) ?? { amount: 0, count: 0 };
      buckets.set(key, { amount: b.amount + e.amount_base, count: b.count + 1 });
    }
    return [...buckets.entries()]
      .map(([slug, { amount }]) => ({
        key: slug,
        displayName: slug === "__other__" ? "Other" : getSubLabel(drillCategory, slug),
        amount_base: amount,
        percentage: catTotal > 0 ? (amount / catTotal) * 100 : 0,
      }))
      .sort((a, b) => b.amount_base - a.amount_base);
  }, [drillCategory, expenses, subcategoryLabelMap]);

  const chartEntries: ChartEntry[] = useMemo(() => {
    if (drillCategory) {
      const catColor = getCategoryColor(drillCategory);
      return subcategoryEntries.map((s, i) => ({
        key: s.key,
        displayName: s.displayName,
        amount_base: s.amount_base,
        percentage: s.percentage,
        color: subcategoryColor(catColor, i, subcategoryEntries.length),
      }));
    }
    return sorted.map((e) => ({
      key: e.category,
      displayName: getCategoryLabel(e.category),
      amount_base: e.amount_base,
      percentage: e.percentage,
      color: getCategoryColor(e.category),
    }));
  }, [drillCategory, subcategoryEntries, sorted]);

  function handleClick(key: string) {
    if (!drillCategory) {
      onCategoryChange(key);
      setActiveSlice(null);
    } else {
      setActiveSlice((prev) => (prev === key ? null : key));
    }
  }

  const centerAmount = activeSlice
    ? (chartEntries.find((e) => e.key === activeSlice)?.amount_base ?? 0)
    : drillCategory
    ? chartEntries.reduce((s, e) => s + e.amount_base, 0)
    : total;

  const centerLabel = activeSlice
    ? (chartEntries.find((e) => e.key === activeSlice)?.displayName ?? "")
    : drillCategory
    ? getCategoryLabel(drillCategory)
    : "total";

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-3">
        {drillCategory ? (
          <>
            <button
              className="flex items-center gap-1 text-xs font-medium"
              style={{ color: "var(--app-accent)" }}
              onClick={() => { onCategoryChange(null); setActiveSlice(null); }}
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M8 2L4 6L8 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              All categories
            </button>
            <span style={{ color: "var(--app-text-secondary)" }}>·</span>
            <p
              className="text-[11px] font-semibold uppercase tracking-wider"
              style={{ color: "var(--app-text-secondary)" }}
            >
              {getCategoryEmoji(drillCategory)} {getCategoryLabel(drillCategory)}
            </p>
          </>
        ) : (
          <p
            className="text-[11px] font-semibold uppercase tracking-wider"
            style={{ color: "var(--app-text-secondary)" }}
          >
            By Category
          </p>
        )}
      </div>

      <div className="flex items-center gap-3">
        {/* Donut chart */}
        <div className="relative flex-shrink-0" style={{ width: 130, height: 130 }}>
          <ResponsiveContainer key={drillCategory ?? "root"} width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartEntries}
                dataKey="amount_base"
                nameKey="key"
                innerRadius="55%"
                outerRadius="85%"
                paddingAngle={2}
                stroke="none"
                onClick={(entry: ChartEntry) => handleClick(entry.key)}
                style={{ cursor: "pointer", outline: "none" }}
              >
                {chartEntries.map((entry) => (
                  <Cell
                    key={entry.key}
                    fill={entry.color}
                    opacity={activeSlice && activeSlice !== entry.key ? 0.35 : 1}
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
              {formatAmount(centerAmount, currency, 0)}
            </span>
            <span
              className="text-[9px] leading-tight text-center px-1"
              style={{ color: "var(--app-text-secondary)" }}
            >
              {centerLabel}
            </span>
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-col gap-1.5 flex-1 min-w-0">
          {drillCategory && chartEntries.length === 0 && (
            <p className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
              No breakdown available
            </p>
          )}
          {drillCategory
            ? chartEntries.map((entry) => (
                <button
                  key={entry.key}
                  className="flex items-center gap-2 text-left"
                  onClick={() => handleClick(entry.key)}
                >
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: entry.color }}
                  />
                  <span
                    className="text-xs truncate flex-1"
                    style={{
                      color:
                        activeSlice && activeSlice !== entry.key
                          ? "var(--app-text-secondary)"
                          : "var(--app-text-primary)",
                    }}
                  >
                    {entry.displayName}
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
              ))
            : sortedAll.map((cat) => {
                  const excluded = excludedCategories.has(cat.category);
                  const visible = chartEntries.find((e) => e.key === cat.category);
                  const color = getCategoryColor(cat.category);
                  return (
                    <div key={cat.category} className="flex items-center gap-2">
                      <button
                        className="flex items-center gap-2 text-left flex-1 min-w-0"
                        onClick={() => !excluded && handleClick(cat.category)}
                        style={{ opacity: excluded ? 0.4 : 1 }}
                      >
                        <span
                          className="w-2 h-2 rounded-full flex-shrink-0"
                          style={{ backgroundColor: color }}
                        />
                        <span
                          className="text-xs truncate flex-1"
                          style={{
                            color:
                              activeSlice && activeSlice !== cat.category
                                ? "var(--app-text-secondary)"
                                : "var(--app-text-primary)",
                            textDecoration: excluded ? "line-through" : "none",
                          }}
                        >
                          {getCategoryLabel(cat.category)}
                        </span>
                        <span
                          className="amount text-xs font-medium flex-shrink-0"
                          style={{ color: "var(--app-text-primary)" }}
                        >
                          {formatAmount(cat.amount_base, currency, 0)}
                        </span>
                        <span
                          className="text-[11px] w-9 text-right flex-shrink-0"
                          style={{ color: "var(--app-text-secondary)" }}
                        >
                          {excluded ? "—" : formatPercent(visible?.percentage ?? cat.percentage)}
                        </span>
                      </button>
                      <button
                        className="flex-shrink-0 flex items-center justify-center"
                        style={{ width: 28, height: 28, color: "var(--app-text-secondary)" }}
                        onClick={() => onToggleExclude(cat.category)}
                        aria-label={excluded ? "Show category" : "Hide category"}
                      >
                        {excluded ? (
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
                            <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
                            <line x1="1" y1="1" x2="23" y2="23"/>
                          </svg>
                        ) : (
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                            <circle cx="12" cy="12" r="3"/>
                          </svg>
                        )}
                      </button>
                    </div>
                  );
                })}
        </div>
      </div>
    </div>
  );
}
