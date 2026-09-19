/** One trip in the Trips tab: dates, total, pace, and budget progress. */

import type { TripEntry } from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";

interface TripCardProps {
  trip: TripEntry;
  onOpen: (trip: TripEntry) => void;
}

/** "10 Sep – 20 Sep 2026", or "10 Sep 2026 – now" while the trip is running. */
export function formatTripRange(trip: { start_date: string; end_date: string | null }): string {
  const start = new Date(trip.start_date + "T00:00:00");
  const startLabel = start.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: trip.end_date ? undefined : "numeric",
  });
  if (!trip.end_date) return `${startLabel} – now`;

  const end = new Date(trip.end_date + "T00:00:00");
  const endLabel = end.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  return `${startLabel} – ${endLabel}`;
}

function progressColor(percentage: number): string {
  if (percentage > 100) return "var(--app-danger)";
  if (percentage >= 80) return "#f59e0b";
  return "var(--app-accent)";
}

export function TripCard({ trip, onOpen }: TripCardProps) {
  const { format, formatLive } = useCurrency();

  const total = format({ base: trip.total_base, default: trip.total_default });
  const perDay = format({ base: trip.daily_average, default: trip.daily_average_default });
  const percentage = trip.budget_percentage ?? 0;

  return (
    <button
      type="button"
      onClick={() => onOpen(trip)}
      className="w-full text-left card"
      style={{
        background: "var(--app-card-bg)",
        border: trip.is_active
          ? "1px solid var(--app-accent)"
          : "1px solid var(--app-border)",
        cursor: "pointer",
      }}
    >
      <div className="flex items-start gap-3">
        <span className="text-2xl leading-none flex-shrink-0">{trip.emoji}</span>

        <div className="flex-1 min-w-0">
          <p
            className="text-sm font-semibold truncate flex items-center gap-2"
            style={{ color: "var(--app-text-primary)" }}
          >
            <span className="truncate">{trip.name}</span>
            {trip.is_active && (
              <span
                className="text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0"
                style={{
                  background: "color-mix(in srgb, var(--app-accent) 20%, transparent)",
                  color: "var(--app-accent)",
                  fontWeight: 600,
                }}
              >
                active
              </span>
            )}
          </p>
          <p className="text-xs mt-0.5" style={{ color: "var(--app-text-secondary)" }}>
            {formatTripRange(trip)} · {trip.days} {trip.days === 1 ? "day" : "days"}
          </p>
        </div>

        <div className="text-right flex-shrink-0">
          <p className="amount text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
            {total}
          </p>
          <p className="text-[11px]" style={{ color: "var(--app-text-secondary)" }}>
            {perDay}/day
          </p>
        </div>
      </div>

      {trip.budget !== null && (
        <div className="mt-3">
          <div
            className="h-1.5 rounded-full overflow-hidden"
            style={{ background: "var(--app-secondary-bg)" }}
          >
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.min(percentage, 100)}%`,
                background: progressColor(percentage),
                transition: "width 0.3s ease",
              }}
            />
          </div>
          <p className="text-[11px] mt-1" style={{ color: "var(--app-text-secondary)" }}>
            {percentage.toFixed(0)}% of {formatLive(trip.budget, 0)}
            {trip.budget_remaining !== null && trip.budget_remaining < 0 && (
              <span style={{ color: "var(--app-danger)" }}>
                {" "}· over by {formatLive(Math.abs(trip.budget_remaining), 0)}
              </span>
            )}
          </p>
        </div>
      )}

      {trip.transaction_count === 0 && (
        <p className="text-[11px] mt-2" style={{ color: "var(--app-text-secondary)" }}>
          No expenses yet — open the trip to pull in existing ones.
        </p>
      )}
    </button>
  );
}
