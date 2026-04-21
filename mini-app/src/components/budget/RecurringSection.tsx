/** ↻ RECURRING section with pill "+ Add" button in header. */

import { useState } from "react";
import type { RecurringItem, RecurringResponse } from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";
import { getCategoryEmoji } from "../../utils/categories";
import { ConfirmDialog } from "../settings/ConfirmDialog";
import { SwipeableRow } from "../shared/SwipeableRow";

interface RecurringSectionProps {
  data: RecurringResponse;
  onAdd: () => void;
  onDelete: (id: string) => Promise<void>;
}

function ordinalSuffix(n: number): string {
  if (n >= 11 && n <= 13) return `${n}th`;
  switch (n % 10) {
    case 1: return `${n}st`;
    case 2: return `${n}nd`;
    case 3: return `${n}rd`;
    default: return `${n}th`;
  }
}

function RecurringRowContent({ item, formatLive }: { item: RecurringItem; formatLive: (v: number, d: number) => string }) {
  return (
    <div className="flex items-center gap-3 py-2.5">
      <span className="text-2xl flex-shrink-0">
        {item.category ? getCategoryEmoji(item.category) : "🔄"}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate" style={{ color: "var(--app-text-primary)" }}>
          {item.description}
        </p>
        <p className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
          {item.subcategory || item.category} · Monthly · {ordinalSuffix(item.day_of_month)}
        </p>
      </div>
      <span className="amount text-sm font-semibold flex-shrink-0" style={{ color: "var(--app-text-primary)" }}>
        {formatLive(item.amount_base, 0)}
      </span>
    </div>
  );
}

export function RecurringSection({ data, onAdd, onDelete }: RecurringSectionProps) {
  const { formatLive } = useCurrency();
  const { items } = data;
  const totalBase = items.reduce((s, i) => s + i.amount_base, 0);

  const [swipedId, setSwipedId] = useState<string | null>(null);
  const [pendingItem, setPendingItem] = useState<RecurringItem | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  async function handleConfirmDelete() {
    if (!pendingItem) return;
    setDeleteLoading(true);
    try {
      await onDelete(pendingItem.id);
    } finally {
      setDeleteLoading(false);
      setPendingItem(null);
      setSwipedId(null);
    }
  }

  return (
    <>
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
              <SwipeableRow
                key={item.id}
                isOpen={swipedId === item.id}
                onOpen={() => setSwipedId(item.id)}
                onClose={() => setSwipedId(null)}
                onDeleteClick={() => setPendingItem(item)}
                borderBottom={i < items.length - 1}
              >
                <RecurringRowContent item={item} formatLive={formatLive} />
              </SwipeableRow>
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

      {pendingItem && (
        <ConfirmDialog
          title="Delete recurring expense?"
          message={`"${pendingItem.description}" will be permanently deleted.`}
          confirmLabel="Delete"
          danger
          loading={deleteLoading}
          onConfirm={() => void handleConfirmDelete()}
          onCancel={() => setPendingItem(null)}
        />
      )}
    </>
  );
}
