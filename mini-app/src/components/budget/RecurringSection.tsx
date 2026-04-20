/** ↻ RECURRING section with pill "+ Add" button in header. */

import type { RecurringResponse } from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";
import { useTelegram } from "../../hooks/useTelegram";
import { getCategoryEmoji } from "../../utils/categories";

interface RecurringSectionProps {
  data: RecurringResponse;
  onAdd: () => void;
  onDelete: (id: string) => Promise<void>;
}

function ordinalSuffix(n: number): string {
  if (n >= 11 && n <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

export function RecurringSection({ data, onAdd, onDelete }: RecurringSectionProps) {
  const { formatLive } = useCurrency();
  const { showConfirm } = useTelegram();
  const { items } = data;
  const totalBase = items.reduce((s, i) => s + i.amount_base, 0);

  async function handleDelete(id: string, description: string) {
    const ok = await showConfirm(`Delete "${description}"?`);
    if (ok) await onDelete(id);
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <p
          className="text-[11px] font-semibold uppercase tracking-wider"
          style={{ color: "var(--app-text-secondary)" }}
        >
          ↻ Recurring
        </p>
        <button
          onClick={onAdd}
          className="text-xs px-3 py-1 rounded-full font-medium"
          style={{ background: "var(--app-secondary-bg)", color: "var(--app-accent)", border: "none" }}
        >
          + Add
        </button>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-center py-4" style={{ color: "var(--app-text-secondary)" }}>
          No recurring expenses yet
        </p>
      ) : (
        <div className="flex flex-col">
          {items.map((item, i) => (
            <div
              key={item.id}
              className="flex items-center gap-3 py-2.5"
              style={{
                borderBottom: i < items.length - 1 ? "1px solid var(--app-border)" : undefined,
              }}
            >
              <span className="text-2xl flex-shrink-0">
                {item.category ? getCategoryEmoji(item.category) : "🔄"}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: "var(--app-text-primary)" }}>
                  {item.description}
                </p>
                <p className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
                  Monthly · {ordinalSuffix(item.day_of_month)}
                </p>
              </div>
              <span
                className="amount text-sm font-semibold flex-shrink-0"
                style={{ color: "var(--app-text-primary)" }}
              >
                {formatLive(item.amount_base, 0)}
              </span>
              <button
                onClick={() => handleDelete(item.id, item.description)}
                className="p-1.5 flex-shrink-0"
                style={{ color: "var(--app-danger)", opacity: 0.4, border: "none", background: "transparent" }}
                title="Delete"
              >
                🗑️
              </button>
            </div>
          ))}
        </div>
      )}

      {items.length > 0 && (
        <div className="mt-3 pt-3" style={{ borderTop: "1px solid var(--app-border)" }}>
          <p className="text-xs text-center" style={{ color: "var(--app-text-secondary)" }}>
            Total recurring:{" "}
            <span className="font-semibold amount" style={{ color: "var(--app-accent)" }}>
              {formatLive(totalBase, 0)}/mo
            </span>
          </p>
        </div>
      )}
    </div>
  );
}
