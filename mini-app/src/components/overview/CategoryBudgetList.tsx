/** Category breakdown with budgets and expandable subcategories.
 *
 * Two modes:
 * - Month mode (filterDay=null): shows spent vs budget, progress bar relative to budget.
 * - Day mode (filterDay set): shows per-day totals, progress bar relative to day total.
 *
 * Two click zones per row: the arrow toggles subcategory expansion, the row
 * body toggles the transaction filter. Subcategory click overrides parent.
 */

import { useMemo, useState } from "react";
import type { BudgetEntry, Expense, SubcategoryBudgetEntry } from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";
import { useTelegram } from "../../hooks/useTelegram";
import { getCategoryColor, getCategoryEmoji, getCategoryLabel } from "../../utils/categories";

export interface CategoryFilter {
  category: string;
  subcategory?: string;
}

interface CategoryBudgetListProps {
  budgets: BudgetEntry[];
  expenses: Expense[];
  filterDay: string | null;
  selected: CategoryFilter | null;
  onSelect: (filter: CategoryFilter | null) => void;
}

interface DayTotals {
  /** base-currency totals per category slug. */
  byCategory: Map<string, number>;
  /** base-currency totals per `${category}/${subcategory}` slug. */
  bySub: Map<string, number>;
  /** overall day total (base currency). */
  total: number;
}

function computeDayTotals(expenses: Expense[], day: string | null): DayTotals {
  const byCategory = new Map<string, number>();
  const bySub = new Map<string, number>();
  let total = 0;
  if (!day) return { byCategory, bySub, total };
  for (const e of expenses) {
    const iso = e.timestamp.slice(0, 10);
    if (iso !== day) continue;
    byCategory.set(e.category, (byCategory.get(e.category) ?? 0) + e.amount_base);
    const subKey = `${e.category}/${e.subcategory}`;
    bySub.set(subKey, (bySub.get(subKey) ?? 0) + e.amount_base);
    total += e.amount_base;
  }
  return { byCategory, bySub, total };
}

