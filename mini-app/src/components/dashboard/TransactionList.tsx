import type { Expense } from "../../api/types";
import { useCurrencyOptional } from "../../context/CurrencyContext";
import { getCategoryColor, getCategoryEmoji, getCategoryLabel } from "../../utils/categories";
import { formatAmount } from "../../utils/format";

interface CategoryFilterSel {
  category: string;
  subcategory?: string;
}

interface TransactionListProps {
  expenses: Expense[];
  filterDay?: string | null;
  filterCategory?: CategoryFilterSel | null;
  onClearCategoryFilter?: () => void;
  showHeader?: boolean;
}

function formatShortDate(isoString: string): string {
  const d = new Date(isoString);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatDayHeader(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function filterName(filter: CategoryFilterSel): string {
  if (filter.subcategory) return filter.subcategory;
  return getCategoryLabel(filter.category);
}

export function TransactionList({
  expenses,
  filterDay = null,
  filterCategory = null,
  onClearCategoryFilter,
  showHeader = false,
}: TransactionListProps) {
  const currency = useCurrencyOptional();

  const filtered = expenses.filter((e) => {
    if (filterDay && e.timestamp.slice(0, 10) !== filterDay) return false;
    if (filterCategory) {
      if (e.category !== filterCategory.category) return false;
      if (filterCategory.subcategory && e.subcategory !== filterCategory.subcategory) return false;
    }
    return true;
  });

  const hasActiveFilters = filterDay !== null || filterCategory !== null;

  return (
    <div className="card">
      {showHeader && (
        <div className="flex items-center justify-between mb-3">
          <p className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
            {filterDay ? `Transactions · ${formatDayHeader(filterDay)}` : "Transactions"}
          </p>
          {filterCategory && onClearCategoryFilter && (
            <button
              type="button"
              onClick={onClearCategoryFilter}
              className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-full"
              style={{
                backgroundColor: "var(--app-secondary-bg)",
                color: "var(--app-text-primary)",
                border: "none",
              }}
            >
              {filterName(filterCategory)}
              <span style={{ color: "var(--app-text-secondary)" }}>×</span>
            </button>
          )}
        </div>
      )}

      {filtered.length === 0 ? (
        <p className="text-sm text-center py-4" style={{ color: "var(--app-text-secondary)" }}>
          {hasActiveFilters ? "No transactions match this filter" : "No transactions found"}
        </p>
      ) : (
        <div className="flex flex-col">
          {filtered.map((expense, i) => (
            <div
              key={expense.id}
              className="flex items-center gap-3 py-3 stagger-item"
              style={{
                animationDelay: `${i * 30}ms`,
                borderBottom: i < filtered.length - 1 ? "1px solid var(--app-border)" : undefined,
              }}
            >
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 text-lg"
                style={{ backgroundColor: `${getCategoryColor(expense.category)}20` }}
              >
                {getCategoryEmoji(expense.category)}
              </div>

              <div className="flex-1 min-w-0">
                <p
                  className="text-sm font-medium truncate flex items-center gap-1"
                  style={{ color: "var(--app-text-primary)" }}
                >
                  <span className="truncate">{expense.description}</span>
                  {expense.is_recurring && (
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0"
                      style={{
                        backgroundColor: "color-mix(in srgb, var(--heatmap-recurring) 20%, transparent)",
                        color: "var(--heatmap-recurring)",
                        fontWeight: 600,
                      }}
                    >
                      ↻ auto
                    </span>
                  )}
                </p>
                <p className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
                  {(expense.subcategory || getCategoryLabel(expense.category))} · {formatShortDate(expense.timestamp)}
                </p>
              </div>

              <div className="flex-shrink-0 text-right">
                <p
                  className="amount text-sm font-medium"
                  style={{ color: "var(--app-text-primary)" }}
                >
                  {currency
                    ? currency.format(expense.amount_base, 0)
                    : formatAmount(expense.amount_local, expense.local_currency, 0)}
                </p>
                {!currency && expense.local_currency !== expense.base_currency && (
                  <p
                    className="amount text-[11px]"
                    style={{ color: "var(--app-text-secondary)" }}
                  >
                    {formatAmount(expense.amount_base, expense.base_currency)}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
