import type { Period } from "../../api/summary";
import { useTelegram } from "../../hooks/useTelegram";

const PERIODS: { value: Period; label: string }[] = [
  { value: "today", label: "Day" },
  { value: "week", label: "Week" },
  { value: "month", label: "Month" },
];

function formatPeriodLabel(
  period: Period,
  offset: number,
  dateRange?: { start: string; end: string }
): string {
  if (offset === 0) {
    if (period === "today") return "Today";
    if (period === "week") return "This week";
    if (period === "month") {
      const now = new Date();
      return now.toLocaleString("en", { month: "long", year: "numeric" });
    }
    return "";
  }

  if (!dateRange) return "";

  const start = new Date(dateRange.start + "T00:00:00");
  const end = new Date(dateRange.end + "T00:00:00");

  if (period === "today") {
    if (offset === -1) return "Yesterday";
    return start.toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" });
  }

  if (period === "week") {
    const startStr = start.toLocaleDateString("en", { month: "short", day: "numeric" });
    const endStr = end.toLocaleDateString("en", { month: "short", day: "numeric" });
    return `${startStr} – ${endStr}`;
  }

  if (period === "month") {
    return start.toLocaleString("en", { month: "long", year: "numeric" });
  }

  return "";
}

interface PeriodSelectorProps {
  value: Period;
  onChange: (period: Period) => void;
  offset: number;
  onOffsetChange: (offset: number) => void;
  dateRange?: { start: string; end: string };
}

export function PeriodSelector({
  value,
  onChange,
  offset,
  onOffsetChange,
  dateRange,
}: PeriodSelectorProps) {
  const { hapticFeedback } = useTelegram();

  function handleSelect(period: Period) {
    if (period === value) return;
    hapticFeedback?.impactOccurred("light");
    onChange(period);
  }

  function handlePrev() {
    hapticFeedback?.impactOccurred("light");
    onOffsetChange(offset - 1);
  }

  function handleNext() {
    if (offset >= 0) return;
    hapticFeedback?.impactOccurred("light");
    onOffsetChange(offset + 1);
  }

  const label = formatPeriodLabel(value, offset, dateRange);

  return (
    <div className="mb-3">
      <div
        className="flex rounded-xl p-1 mb-2"
        style={{ backgroundColor: "var(--app-secondary-bg)" }}
      >
        {PERIODS.map(({ value: p, label: tabLabel }) => {
          const isActive = p === value;
          return (
            <button
              key={p}
              onClick={() => handleSelect(p)}
              className="flex-1 py-1.5 text-sm font-medium rounded-lg transition-colors"
              style={
                isActive
                  ? {
                      backgroundColor: "var(--app-accent)",
                      color: "var(--tg-theme-button-text-color, #ffffff)",
                    }
                  : {
                      color: "var(--app-text-secondary)",
                    }
              }
            >
              {tabLabel}
            </button>
          );
        })}
      </div>

      <div className="flex items-center justify-between px-1">
        <button
          onClick={handlePrev}
          className="p-1 rounded-lg transition-opacity"
          style={{ color: "var(--app-text-secondary)" }}
          aria-label="Previous period"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>

        <span
          className="text-sm font-medium"
          style={{ color: "var(--app-text-primary)" }}
        >
          {label}
        </span>

        <button
          onClick={handleNext}
          className="p-1 rounded-lg transition-opacity"
          style={{
            color: "var(--app-text-secondary)",
            opacity: offset < 0 ? 1 : 0,
            pointerEvents: offset < 0 ? "auto" : "none",
          }}
          aria-label="Next period"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>
      </div>
    </div>
  );
}
