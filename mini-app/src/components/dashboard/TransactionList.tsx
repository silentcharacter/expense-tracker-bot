import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Expense } from "../../api/types";
import { useCurrencyOptional } from "../../context/CurrencyContext";
import { getCategoryColor, getCategoryEmoji, getCategoryLabel } from "../../utils/categories";
import { formatAmount } from "../../utils/format";
import { ConfirmDialog } from "../settings/ConfirmDialog";

interface CategoryFilterSel {
  category: string;
  subcategory?: string;
}

interface TransactionListProps {
  expenses: Expense[];
  filterDay?: string | null;
  filterCategory?: CategoryFilterSel | null;
  onClearCategoryFilter?: () => void;
  onDeleteExpense?: (id: string) => Promise<void>;
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

const SWIPE_SNAP = 80;
const SWIPE_THRESHOLD = 40;

interface SwipeRowProps {
  expense: Expense;
  index: number;
  isLast: boolean;
  isOpen: boolean;
  onOpen: (id: string) => void;
  onClose: () => void;
  onDeleteClick: (id: string) => void;
  currency: ReturnType<typeof useCurrencyOptional>;
}

function SwipeRow({
  expense,
  index,
  isLast,
  isOpen,
  onOpen,
  onClose,
  onDeleteClick,
  currency,
}: SwipeRowProps) {
  const rowRef = useRef<HTMLDivElement>(null);

  // Stable refs so event handlers registered once always see current values
  const isOpenRef = useRef(isOpen);
  const onOpenRef = useRef(onOpen);
  const onCloseRef = useRef(onClose);
  useLayoutEffect(() => { isOpenRef.current = isOpen; }, [isOpen]);
  useLayoutEffect(() => { onOpenRef.current = onOpen; }, [onOpen]);
  useLayoutEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  const [translateX, setTranslateX] = useState(isOpen ? -SWIPE_SNAP : 0);
  const [isDragging, setIsDragging] = useState(false);

  // Sync position when open/close state changes externally (e.g. another row opens)
  useLayoutEffect(() => {
    setTranslateX(isOpen ? -SWIPE_SNAP : 0);
  }, [isOpen]);

  const expenseId = expense.id;

  useEffect(() => {
    const el = rowRef.current;
    if (!el) return;

    const gesture = {
      startX: 0,
      startY: 0,
      dragging: false,
      locked: false,
      currentX: 0,
    };

    function onTouchStart(e: TouchEvent) {
      const t = e.touches[0];
      gesture.startX = t.clientX;
      gesture.startY = t.clientY;
      gesture.dragging = false;
      gesture.locked = false;
      gesture.currentX = isOpenRef.current ? -SWIPE_SNAP : 0;
    }

    function onTouchMove(e: TouchEvent) {
      if (gesture.locked) return;

      const t = e.touches[0];
      const dx = t.clientX - gesture.startX;
      const dy = t.clientY - gesture.startY;

      if (!gesture.dragging) {
        // Let vertical scrolling pass through
        if (Math.abs(dy) > Math.abs(dx) + 5) {
          gesture.locked = true;
          return;
        }
        if (Math.abs(dx) <= 5) return;
        gesture.dragging = true;
        setIsDragging(true);
      }

      // Non-passive: this actually prevents the page from scrolling
      e.preventDefault();

      const base = isOpenRef.current ? -SWIPE_SNAP : 0;
      const newX = Math.max(-SWIPE_SNAP, Math.min(0, base + dx));
      gesture.currentX = newX;
      setTranslateX(newX);
    }

    function onTouchEnd() {
      if (!gesture.dragging) return;

      gesture.dragging = false;
      setIsDragging(false);

      const base = isOpenRef.current ? -SWIPE_SNAP : 0;
      const delta = gesture.currentX - base;

      if (!isOpenRef.current && gesture.currentX < -SWIPE_THRESHOLD) {
        onOpenRef.current(expenseId);
      } else if (isOpenRef.current && delta > SWIPE_THRESHOLD) {
        onCloseRef.current();
      } else {
        // snap back
        setTranslateX(base);
      }
    }

    el.addEventListener("touchstart", onTouchStart, { passive: true });
    el.addEventListener("touchmove", onTouchMove, { passive: false });
    el.addEventListener("touchend", onTouchEnd, { passive: true });

    return () => {
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchmove", onTouchMove);
      el.removeEventListener("touchend", onTouchEnd);
    };
  }, [expenseId]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      className="relative overflow-hidden stagger-item"
      style={{
        animationDelay: `${index * 30}ms`,
        borderBottom: !isLast ? "1px solid var(--app-border)" : undefined,
      }}
    >
      {/* Delete button revealed on swipe */}
      <div
        className="absolute right-0 top-0 bottom-0 flex items-center justify-center"
        style={{ width: SWIPE_SNAP, background: "var(--app-danger)" }}
      >
        <button
          type="button"
          className="w-full h-full flex items-center justify-center text-white text-sm font-semibold"
          onClick={() => onDeleteClick(expenseId)}
        >
          Delete
        </button>
      </div>

      {/* Swipeable row — no stagger-item here so animation doesn't fight transform */}
      <div
        ref={rowRef}
        className="flex items-center gap-3 py-3 relative"
        style={{
          transform: `translateX(${translateX}px)`,
          transition: isDragging ? "none" : "transform 0.22s ease",
          background: "var(--app-bg)",
          cursor: "default",
        }}
        onClick={() => {
          if (isOpenRef.current) onCloseRef.current();
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
            {expense.subcategory || getCategoryLabel(expense.category)} · {formatShortDate(expense.timestamp)}
          </p>
        </div>

        <div className="flex-shrink-0 text-right">
          <p className="amount text-sm font-medium" style={{ color: "var(--app-text-primary)" }}>
            {currency
              ? currency.format({ base: expense.amount_base, default: expense.amount_default }, 0)
              : formatAmount(expense.amount_local, expense.local_currency, 0)}
          </p>
          {!currency && expense.local_currency !== expense.base_currency && (
            <p className="amount text-[11px]" style={{ color: "var(--app-text-secondary)" }}>
              {formatAmount(expense.amount_base, expense.base_currency)}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export function TransactionList({
  expenses,
  filterDay = null,
  filterCategory = null,
  onClearCategoryFilter,
  onDeleteExpense,
  showHeader = false,
}: TransactionListProps) {
  const currency = useCurrencyOptional();
  const [swipedId, setSwipedId] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const filtered = expenses.filter((e) => {
    if (filterDay && e.timestamp.slice(0, 10) !== filterDay) return false;
    if (filterCategory) {
      if (e.category !== filterCategory.category) return false;
      if (filterCategory.subcategory && e.subcategory !== filterCategory.subcategory) return false;
    }
    return true;
  });

  const hasActiveFilters = filterDay !== null || filterCategory !== null;

  async function handleConfirmDelete() {
    if (!pendingDeleteId || !onDeleteExpense) return;
    setDeleteLoading(true);
    try {
      await onDeleteExpense(pendingDeleteId);
    } finally {
      setDeleteLoading(false);
      setPendingDeleteId(null);
      setSwipedId(null);
    }
  }

  const pendingExpense = filtered.find((e) => e.id === pendingDeleteId);

  return (
    <>
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
            {filtered.map((expense, i) =>
              onDeleteExpense ? (
                <SwipeRow
                  key={expense.id}
                  expense={expense}
                  index={i}
                  isLast={i === filtered.length - 1}
                  isOpen={swipedId === expense.id}
                  onOpen={setSwipedId}
                  onClose={() => setSwipedId(null)}
                  onDeleteClick={setPendingDeleteId}
                  currency={currency}
                />
              ) : (
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
                      {expense.subcategory || getCategoryLabel(expense.category)} · {formatShortDate(expense.timestamp)}
                    </p>
                  </div>
                  <div className="flex-shrink-0 text-right">
                    <p className="amount text-sm font-medium" style={{ color: "var(--app-text-primary)" }}>
                      {currency
                        ? currency.format({ base: expense.amount_base, default: expense.amount_default }, 0)
                        : formatAmount(expense.amount_local, expense.local_currency, 0)}
                    </p>
                    {!currency && expense.local_currency !== expense.base_currency && (
                      <p className="amount text-[11px]" style={{ color: "var(--app-text-secondary)" }}>
                        {formatAmount(expense.amount_base, expense.base_currency)}
                      </p>
                    )}
                  </div>
                </div>
              )
            )}
          </div>
        )}
      </div>

      {pendingDeleteId && (
        <ConfirmDialog
          title="Delete transaction?"
          message={
            pendingExpense
              ? `"${pendingExpense.description}" will be permanently deleted.`
              : "This transaction will be permanently deleted."
          }
          confirmLabel="Delete"
          danger
          loading={deleteLoading}
          onConfirm={() => void handleConfirmDelete()}
          onCancel={() => setPendingDeleteId(null)}
        />
      )}
    </>
  );
}
