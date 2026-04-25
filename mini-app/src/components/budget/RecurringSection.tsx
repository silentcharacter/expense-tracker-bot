/** ↻ RECURRING section grouped by category → subcategory with totals. */

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

interface SubcategoryGroup {
  subcategory: string;
  items: RecurringItem[];
  total: number;
}

interface CategoryGroup {
  category: string;
  subcategories: SubcategoryGroup[];
  total: number;
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

function groupItems(items: RecurringItem[]): CategoryGroup[] {
  const catMap = new Map<string, Map<string, RecurringItem[]>>();

  for (const item of items) {
    const cat = item.category || "";
    const sub = item.subcategory || "";
    if (!catMap.has(cat)) catMap.set(cat, new Map());
    const subMap = catMap.get(cat)!;
    if (!subMap.has(sub)) subMap.set(sub, []);
    subMap.get(sub)!.push(item);
  }

  return Array.from(catMap.entries()).map(([category, subMap]) => {
    const subcategories: SubcategoryGroup[] = Array.from(subMap.entries()).map(([subcategory, subItems]) => ({
      subcategory,
      items: subItems,
      total: subItems.reduce((s, i) => s + i.amount_base, 0),
    }));
    return {
      category,
      subcategories,
      total: subcategories.reduce((s, sg) => s + sg.total, 0),
    };
  });
}

function RecurringRowContent({ item, formatLive }: { item: RecurringItem; formatLive: (v: number, d: number) => string }) {
  return (
    <div className="flex items-center gap-3 py-2.5 pl-4">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate" style={{ color: "var(--app-text-primary)" }}>
          {item.description}
        </p>
        <p className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
          Monthly · {ordinalSuffix(item.day_of_month)}
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
  const groups = groupItems(items);

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

  const allItems = groups.flatMap(g => g.subcategories.flatMap(sg => sg.items));

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
            {groups.map((group, gi) => (
              <div key={group.category || "__none__"}>
                {/* Category header */}
                <div
                  className="flex items-center justify-between py-2"
                  style={{ borderTop: gi > 0 ? "1px solid var(--app-border)" : undefined }}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{group.category ? getCategoryEmoji(group.category) : "🔄"}</span>
                    <span className="text-sm font-semibold capitalize" style={{ color: "var(--app-text-primary)" }}>
                      {group.category || "Other"}
                    </span>
                  </div>
                  <span className="amount text-sm font-semibold" style={{ color: "var(--app-accent)" }}>
                    {formatLive(group.total, 0)}/mo
                  </span>
                </div>

                {/* Subcategory groups */}
                {group.subcategories.map((sg) => (
                  <div key={sg.subcategory || "__none__"} className="mb-1">
                    {/* Subcategory header (only if there's a subcategory name) */}
                    {sg.subcategory && (
                      <div className="flex items-center justify-between pl-4 py-1">
                        <span className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--app-text-secondary)" }}>
                          {sg.subcategory}
                        </span>
                        <span className="amount text-xs font-medium" style={{ color: "var(--app-text-secondary)" }}>
                          {formatLive(sg.total, 0)}/mo
                        </span>
                      </div>
                    )}

                    {/* Items */}
                    {sg.items.map((item, ii) => {
                      const globalIdx = allItems.indexOf(item);
                      const isLast = globalIdx === allItems.length - 1;
                      return (
                        <SwipeableRow
                          key={item.id}
                          isOpen={swipedId === item.id}
                          onOpen={() => setSwipedId(item.id)}
                          onClose={() => setSwipedId(null)}
                          onDeleteClick={() => setPendingItem(item)}
                          borderBottom={!isLast && ii < sg.items.length - 1}
                        >
                          <RecurringRowContent item={item} formatLive={formatLive} />
                        </SwipeableRow>
                      );
                    })}
                  </div>
                ))}
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
