import type { Expense } from "../../api/types";
import { getCategoryColor, getCategoryEmoji, getCategoryLabel } from "../../utils/categories";
import { formatAmount } from "../../utils/format";

interface TransactionListProps {
  expenses: Expense[];
}

function formatShortDate(isoString: string): string {
  const d = new Date(isoString);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function TransactionList({ expenses }: TransactionListProps) {
  if (!expenses.length) {
    return (
      <div className="card text-center py-6">
        <p className="text-sm" style={{ color: "var(--app-text-secondary)" }}>
          No transactions found
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {expenses.map((expense, i) => (
        <div
          key={expense.id}
          className="flex items-center gap-3 py-3 stagger-item"
          style={{
            animationDelay: `${i * 30}ms`,
            borderBottom: i < expenses.length - 1 ? "1px solid var(--app-border)" : undefined,
          }}
        >
          {/* Category icon */}
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 text-lg"
            style={{ backgroundColor: `${getCategoryColor(expense.category)}20` }}
          >
            {getCategoryEmoji(expense.category)}
          </div>

          {/* Description + category/date */}
          <div className="flex-1 min-w-0">
            <p
              className="text-sm font-medium truncate"
              style={{ color: "var(--app-text-primary)" }}
            >
              {expense.description}
            </p>
            <p className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
              {getCategoryLabel(expense.category)} · {formatShortDate(expense.timestamp)}
            </p>
          </div>

          {/* Amounts */}
          <div className="flex-shrink-0 text-right">
            <p
              className="amount text-sm font-medium"
              style={{ color: "var(--app-text-primary)" }}
            >
              {formatAmount(expense.amount_local, expense.local_currency, 0)}
            </p>
            {expense.local_currency !== expense.base_currency && (
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
  );
}
