/** Spending pace card: discretionary progress bar + recurring line + per-day hint.
 *
 * Recurring is excluded from the projection (per spec §1.2) because it's a
 * fixed monthly template, not a linear-in-time expense.
 */

import type { SpendingPace as SpendingPaceData } from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";

interface SpendingPaceProps {
  pace: SpendingPaceData;
}

export function SpendingPace({ pace }: SpendingPaceProps) {
  const { format: formatAmount, formatLive } = useCurrency();
  const formatSpent = (base: number, defaultAmount?: number) =>
    defaultAmount == null ? formatLive(base, 0) : formatAmount({ base, default: defaultAmount }, 0);

  const budget = Math.max(1, pace.discretionary_budget);
  const spentPct = Math.min(100, (pace.discretionary_spent / budget) * 100);
  const projectedPct = Math.min(100, (pace.projected_discretionary / budget) * 100);
  const isOver = pace.status === "over_pace";
  const projectedTotal = pace.projected_discretionary + pace.recurring_total;
  const totalDeviation = projectedTotal - pace.budget_total;
  const isOverBudget = totalDeviation > 0;
  const daysRemaining = Math.max(pace.days_in_month - pace.days_elapsed, 0);

  // Default-currency counterparts so the projected/deviation figures reconcile
  // with the historical recurring total (see backend _recurring_base_total).
  const hasDefault =
    pace.projected_discretionary_default != null &&
    pace.recurring_total_default != null &&
    pace.budget_total_default != null;
  const projectedTotalDefault = hasDefault
    ? pace.projected_discretionary_default! + pace.recurring_total_default!
    : undefined;
  const totalDeviationDefault =
    projectedTotalDefault != null ? projectedTotalDefault - pace.budget_total_default! : undefined;

  return (
    <div className="card">
      <div className="flex items-center justify-between gap-2 flex-wrap mb-3">
        <span
          className="text-[11px] font-semibold uppercase"
          style={{ color: "var(--app-text-secondary)", letterSpacing: "0.5px" }}
        >
          Spending pace
        </span>
        <span className="status-badge" data-tone={isOverBudget ? "danger" : "success"}>
          Projected <span className="amount ml-1">{formatSpent(projectedTotal, projectedTotalDefault)}</span>
          <span className="ml-1" style={{ opacity: 0.8 }}>
            ({isOverBudget ? "Over" : "Saving"}{" "}
            {formatSpent(
              Math.abs(totalDeviation),
              totalDeviationDefault != null ? Math.abs(totalDeviationDefault) : undefined,
            )})
          </span>
        </span>
      </div>

      <div className="flex items-center justify-between mb-2">
        <p className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
          Day-to-day
        </p>
        <span className="status-badge" data-tone={isOver ? "danger" : "success"}>
          {isOver ? "Over pace" : "On track"}
        </span>
      </div>

      <div className="pace-bar mb-1">
        <div
          className="pace-bar__fill"
          data-status={pace.status}
          style={{ width: `${spentPct}%` }}
        />
        <div className="pace-bar__projection" style={{ left: `${projectedPct}%` }} />
        <div className="pace-bar__limit" />
      </div>

      <div className="flex justify-between text-[11px] mb-4" style={{ color: "var(--app-text-secondary)" }}>
        <span>
          Spent <span className="amount" style={{ color: "var(--app-text-primary)" }}>{formatSpent(pace.discretionary_spent, pace.discretionary_spent_default)}</span>
          {" of "}
          <span className="amount" style={{ color: "var(--app-text-primary)" }}>{formatSpent(pace.discretionary_budget, pace.discretionary_budget_default)}</span>
        </span>
        <span>
          Proj <span className="amount" style={{ color: "var(--app-text-primary)" }}>{formatSpent(pace.projected_discretionary, pace.projected_discretionary_default)}</span>
        </span>
      </div>

      {/* Recurring line — no bar: binary (paid/unpaid), a bar adds no info */}
      <div
        className="flex items-center justify-between py-2 mb-3"
        style={{ borderTop: "1px solid var(--app-border)" }}
      >
        <span className="text-sm" style={{ color: "var(--app-text-primary)" }}>
          ↻ Recurring
        </span>
        <span className="amount text-sm" style={{ color: "var(--app-text-secondary)" }}>
          <span style={{ color: "var(--app-text-primary)" }}>{formatSpent(pace.recurring_spent, pace.recurring_spent_default)}</span>
          {" / "}
          {formatSpent(pace.recurring_total, pace.recurring_total_default)}
        </span>
      </div>

      {/* Per-day callout */}
      <div
        className="rounded-lg p-3 flex items-center justify-between"
        style={{ backgroundColor: "var(--app-secondary-bg)" }}
      >
        <div className="flex flex-col">
          <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
            You can spend per day
          </span>
          <span className="text-[11px]" style={{ color: "var(--app-text-secondary)" }}>
            for the remaining {daysRemaining} {daysRemaining === 1 ? "day" : "days"}
          </span>
        </div>
        <span className="amount text-base font-semibold" style={{ color: "var(--app-text-primary)" }}>
          {formatSpent(pace.available_per_day, pace.available_per_day_default ?? undefined)}
        </span>
      </div>
    </div>
  );
}
