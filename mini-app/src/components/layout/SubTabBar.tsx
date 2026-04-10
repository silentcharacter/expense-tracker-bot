/** Pill-style sub-tab bar for MainPage: Overview / Trends / Budget. */

import { useTelegram } from "../../hooks/useTelegram";

export type SubTab = "overview" | "trends" | "budget";

interface SubTabBarProps {
  active: SubTab;
  onChange: (tab: SubTab) => void;
}

const TABS: { key: SubTab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "trends", label: "Trends" },
  { key: "budget", label: "Budget" },
];

export function SubTabBar({ active, onChange }: SubTabBarProps) {
  const { hapticFeedback } = useTelegram();

  function handleClick(tab: SubTab) {
    if (tab === active) return;
    hapticFeedback?.selectionChanged();
    onChange(tab);
  }

  return (
    <div
      className="flex rounded-full p-1 mb-3"
      style={{ backgroundColor: "var(--app-secondary-bg)" }}
      role="tablist"
    >
      {TABS.map((tab) => {
        const isActive = tab.key === active;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => handleClick(tab.key)}
            className="flex-1 text-sm font-semibold py-2 rounded-full transition-colors"
            style={{
              backgroundColor: isActive ? "var(--app-card-bg)" : "transparent",
              color: isActive ? "var(--app-text-primary)" : "var(--app-text-secondary)",
              border: "none",
              cursor: "pointer",
              boxShadow: isActive ? "0 1px 3px rgba(0, 0, 0, 0.1)" : "none",
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
