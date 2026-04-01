import { type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTelegram } from "../../hooks/useTelegram";

const iconProps = { width: 20, height: 20, fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

function GridIcon() {
  return (
    <svg {...iconProps} viewBox="0 0 24 24">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  );
}

function TrendUpIcon() {
  return (
    <svg {...iconProps} viewBox="0 0 24 24">
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
      <polyline points="16 7 22 7 22 13" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg {...iconProps} viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="9" />
      <polyline points="12 7 12 12 15.5 14" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg {...iconProps} viewBox="0 0 24 24">
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

interface Tab {
  path: string;
  label: string;
  icon: ReactNode;
}

const TABS: Tab[] = [
  { path: "/", label: "Overview", icon: <GridIcon /> },
  { path: "/analytics", label: "Analytics", icon: <TrendUpIcon /> },
  { path: "/budget", label: "Budget", icon: <ClockIcon /> },
  { path: "/settings", label: "Settings", icon: <SettingsIcon /> },
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
            className="flex flex-1 flex-col items-center justify-center gap-1 text-xs transition-opacity active:opacity-60"
            style={{
              color: isActive
                ? "var(--tg-theme-button-color, var(--app-accent))"
                : "var(--tg-theme-hint-color, var(--app-text-secondary))",
              background: "none",
              border: "none",
              cursor: "pointer",
            }}
          >
            {tab.icon}
            <span className={isActive ? "font-medium" : ""}>{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
