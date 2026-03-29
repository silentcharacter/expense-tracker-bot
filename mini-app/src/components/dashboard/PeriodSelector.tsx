import type { Period } from "../../api/summary";
import { useTelegram } from "../../hooks/useTelegram";

const PERIODS: { value: Period; label: string }[] = [
  { value: "week", label: "Week" },
  { value: "month", label: "Month" },
  { value: "year", label: "Year" },
];

interface PeriodSelectorProps {
  value: Period;
  onChange: (period: Period) => void;
}

export function PeriodSelector({ value, onChange }: PeriodSelectorProps) {
  const { hapticFeedback } = useTelegram();

  function handleSelect(period: Period) {
    if (period === value) return;
    hapticFeedback?.impactOccurred("light");
    onChange(period);
  }

  return (
    <div
      className="flex rounded-xl p-1 mb-3"
      style={{ backgroundColor: "var(--app-secondary-bg)" }}
    >
      {PERIODS.map(({ value: p, label }) => {
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
            {label}
          </button>
        );
      })}
    </div>
  );
}
