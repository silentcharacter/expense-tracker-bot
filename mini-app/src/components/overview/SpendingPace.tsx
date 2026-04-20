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
  const { formatLive: format } = useCurrency();

  const budget = Math.max(1, pace.discretionary_budget);
  const spentPct = Math.min(100, (pace.discretionary_spent / budget) * 100);
  const projectedPct = Math.min(100, (pace.projected_discretionary / budget) * 100);
  const isOver = pace.status === "over_pace";
  const projectedTotal = pace.projected_discretionary + pace.recurring_total;
  const daysRemaining = Math.max(pace.days_in_month - pace.days_elapsed, 0);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <span
          className="text-[11px] font-semibold uppercase"
          style={{ color: "var(--app-text-secondary)", letterSpacing: "0.5px" }}
        >
          Spending pace
        </span>
        <span className="status-badge" data-tone="success">
          Projected <span className="amount ml-1">{format(projectedTotal, 0)}</span>
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
          Spent <span className="amount" style={{ color: "var(--app-text-primary)" }}>{format(pace.discretionary_spent, 0)}</span>
        </span>
        <span>
          Proj <span className="amount" style={{ color: "var(--app-text-primary)" }}>{format(pace.projected_discretionary, 0)}</span>
        </span>
        <span>
          Budget <span className="amount" style={{ color: "var(--app-text-primary)" }}>{format(pace.discretionary_budget, 0)}</span>
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
          <span style={{ color: "var(--app-text-primary)" }}>{format(pace.recurring_spent, 0)}</span>
          {" / "}
          {format(pace.recurring_total, 0)}
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
          {format(pace.available_per_day, 0)}
        </span>
      </div>
    </div>
  );
}
