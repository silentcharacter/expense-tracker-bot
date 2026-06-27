/** Top-of-tab budget summary: total + remaining + arc gauge + status pills.
 *
 * Per spec §3.1: status pills count subcategories re-bucketed by raw % used —
 * <70% on track, 70-100% warning, >100% over. Ignores the API's `status` enum
 * because its thresholds differ.
 */

import type { BudgetEntry } from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";

interface BudgetSummaryCardProps {
  budgets: BudgetEntry[];
  totalBudget: number;
  totalSpent: number;
}

function ArcGauge({ pct }: { pct: number }) {
  const r = 60;
  const cx = 80;
  const cy = 75;
  const circ = 2 * Math.PI * r;
  const arcLen = circ * 0.5; // 180° arc, top half only
  const fill = Math.min(pct, 100);
  const fillLen = arcLen * (fill / 100);
  const color =
    pct > 100 ? "var(--app-danger)" : pct >= 70 ? "#fbbf24" : "var(--app-accent)";
  return (
    <svg width={160} height={95} viewBox="0 0 160 95">
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke="var(--app-secondary-bg)"
        strokeWidth={12}
        strokeLinecap="round"
        strokeDasharray={`${arcLen} ${circ}`}
        transform={`rotate(180 ${cx} ${cy})`}
      />
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={12}
        strokeLinecap="round"
        strokeDasharray={`${fillLen} ${circ}`}
        transform={`rotate(180 ${cx} ${cy})`}
        style={{ transition: "stroke-dasharray 0.5s ease" }}
      />
      <text
        x={cx}
        y={cy - 18}
        textAnchor="middle"
        dominantBaseline="middle"
        fill="var(--app-text-primary)"
        fontSize={24}
        fontWeight={700}
      >
        {Math.round(fill)}%
      </text>
      <text
        x={cx}
        y={cy + 2}
        textAnchor="middle"
        dominantBaseline="middle"
        fill="var(--app-text-secondary)"
        fontSize={11}
      >
        used
      </text>
    </svg>
  );
}

export function BudgetSummaryCard({ budgets, totalBudget, totalSpent }: BudgetSummaryCardProps) {
  const { formatLive: format } = useCurrency();

  const activeSubs = budgets
    .flatMap((c) => c.subcategories)
    .filter((s) => s.budget > 0);

  const totalRemaining = totalBudget - totalSpent;
  const overallPct = totalBudget > 0 ? (totalSpent / totalBudget) * 100 : 0;

  const onTrack = activeSubs.filter((s) => s.percentage < 70).length;
  const warning = activeSubs.filter((s) => s.percentage >= 70 && s.percentage <= 100).length;
  const over = activeSubs.filter((s) => s.percentage > 100).length;

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
