/** Top-of-tab budget summary: total + remaining + arc gauge + status pills.
 *
 * Per spec §3.1: status pills count subcategories re-bucketed by raw % used —
 * <70% on track, 70-90% warning, >90% over. Ignores the API's `status` enum
 * because its thresholds differ.
 */

import type { BudgetEntry } from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";

interface BudgetSummaryCardProps {
  budgets: BudgetEntry[];
}

function ArcGauge({ pct }: { pct: number }) {
  const r = 54;
  const circ = 2 * Math.PI * r;
  const fill = Math.min(pct, 100);
  const offset = circ * (1 - fill / 100);
  const color =
    pct > 90 ? "var(--app-danger)" : pct >= 70 ? "#fbbf24" : "var(--app-accent)";
  return (
    <svg width={130} height={130} viewBox="0 0 130 130">
      <circle cx={65} cy={65} r={r} fill="none" stroke="var(--app-secondary-bg)" strokeWidth={10} />
      <circle
        cx={65}
        cy={65}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={10}
        strokeLinecap="round"
        strokeDasharray={circ}
        strokeDashoffset={offset}
        transform="rotate(-90 65 65)"
        style={{ transition: "stroke-dashoffset 0.5s ease" }}
      />
      <text
        x={65}
        y={60}
        textAnchor="middle"
        dominantBaseline="middle"
        fill={color}
        fontSize={20}
        fontWeight={700}
      >
        {Math.round(fill)}%
      </text>
      <text
        x={65}
        y={80}
        textAnchor="middle"
        dominantBaseline="middle"
        fill="var(--app-text-secondary)"
        fontSize={10}
      >
        used
      </text>
    </svg>
  );
}

export function BudgetSummaryCard({ budgets }: BudgetSummaryCardProps) {
  const { format } = useCurrency();

  const activeSubs = budgets
    .flatMap((c) => c.subcategories)
    .filter((s) => s.budget > 0);

  const totalBudget = budgets.reduce((s, c) => s + c.budget, 0);
  const totalSpent = budgets.reduce((s, c) => s + c.spent, 0);
  const totalRemaining = totalBudget - totalSpent;
  const overallPct = totalBudget > 0 ? (totalSpent / totalBudget) * 100 : 0;

  const onTrack = activeSubs.filter((s) => s.percentage < 70).length;
  const warning = activeSubs.filter((s) => s.percentage >= 70 && s.percentage <= 90).length;
  const over = activeSubs.filter((s) => s.percentage > 90).length;

  if (totalBudget === 0) {
    return (
      <div className="card text-center py-6">
        <p className="text-2xl mb-2">💰</p>
        <p className="text-sm font-medium" style={{ color: "var(--app-text-primary)" }}>
          No budgets set yet
        </p>
        <p className="text-xs mt-1" style={{ color: "var(--app-text-secondary)" }}>
          Set a budget below to start tracking
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-[11px] uppercase tracking-wider" style={{ color: "var(--app-text-secondary)" }}>
            Total budget
          </p>
          <p className="amount text-lg font-bold" style={{ color: "var(--app-text-primary)" }}>
            {format(totalBudget, 0)}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[11px] uppercase tracking-wider" style={{ color: "var(--app-text-secondary)" }}>
            Remaining
          </p>
          <p
            className="amount text-lg font-bold"
            style={{ color: totalRemaining >= 0 ? "var(--app-success)" : "var(--app-danger)" }}
          >
            {format(totalRemaining, 0)}
          </p>
        </div>
      </div>

      <div className="flex justify-center mb-3">
        <ArcGauge pct={overallPct} />
      </div>

      <div className="flex gap-2">
        <Pill count={onTrack} label="On track" color="var(--app-success)" />
        <Pill count={warning} label="Warning" color="#fbbf24" />
        <Pill count={over} label="Over" color="var(--app-danger)" />
      </div>
    </div>
  );
}

function Pill({ count, label, color }: { count: number; label: string; color: string }) {
  return (
    <div
      className="flex flex-col items-center py-1.5 rounded-xl flex-1"
      style={{ background: "var(--app-secondary-bg)" }}
    >
      <span className="text-base font-bold" style={{ color }}>
        {count}
      </span>
      <span className="text-[11px]" style={{ color: "var(--app-text-secondary)" }}>
        {label}
      </span>
    </div>
  );
}
