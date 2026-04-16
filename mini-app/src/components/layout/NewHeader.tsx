/** Fixed app header: month label + day counter, currency toggle, settings gear.
 *
 * Replaces the old routed Header. Lives at the top of `MainPage` above the
 * summary card and sub-tabs.
 */

import { useCurrency } from "../../context/CurrencyContext";
import { useTelegram } from "../../hooks/useTelegram";
import { getCurrencySymbol } from "../../utils/currency";

interface NewHeaderProps {
  /** Day of month, 1-based. */
  dayOfMonth: number;
  /** Total days in the current month. */
  daysInMonth: number;
  /** 0 = current month, -1 = previous, etc. */
  monthOffset: number;
  /** Change the viewed month. */
  onMonthOffsetChange: (offset: number) => void;
  /** Opens the settings modal. */
  onOpenSettings: () => void;
}

function GearIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

export function NewHeader({
  dayOfMonth,
  daysInMonth,
  monthOffset,
  onMonthOffsetChange,
  onOpenSettings,
}: NewHeaderProps) {
  const { displayMode, baseCurrency, defaultCurrency, setMode } = useCurrency();
  const { hapticFeedback } = useTelegram();

  const now = new Date();
  const viewed = new Date(now.getFullYear(), now.getMonth() + monthOffset, 1);
  const monthLabel = viewed.toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
  const isCurrentMonth = monthOffset === 0;

  const sameCurrency = baseCurrency.toUpperCase() === defaultCurrency.toUpperCase();

  function handleToggle(mode: "base" | "default") {
    if (displayMode === mode) return;
    hapticFeedback?.selectionChanged();
    setMode(mode);
  }

  function handleSettings() {
    hapticFeedback?.impactOccurred("light");
    onOpenSettings();
  }

  function handlePrev() {
    hapticFeedback?.impactOccurred("light");
    onMonthOffsetChange(monthOffset - 1);
  }

  function handleNext() {
    if (monthOffset >= 0) return;
    hapticFeedback?.impactOccurred("light");
    onMonthOffsetChange(monthOffset + 1);
  }

  return (
    <header
      className="flex items-center justify-between pt-3 pb-2"
      style={{ color: "var(--app-text-primary)" }}
    >
      <div className="flex items-center gap-1 min-w-0">
        <button
          type="button"
          onClick={handlePrev}
          className="flex items-center justify-center rounded-full"
          style={{
            width: 28,
            height: 28,
            background: "transparent",
            color: "var(--app-text-secondary)",
            border: "none",
            cursor: "pointer",
            flexShrink: 0,
          }}
          aria-label="Previous month"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <div className="min-w-0">
          <h1 className="text-lg font-semibold leading-tight truncate">{monthLabel}</h1>
          {isCurrentMonth ? (
            <p className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
              Day {dayOfMonth} of {daysInMonth}
            </p>
          ) : (
            <p className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
              Full month
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={handleNext}
          disabled={monthOffset >= 0}
          className="flex items-center justify-center rounded-full"
          style={{
            width: 28,
            height: 28,
            background: "transparent",
            color: "var(--app-text-secondary)",
            border: "none",
            cursor: monthOffset < 0 ? "pointer" : "default",
            opacity: monthOffset < 0 ? 1 : 0.3,
            flexShrink: 0,
          }}
          aria-label="Next month"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>
      </div>

      <div className="flex items-center gap-2">
        {!sameCurrency && (
          <div
            className="flex rounded-full p-0.5 text-xs font-semibold"
            style={{ backgroundColor: "var(--app-secondary-bg)" }}
          >
            <button
              type="button"
              onClick={() => handleToggle("base")}
              className="px-3 py-1 rounded-full transition-colors"
              style={{
                backgroundColor: displayMode === "base" ? "var(--app-card-bg)" : "transparent",
                color:
                  displayMode === "base"
                    ? "var(--app-text-primary)"
                    : "var(--app-text-secondary)",
                border: "none",
                cursor: "pointer",
              }}
              aria-pressed={displayMode === "base"}
            >
              {getCurrencySymbol(baseCurrency)}
            </button>
            <button
              type="button"
              onClick={() => handleToggle("default")}
              className="px-3 py-1 rounded-full transition-colors"
              style={{
                backgroundColor:
                  displayMode === "default" ? "var(--app-card-bg)" : "transparent",
                color:
                  displayMode === "default"
                    ? "var(--app-text-primary)"
                    : "var(--app-text-secondary)",
                border: "none",
                cursor: "pointer",
              }}
              aria-pressed={displayMode === "default"}
            >
              {getCurrencySymbol(defaultCurrency)}
            </button>
          </div>
        )}

        <button
          type="button"
          onClick={handleSettings}
          className="flex items-center justify-center rounded-full"
          style={{
            width: 36,
            height: 36,
            backgroundColor: "var(--app-secondary-bg)",
            color: "var(--app-text-primary)",
            border: "none",
            cursor: "pointer",
          }}
          aria-label="Open settings"
        >
          <GearIcon />
        </button>
      </div>
    </header>
  );
}
