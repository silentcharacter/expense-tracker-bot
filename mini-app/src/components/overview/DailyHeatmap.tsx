/** GitHub-style heatmap for the current month's daily spending.
 *
 * Color intensity = quartile of non-recurring spend. Days that include a
 * recurring transaction get a small purple marker in the bottom-left corner,
 * while the cell itself still reflects the day's total spend. Future days are
 * dimmed and non-interactive. Tapping a day toggles selection; selection is
 * reported via `onDaySelect`.
 */

import { useMemo } from "react";
import type { Expense } from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";
import { useTelegram } from "../../hooks/useTelegram";

interface DailyHeatmapProps {
  expenses: Expense[];
  /** 4-digit year of the month to render. */
  referenceYear: number;
  /** Month index (0-11) of the month to render. */
  referenceMonth: number;
  /** ISO date string "YYYY-MM-DD" or null. */
  selectedDay: string | null;
  onDaySelect: (date: string | null) => void;
}

interface DayStats {
  iso: string;
  day: number;
  total: number;
  totalDefault: number;
  recurringTotal: number;
  count: number;
  isFuture: boolean;
}

function isoDate(y: number, m: number, d: number): string {
  return `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

function computeDays(expenses: Expense[], y: number, m: number): DayStats[] {
  const now = new Date();
  const daysInMonth = new Date(y, m + 1, 0).getDate();
  const isCurrentMonth = y === now.getFullYear() && m === now.getMonth();
  const isPastMonth =
    y < now.getFullYear() || (y === now.getFullYear() && m < now.getMonth());
  const todayDay = isCurrentMonth ? now.getDate() : isPastMonth ? daysInMonth : 0;

  const byDay = new Map<number, { total: number; totalDefault: number; recurring: number; count: number }>();
  for (const e of expenses) {
    const d = new Date(e.timestamp);
    if (d.getFullYear() !== y || d.getMonth() !== m) continue;
    const day = d.getDate();
    const entry = byDay.get(day) ?? { total: 0, totalDefault: 0, recurring: 0, count: 0 };
    entry.total += e.amount_base;
    entry.totalDefault += e.amount_default;
    if (e.is_recurring) entry.recurring += e.amount_base;
    entry.count += 1;
    byDay.set(day, entry);
  }

  return Array.from({ length: daysInMonth }, (_, i) => {
    const day = i + 1;
    const s = byDay.get(day) ?? { total: 0, totalDefault: 0, recurring: 0, count: 0 };
    return {
      iso: isoDate(y, m, day),
      day,
      total: s.total,
      totalDefault: s.totalDefault,
      recurringTotal: s.recurring,
      count: s.count,
      isFuture: day > todayDay,
    };
  });
}

/** Number of non-empty intensity levels (1..LEVELS). */
const LEVELS = 5;

/** Build LEVELS thresholds geometrically spaced between the min and max
 *  non-recurring daily spend, so each step covers a constant *ratio* rather
 *  than a constant amount. This keeps low-spend days distinguishable while
 *  compressing the long tail of high-spend days. */
function computeThresholds(days: DayStats[]): number[] {
  const vals = days
    .filter((d) => !d.isFuture && d.total > 0)
    .map((d) => Math.max(0, d.total - d.recurringTotal))
    .filter((v) => v > 0);
  if (vals.length === 0) return Array(LEVELS).fill(0);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  if (max <= min) return Array(LEVELS).fill(max);
  const ratio = Math.pow(max / min, 1 / LEVELS);
  return Array.from({ length: LEVELS }, (_, i) => min * Math.pow(ratio, i + 1));
}

function levelFor(day: DayStats, thresholds: number[]): number {
  const discretionary = Math.max(0, day.total - day.recurringTotal);
  if (discretionary <= 0) return 0;
  for (let i = 0; i < thresholds.length; i++) {
    if (discretionary <= thresholds[i]) return i + 1;
  }
  return thresholds.length;
}

function hasRecurring(day: DayStats): boolean {
  return day.recurringTotal > 0;
}

function formatBannerDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function DailyHeatmap({
  expenses,
  referenceYear,
  referenceMonth,
  selectedDay,
  onDaySelect,
}: DailyHeatmapProps) {
  const { format } = useCurrency();
  const { hapticFeedback } = useTelegram();

  const days = useMemo(
    () => computeDays(expenses, referenceYear, referenceMonth),
    [expenses, referenceYear, referenceMonth],
  );
  const thresholds = useMemo(() => computeThresholds(days), [days]);
  const selected = selectedDay ? days.find((d) => d.iso === selectedDay) ?? null : null;

  function handleClick(d: DayStats) {
    if (d.isFuture) return;
    hapticFeedback?.selectionChanged();
    onDaySelect(d.iso === selectedDay ? null : d.iso);
  }

  const DOW_LABELS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
  const offset = (new Date(referenceYear, referenceMonth, 1).getDay() + 6) % 7;

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
                {format({ base: selected.total, default: selected.totalDefault }, 0)}
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
        {/* Day-of-week header */}
        {DOW_LABELS.map((label) => (
          <div key={label} className="heatmap-dow-header">{label}</div>
        ))}
        {/* Offset placeholders */}
        {Array.from({ length: offset }, (_, i) => (
          <div key={`pad-${i}`} className="heatmap-cell-placeholder" />
        ))}
        {/* Day cells */}
        {days.map((d) => {
          const recurring = hasRecurring(d);
          const level = levelFor(d, thresholds);
          return (
            <button
              key={d.iso}
              type="button"
              className="heatmap-cell"
              data-level={level}
              data-recurring={recurring ? "true" : "false"}
              data-future={d.isFuture ? "true" : "false"}
              data-selected={d.iso === selectedDay ? "true" : "false"}
              aria-label={`${formatBannerDate(d.iso)} ${format({ base: d.total, default: d.totalDefault }, 0)}${recurring ? " (recurring)" : ""}`}
              onClick={() => handleClick(d)}
              disabled={d.isFuture}
            >
              <span className="heatmap-cell__day">{d.day}</span>
              {recurring && <span className="heatmap-cell__recurring" />}
            </button>
          );
        })}
      </div>

      {/* Legend */}
      <div className="mt-3 flex items-center justify-between text-[11px]" style={{ color: "var(--app-text-secondary)" }}>
        <div className="flex items-center gap-1">
          <span>Less</span>
          {Array.from({ length: LEVELS + 1 }, (_, lvl) => (
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
