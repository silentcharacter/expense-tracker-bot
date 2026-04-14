/** GitHub-style heatmap for the current month's daily spending.
 *
 * Color intensity = quartile of non-recurring spend. Days whose spend is
 * dominated by recurring transactions are colored purple so they don't skew
 * the scale. Future days are dimmed and non-interactive. Tapping a day toggles
 * selection; selection is reported via `onDaySelect`.
 */

import { useMemo } from "react";
import type { Expense } from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";
import { useTelegram } from "../../hooks/useTelegram";

interface DailyHeatmapProps {
  expenses: Expense[];
  /** ISO date string "YYYY-MM-DD" or null. */
  selectedDay: string | null;
  onDaySelect: (date: string | null) => void;
}

interface DayStats {
  iso: string;
  day: number;
  total: number;
  recurringTotal: number;
  count: number;
  isFuture: boolean;
}

function isoDate(y: number, m: number, d: number): string {
  return `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

function computeDays(expenses: Expense[]): DayStats[] {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  const daysInMonth = new Date(y, m + 1, 0).getDate();
  const todayDay = now.getDate();

  const byDay = new Map<number, { total: number; recurring: number; count: number }>();
  for (const e of expenses) {
    const d = new Date(e.timestamp);
    if (d.getFullYear() !== y || d.getMonth() !== m) continue;
    const day = d.getDate();
    const entry = byDay.get(day) ?? { total: 0, recurring: 0, count: 0 };
    entry.total += e.amount_base;
    if (e.is_recurring) entry.recurring += e.amount_base;
    entry.count += 1;
    byDay.set(day, entry);
  }

  return Array.from({ length: daysInMonth }, (_, i) => {
    const day = i + 1;
    const s = byDay.get(day) ?? { total: 0, recurring: 0, count: 0 };
    return {
      iso: isoDate(y, m, day),
      day,
      total: s.total,
      recurringTotal: s.recurring,
      count: s.count,
      isFuture: day > todayDay,
    };
  });
}

/** Split non-recurring daily spend into 4 quartile thresholds. */
function computeThresholds(days: DayStats[]): number[] {
  const vals = days
    .filter((d) => !d.isFuture && d.total > 0)
    .map((d) => Math.max(0, d.total - d.recurringTotal))
    .filter((v) => v > 0)
    .sort((a, b) => a - b);
  if (vals.length === 0) return [0, 0, 0, 0];
  const q = (p: number) => vals[Math.min(vals.length - 1, Math.floor(vals.length * p))];
  return [q(0.25), q(0.5), q(0.75), q(1)];
}

function levelFor(day: DayStats, thresholds: number[]): number {
  const discretionary = Math.max(0, day.total - day.recurringTotal);
  if (discretionary <= 0) return 0;
  if (discretionary <= thresholds[0]) return 1;
  if (discretionary <= thresholds[1]) return 2;
  if (discretionary <= thresholds[2]) return 3;
  return 4;
}

function isRecurringDominant(day: DayStats): boolean {
  return day.total > 0 && day.recurringTotal / day.total >= 0.6;
}

function formatBannerDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function DailyHeatmap({ expenses, selectedDay, onDaySelect }: DailyHeatmapProps) {
  const { format } = useCurrency();
  const { hapticFeedback } = useTelegram();

  const days = useMemo(() => computeDays(expenses), [expenses]);
  const thresholds = useMemo(() => computeThresholds(days), [days]);
  const selected = selectedDay ? days.find((d) => d.iso === selectedDay) ?? null : null;

  function handleClick(d: DayStats) {
    if (d.isFuture) return;
    hapticFeedback?.selectionChanged();
    onDaySelect(d.iso === selectedDay ? null : d.iso);
  }

  return (
    <div className="card">
      {/* Banner */}
      <div className="mb-3 flex items-center justify-between">
        {selected ? (
          <>
            <div>
              <p className="text-xs uppercase tracking-wide" style={{ color: "var(--app-text-secondary)" }}>
                {formatBannerDate(selected.iso)}
              </p>
              <p className="amount text-lg font-semibold" style={{ color: "var(--app-text-primary)" }}>
                {format(selected.total, 0)}
              </p>
            </div>
            <p className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
              {selected.count} {selected.count === 1 ? "txn" : "txns"}
            </p>
          </>
        ) : (
          <p className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
            Tap a day to see details
          </p>
        )}
      </div>

      {/* Grid */}
      <div className="heatmap-grid">
        {days.map((d) => {
          const recurring = isRecurringDominant(d);
          const level = recurring ? 0 : levelFor(d, thresholds);
          return (
            <button
              key={d.iso}
              type="button"
              className="heatmap-cell"
              data-level={level}
              data-recurring={recurring ? "true" : "false"}
              data-future={d.isFuture ? "true" : "false"}
              data-selected={d.iso === selectedDay ? "true" : "false"}
              aria-label={`${formatBannerDate(d.iso)} ${format(d.total, 0)}`}
              onClick={() => handleClick(d)}
              disabled={d.isFuture}
            />
          );
        })}
      </div>

      {/* Legend */}
      <div className="mt-3 flex items-center justify-between text-[11px]" style={{ color: "var(--app-text-secondary)" }}>
        <div className="flex items-center gap-1">
          <span>Less</span>
          {[0, 1, 2, 3, 4].map((lvl) => (
            <span
              key={lvl}
              style={{
                width: 10,
                height: 10,
                borderRadius: 2,
                backgroundColor: `var(--heatmap-${lvl})`,
              }}
            />
          ))}
          <span>More</span>
        </div>
        <div className="flex items-center gap-1">
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: 2,
              backgroundColor: "var(--heatmap-recurring)",
            }}
          />
          <span>Recurring</span>
        </div>
      </div>
    </div>
  );
}
