/** Full-screen report for one trip: totals, categories, transactions, actions. */

import { useCallback, useEffect, useState } from "react";
import { fetchExpenses } from "../../api/expenses";
import { exportExpenses } from "../../api/settings";
import { assignTripExpenses, deleteTrip, fetchTripSummary, updateTrip } from "../../api/trips";
import type {
  Expense,
  SummaryResponse,
  TripEntry,
  UpdateExpenseRequest,
} from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";
import { getCategoryColor, getCategoryEmoji, getCategoryLabel } from "../../utils/categories";
import { TransactionList } from "../dashboard/TransactionList";
import { ConfirmDialog } from "../settings/ConfirmDialog";
import { SkeletonBlock } from "../shared/Skeleton";
import { formatTripRange } from "./TripCard";
import { TripFormModal } from "./TripFormModal";

interface TripDetailProps {
  trip: TripEntry;
  onClose: () => void;
  /** Reload the trip list (and the rest of the page) after a change. */
  onChanged: () => Promise<void>;
  onDeleteExpense?: (id: string) => Promise<void>;
  onEditExpense?: (id: string, data: UpdateExpenseRequest) => Promise<void>;
}

function todayIso(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(
    now.getDate(),
  ).padStart(2, "0")}`;
}

function ActionButton({
  label,
  onClick,
  disabled,
  danger,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="flex-1 py-2.5 rounded-xl text-xs font-semibold whitespace-nowrap"
      style={{
        background: "var(--app-secondary-bg)",
        color: danger ? "var(--app-danger)" : "var(--app-text-primary)",
        border: "1px solid var(--app-border)",
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {label}
    </button>
  );
}

export function TripDetail({
  trip,
  onClose,
  onChanged,
  onDeleteExpense,
  onEditExpense,
}: TripDetailProps) {
  const { format, formatLive } = useCurrency();

  const [current, setCurrent] = useState<TripEntry>(trip);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [summaryData, expenseData] = [
        await fetchTripSummary(current.id),
        await fetchExpenses({ trip_id: current.id, limit: 200 }),
      ];
      setSummary(summaryData);
      setExpenses(expenseData.expenses);
      if (summaryData.trip) setCurrent(summaryData.trip);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load the trip");
    } finally {
      setIsLoading(false);
    }
  }, [current.id]);

  useEffect(() => {
    void load();
    // Only on mount / trip change: `load` is stable per trip id.
  }, [load]);

  async function run(action: () => Promise<string | null>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const message = await action();
      if (message) setNotice(message);
      await load();
      await onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const finishTrip = () =>
    run(async () => {
      await updateTrip(current.id, { end_date: todayIso(), active: false });
      return "Trip finished — new expenses are no longer tagged.";
    });

  const reopenTrip = () =>
    run(async () => {
      await updateTrip(current.id, { end_date: null, active: true });
      return "Trip reopened — new expenses are tagged with it again.";
    });

  const setActive = (active: boolean) =>
    run(async () => {
      await updateTrip(current.id, { active });
      return active
        ? "New expenses are now tagged with this trip."
        : "New expenses are no longer tagged with this trip.";
    });

  const pullInExpenses = () =>
    run(async () => {
      const result = await assignTripExpenses(current.id);
      return result.assigned > 0
        ? `Added ${result.assigned} existing ${result.assigned === 1 ? "expense" : "expenses"}.`
        : "No untagged expenses found in these dates.";
    });

  const removeTrip = () =>
    run(async () => {
      await deleteTrip(current.id);
      onClose();
      return null;
    });

  const categories = summary?.by_category ?? [];
  const total = format({ base: current.total_base, default: current.total_default });
  const perDay = format({
    base: current.daily_average,
    default: current.daily_average_default,
  });

  return (
    <div
      className="fixed inset-0 z-40 overflow-y-auto"
      style={{ background: "var(--app-bg)", color: "var(--app-text-primary)" }}
    >
      <div className="px-4 py-4 flex flex-col gap-3">
        <div className="flex items-start gap-3">
          <span className="text-2xl leading-none">{current.emoji}</span>
          <div className="flex-1 min-w-0">
            <p className="text-base font-semibold truncate">{current.name}</p>
            <p className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
              {formatTripRange(current)} · {current.days}{" "}
              {current.days === 1 ? "day" : "days"}
              {current.is_active && " · active"}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-sm px-2 py-1 rounded"
            style={{ color: "var(--app-text-secondary)", background: "transparent", border: "none" }}
          >
            Close
          </button>
        </div>

        <div className="card">
          <p className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
            Total spent
          </p>
          <p className="amount text-3xl font-semibold mt-1">{total}</p>
          <p className="text-xs mt-1" style={{ color: "var(--app-text-secondary)" }}>
            {current.transaction_count}{" "}
            {current.transaction_count === 1 ? "expense" : "expenses"} · {perDay}/day
          </p>

          {current.budget !== null && (
            <div className="mt-3">
              <div
                className="h-2 rounded-full overflow-hidden"
                style={{ background: "var(--app-secondary-bg)" }}
              >
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.min(current.budget_percentage ?? 0, 100)}%`,
                    background:
                      (current.budget_percentage ?? 0) > 100
                        ? "var(--app-danger)"
                        : "var(--app-accent)",
                  }}
                />
              </div>
              <p className="text-xs mt-1" style={{ color: "var(--app-text-secondary)" }}>
                {(current.budget_percentage ?? 0).toFixed(0)}% of {formatLive(current.budget, 0)}
                {current.budget_remaining !== null &&
                  ` · ${
                    current.budget_remaining >= 0
                      ? `${formatLive(current.budget_remaining, 0)} left`
                      : `${formatLive(Math.abs(current.budget_remaining), 0)} over`
                  }`}
              </p>
            </div>
          )}
        </div>

        <div className="flex gap-2">
          <ActionButton label="Edit" onClick={() => setEditing(true)} disabled={busy} />
          {current.is_open ? (
            <ActionButton label="Finish trip" onClick={() => void finishTrip()} disabled={busy} />
          ) : (
            <ActionButton label="Reopen" onClick={() => void reopenTrip()} disabled={busy} />
          )}
          {current.is_open && !current.is_active && (
            <ActionButton
              label="Tag new expenses"
              onClick={() => void setActive(true)}
              disabled={busy}
            />
          )}
          {current.is_active && (
            <ActionButton
              label="Stop tagging"
              onClick={() => void setActive(false)}
              disabled={busy}
            />
          )}
        </div>

        <div className="flex gap-2">
          <ActionButton
            label="Pull in expenses"
            onClick={() => void pullInExpenses()}
            disabled={busy}
          />
          <ActionButton
            label="Export CSV"
            onClick={() => void exportExpenses({ trip_id: current.id })}
            disabled={busy}
          />
          <ActionButton
            label="Delete"
            danger
            onClick={() => setConfirmingDelete(true)}
            disabled={busy}
          />
        </div>

        {notice && (
          <p className="text-xs px-1" style={{ color: "var(--app-text-secondary)" }}>
            {notice}
          </p>
        )}
        {error && (
          <p className="text-xs px-1" style={{ color: "var(--app-danger)" }}>
            {error}
          </p>
        )}

        {isLoading && !summary ? (
          <SkeletonBlock height={160} className="rounded-xl" />
        ) : (
          categories.length > 0 && (
            <div className="card">
              <p className="text-sm font-semibold mb-3">By category</p>
              {categories.map((entry) => (
                <div key={entry.category} className="flex items-center gap-3 py-2">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center text-base flex-shrink-0"
                    style={{ backgroundColor: `${getCategoryColor(entry.category)}20` }}
                  >
                    {getCategoryEmoji(entry.category)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm truncate">{getCategoryLabel(entry.category)}</p>
                    <div
                      className="h-1 rounded-full mt-1 overflow-hidden"
                      style={{ background: "var(--app-secondary-bg)" }}
                    >
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${entry.percentage}%`,
                          background: getCategoryColor(entry.category),
                        }}
                      />
                    </div>
                  </div>
                  <p className="amount text-sm font-medium flex-shrink-0">
                    {format({ base: entry.amount_base, default: entry.amount_default }, 0)}
                  </p>
                </div>
              ))}
            </div>
          )
        )}

        <TransactionList
          expenses={expenses}
          onDeleteExpense={
            onDeleteExpense &&
            (async (id) => {
              await onDeleteExpense(id);
              await load();
            })
          }
          onEditExpense={
            onEditExpense &&
            (async (id, data) => {
              await onEditExpense(id, data);
              await load();
            })
          }
          showHeader
        />
      </div>

      {editing && (
        <TripFormModal
          trip={current}
          onUpdate={async (data) => {
            await updateTrip(current.id, data);
            await load();
            await onChanged();
          }}
          onClose={() => setEditing(false)}
        />
      )}

      {confirmingDelete && (
        <ConfirmDialog
          title="Delete trip?"
          message={`"${current.name}" will be removed. Its ${current.transaction_count} ${
            current.transaction_count === 1 ? "expense stays" : "expenses stay"
          } in your history, just without the trip label.`}
          confirmLabel="Delete"
          danger
          loading={busy}
          onConfirm={() => {
            setConfirmingDelete(false);
            void removeTrip();
          }}
          onCancel={() => setConfirmingDelete(false)}
        />
      )}
    </div>
  );
}
