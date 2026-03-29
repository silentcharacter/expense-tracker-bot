import { useLocation, useNavigate } from "react-router-dom";
import { useTelegram } from "../../hooks/useTelegram";

interface Tab {
  path: string;
  label: string;
  icon: string;
}

const TABS: Tab[] = [
  { path: "/", label: "Overview", icon: "📊" },
  { path: "/analytics", label: "Analytics", icon: "📈" },
  { path: "/budget", label: "Budget", icon: "💰" },
  { path: "/settings", label: "Settings", icon: "⚙️" },
];

export function TabBar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { hapticFeedback } = useTelegram();

  function handleTabPress(tab: Tab) {
    if (location.pathname === tab.path) return;
    hapticFeedback?.selectionChanged();
    void navigate(tab.path);
  }

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-10 flex"
      style={{
        height: "56px",
        backgroundColor: "var(--tg-theme-secondary-bg-color, var(--app-secondary-bg))",
        borderTop: "1px solid var(--app-border)",
      }}
    >
      {TABS.map((tab) => {
        const isActive = location.pathname === tab.path;
        return (
          <button
            key={tab.path}
            onClick={() => handleTabPress(tab)}
            className="flex flex-1 flex-col items-center justify-center gap-0.5 text-xs transition-opacity active:opacity-60"
            style={{
              color: isActive
                ? "var(--tg-theme-button-color, var(--app-accent))"
                : "var(--tg-theme-hint-color, var(--app-text-secondary))",
              background: "none",
              border: "none",
              cursor: "pointer",
            }}
          >
            <span className="text-lg leading-none">{tab.icon}</span>
            <span className={isActive ? "font-medium" : ""}>{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
