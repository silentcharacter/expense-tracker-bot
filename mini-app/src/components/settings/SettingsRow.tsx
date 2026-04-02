/** Generic settings list row with icon, label, subtitle, and right-side slot. */

import type { ReactNode } from "react";

interface SettingsRowProps {
  icon: string;
  label: string;
  subtitle?: string;
  right?: ReactNode;
  onClick?: () => void;
  danger?: boolean;
  disabled?: boolean;
}

export function SettingsRow({
  icon,
  label,
  subtitle,
  right,
  onClick,
  danger = false,
  disabled = false,
}: SettingsRowProps) {
  const labelColor = danger ? "var(--app-danger)" : "var(--app-text-primary)";

  return (
    <button
      className="w-full flex items-center gap-3 py-3 text-left disabled:opacity-50"
      onClick={onClick}
      disabled={disabled || !onClick}
      style={{ cursor: onClick && !disabled ? "pointer" : "default", background: "transparent" }}
    >
      <div
        className="flex items-center justify-center rounded-xl text-lg flex-shrink-0"
        style={{
          width: 40,
          height: 40,
          background: danger
            ? "color-mix(in srgb, var(--app-danger) 15%, transparent)"
            : "var(--app-secondary-bg)",
        }}
      >
        {icon}
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium leading-snug" style={{ color: labelColor }}>
          {label}
        </p>
        {subtitle && (
          <p className="text-xs mt-0.5 truncate" style={{ color: "var(--app-text-secondary)" }}>
            {subtitle}
          </p>
        )}
      </div>

      {right !== undefined ? (
        <div className="flex-shrink-0">{right}</div>
      ) : onClick ? (
        <svg
          width={16}
          height={16}
          viewBox="0 0 16 16"
          fill="none"
          className="flex-shrink-0"
          style={{ color: "var(--app-text-secondary)" }}
        >
          <path d="M6 3l5 5-5 5" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : null}
    </button>
  );
}