function formatDayHeader(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function CategoryBudgetList({
  budgets,
  expenses,
  filterDay,
  selected,
  onSelect,
}: CategoryBudgetListProps) {
  const { format } = useCurrency();
  const { hapticFeedback } = useTelegram();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const dayTotals = useMemo(() => computeDayTotals(expenses, filterDay), [expenses, filterDay]);

  const isDay = filterDay !== null;

  const getVisibleSubs = (cat: BudgetEntry) =>
    cat.subcategories.filter((sub) =>
      isDay
        ? (dayTotals.bySub.get(`${cat.category}/${sub.slug}`) ?? 0) > 0
        : sub.spent > 0,
    );

  const expandable = useMemo(
    () => budgets.filter((b) => getVisibleSubs(b).length > 0).map((b) => b.category),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [budgets, isDay, dayTotals],
  );
  const allExpanded = expandable.length > 0 && expandable.every((c) => expanded.has(c));

  function toggleAll() {
    hapticFeedback?.selectionChanged();
    setExpanded(allExpanded ? new Set() : new Set(expandable));
  }

  function toggleExpand(catSlug: string) {
    hapticFeedback?.selectionChanged();
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(catSlug)) next.delete(catSlug);
      else next.add(catSlug);
      return next;
    });
  }

  function selectCategory(catSlug: string) {
    hapticFeedback?.selectionChanged();
    if (selected?.category === catSlug && !selected.subcategory) {
      onSelect(null);
    } else {
      onSelect({ category: catSlug });
    }
  }

  function selectSub(catSlug: string, subSlug: string) {
    hapticFeedback?.selectionChanged();
    if (selected?.category === catSlug && selected.subcategory === subSlug) {
      onSelect(null);
    } else {
      onSelect({ category: catSlug, subcategory: subSlug });
    }
  }

  // Sort: in month mode keep API order; in day mode sort by day spend desc.
  const sorted = useMemo(() => {
    if (!isDay) return budgets;
    return [...budgets].sort(
      (a, b) => (dayTotals.byCategory.get(b.category) ?? 0) - (dayTotals.byCategory.get(a.category) ?? 0),
    );
  }, [budgets, dayTotals, isDay]);

  const visible = isDay
    ? sorted.filter((b) => (dayTotals.byCategory.get(b.category) ?? 0) > 0)
    : sorted.filter((b) => b.spent > 0);

  return (
    <div className="card">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
          {isDay ? `Spending · ${formatDayHeader(filterDay!)}` : "By Category"}
        </p>
        <div className="flex items-center gap-2">
          {isDay && (
            <span className="amount text-sm font-medium" style={{ color: "var(--app-text-primary)" }}>
              {format(dayTotals.total, 0)}
            </span>
          )}
          {expandable.length > 0 && (
            <button
              type="button"
              onClick={toggleAll}
              className="text-[11px] px-2 py-0.5 rounded-full"
              style={{
                backgroundColor: "var(--app-secondary-bg)",
                color: "var(--app-text-secondary)",
                border: "none",
              }}
            >
              {allExpanded ? "Collapse" : "Expand"}
            </button>
          )}
        </div>
      </div>

      {visible.length === 0 && (
        <p className="text-sm text-center py-4" style={{ color: "var(--app-text-secondary)" }}>
          {isDay ? "No spending this day" : "No spending this period"}
        </p>
      )}

      {/* Rows */}
      <div className="flex flex-col">
        {visible.map((cat) => {
          const visibleSubs = getVisibleSubs(cat);
          const hasSubs = visibleSubs.length > 0;
          const isExpanded = expanded.has(cat.category);
          const isSelected = selected?.category === cat.category && !selected.subcategory;

          const daySpend = dayTotals.byCategory.get(cat.category) ?? 0;
          const spent = isDay ? daySpend : cat.spent;
          const denom = isDay ? Math.max(1, dayTotals.total) : Math.max(1, cat.budget || 1);
          const pct = isDay ? (daySpend / denom) * 100 : cat.percentage;
          const barPct = Math.min(100, pct);
          const isHot = !isDay && cat.budget > 0 && pct > 90;

          return (
            <div key={cat.category}>
              <div
                className="flex items-center gap-2 py-2 px-1 rounded-lg"
                style={{
                  backgroundColor: isSelected ? "var(--app-card-alt-bg)" : "transparent",
                }}
              >
                {/* Expand arrow (click zone 1) */}
                <button
                  type="button"
                  onClick={() => hasSubs && toggleExpand(cat.category)}
                  aria-label={hasSubs ? (isExpanded ? "Collapse" : "Expand") : ""}
                  className="w-5 h-5 flex items-center justify-center flex-shrink-0"
                  style={{
                    color: "var(--app-text-secondary)",
                    border: "none",
                    background: "transparent",
                    cursor: hasSubs ? "pointer" : "default",
                    visibility: hasSubs ? "visible" : "hidden",
                    transform: isExpanded ? "rotate(90deg)" : "none",
                    transition: "transform 120ms ease",
                    fontSize: 10,
                  }}
                >
                  ▶
                </button>

                {/* Row body (click zone 2) */}
                <button
                  type="button"
                  onClick={() => selectCategory(cat.category)}
                  className="flex-1 flex items-center gap-2 min-w-0 text-left"
                  style={{ border: "none", background: "transparent", cursor: "pointer" }}
                >
                  <span className="text-lg flex-shrink-0">
                    {getCategoryEmoji(cat.category)}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-sm truncate" style={{ color: "var(--app-text-primary)" }}>
                        {getCategoryLabel(cat.category)}
                      </span>
                      <span className="text-xs flex-shrink-0" style={{ color: "var(--app-text-secondary)" }}>
                        {isDay ? (
                          `${pct.toFixed(0)}%`
                        ) : (
                          <>
                            <span className="amount" style={{ color: "var(--app-text-primary)" }}>
                              {format(spent, 0)}
                            </span>
                            {cat.budget > 0 && <> · {pct.toFixed(0)}%</>}
                          </>
                        )}
                      </span>
                    </div>
                    <div
                      className="h-1 rounded-full overflow-hidden"
                      style={{ backgroundColor: "var(--app-secondary-bg)" }}
                    >
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${barPct}%`,
                          backgroundColor: isHot ? "var(--app-danger)" : getCategoryColor(cat.category),
                        }}
                      />
                    </div>
                  </div>
                </button>
              </div>

              {/* Subcategories */}
              {hasSubs && isExpanded && (
                <div
                  className="ml-6 pl-3 mb-1"
                  style={{ borderLeft: "2px solid var(--app-border)" }}
                >
                  {visibleSubs.map((sub) => (
                    <SubRow
                      key={sub.slug}
                      sub={sub}
                      parentColor={getCategoryColor(cat.category)}
                      isDay={isDay}
                      daySpend={dayTotals.bySub.get(`${cat.category}/${sub.slug}`) ?? 0}
                      dayTotal={dayTotals.total}
                      isSelected={
                        selected?.category === cat.category && selected.subcategory === sub.slug
                      }
                      onSelect={() => selectSub(cat.category, sub.slug)}
                      format={format}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface SubRowProps {
  sub: SubcategoryBudgetEntry;
  parentColor: string;
  isDay: boolean;
  daySpend: number;
  dayTotal: number;
  isSelected: boolean;
  onSelect: () => void;
  format: (amount: number, decimals?: number) => string;
}

function SubRow({
  sub,
  parentColor,
  isDay,
  daySpend,
  dayTotal,
  isSelected,
  onSelect,
  format,
}: SubRowProps) {
  const hasBudget = sub.budget > 0;
  const spent = isDay ? daySpend : sub.spent;
  const pct = isDay
    ? (daySpend / Math.max(1, dayTotal)) * 100
    : hasBudget
    ? sub.percentage
    : 0;
  const barPct = Math.min(100, pct);
  const isHot = !isDay && hasBudget && pct > 90;

  if (isDay && daySpend <= 0) return null;

  return (
    <button
      type="button"
      onClick={onSelect}
      className="w-full flex items-center gap-2 py-1.5 text-left rounded-lg px-2"
      style={{
        border: "none",
        background: isSelected ? "var(--app-card-alt-bg)" : "transparent",
        cursor: "pointer",
      }}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 mb-1">
          <span className="text-xs truncate" style={{ color: "var(--app-text-primary)" }}>
            {sub.label}
          </span>
          <span className="text-[11px] flex-shrink-0" style={{ color: "var(--app-text-secondary)" }}>
            {isDay ? (
              <>
                <span className="amount" style={{ color: "var(--app-text-primary)" }}>
                  {format(spent, 0)}
                </span>
                {" · "}
                {pct.toFixed(0)}%
              </>
            ) : hasBudget ? (
              <>
                <span className="amount" style={{ color: "var(--app-text-primary)" }}>
                  {format(spent, 0)}
                </span>
                {" / "}
                {format(sub.budget, 0)}
              </>
            ) : (
              "no budget"
            )}
          </span>
        </div>
        {(isDay || hasBudget) && (
          <div
            className="h-0.5 rounded-full overflow-hidden"
            style={{ backgroundColor: "var(--app-secondary-bg)" }}
          >
            <div
              className="h-full rounded-full"
              style={{
                width: `${barPct}%`,
                backgroundColor: isHot ? "var(--app-danger)" : parentColor,
              }}
            />
          </div>
        )}
      </div>
    </button>
  );
}
