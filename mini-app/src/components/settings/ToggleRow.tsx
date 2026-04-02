/** Settings row with an iOS-style toggle switch on the right. */

import { SettingsRow } from "./SettingsRow";

interface ToggleRowProps {
  icon: string;
  label: string;
  subtitle?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
}

export function ToggleRow({ icon, label, subtitle, checked, disabled, onChange }: ToggleRowProps) {
  return (
    <SettingsRow
      icon={icon}
      label={label}
      subtitle={subtitle}
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      right={<Toggle checked={checked} disabled={disabled} />}
    />
  );
}

function Toggle({ checked, disabled }: { checked: boolean; disabled?: boolean }) {
  return (
    <div
      className="relative flex-shrink-0"
      style={{
        width: 44,
        height: 26,
        borderRadius: 13,
        background: checked
          ? "var(--app-accent)"
          : "color-mix(in srgb, var(--app-text-secondary) 30%, transparent)",
        opacity: disabled ? 0.5 : 1,
        transition: "background 0.2s ease",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 3,
          left: checked ? 21 : 3,
          width: 20,
          height: 20,
          borderRadius: "50%",
          background: "#ffffff",
          boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
          transition: "left 0.2s ease",
        }}
      />
    </div>
  );
}
