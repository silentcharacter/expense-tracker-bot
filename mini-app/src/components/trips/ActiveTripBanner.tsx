/** Compact banner on Overview showing the trip that new expenses are tagged with. */

import type { TripEntry } from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";

interface ActiveTripBannerProps {
  trip: TripEntry;
  onOpen: () => void;
}

export function ActiveTripBanner({ trip, onOpen }: ActiveTripBannerProps) {
  const { format, formatLive } = useCurrency();

  const spent = format({ base: trip.total_base, default: trip.total_default });
  const dayLabel = trip.total_days
    ? `Day ${trip.days} of ${trip.total_days}`
    : `Day ${trip.days}`;

  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full text-left card flex items-center gap-3"
      style={{
        background: "color-mix(in srgb, var(--app-accent) 12%, var(--app-card-bg))",
        border: "1px solid var(--app-accent)",
        cursor: "pointer",
      }}
    >
      <span className="text-xl leading-none flex-shrink-0">{trip.emoji}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold truncate" style={{ color: "var(--app-text-primary)" }}>
          {trip.name}
        </p>
        <p className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
          {dayLabel} · new expenses are tagged with this trip
        </p>
      </div>
      <div className="text-right flex-shrink-0">
        <p className="amount text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
          {spent}
        </p>
        {trip.budget !== null && (
          <p className="text-[11px]" style={{ color: "var(--app-text-secondary)" }}>
            of {formatLive(trip.budget, 0)}
          </p>
        )}
      </div>
    </button>
  );
}
