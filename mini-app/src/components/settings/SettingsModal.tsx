/** Full-screen slide-in modal wrapping the existing SettingsPage. */

import { useEffect } from "react";
import { SettingsPage } from "../../pages/SettingsPage";
import { useTelegram } from "../../hooks/useTelegram";

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
}

function CloseIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

export function SettingsModal({ open, onClose }: SettingsModalProps) {
  const { hapticFeedback } = useTelegram();

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  function handleClose() {
    hapticFeedback?.impactOccurred("light");
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 settings-modal"
      style={{ backgroundColor: "var(--app-bg)", color: "var(--app-text-primary)" }}
      role="dialog"
      aria-modal="true"
      aria-label="Settings"
    >
      <div
        className="flex items-center justify-between px-4 pt-3 pb-2"
        style={{
          borderBottom: "1px solid var(--app-border)",
          backgroundColor: "var(--app-secondary-bg)",
        }}
      >
        <h2 className="text-lg font-semibold">Settings</h2>
        <button
          type="button"
          onClick={handleClose}
          className="flex items-center justify-center rounded-full"
          style={{
            width: 36,
            height: 36,
            backgroundColor: "var(--app-card-bg)",
            color: "var(--app-text-primary)",
            border: "none",
            cursor: "pointer",
          }}
          aria-label="Close settings"
        >
          <CloseIcon />
        </button>
      </div>

      <div
        className="overflow-y-auto"
        style={{
          position: "absolute",
          top: 56,
          left: 0,
          right: 0,
          bottom: 0,
          WebkitOverflowScrolling: "touch",
          padding: "0 16px",
        }}
      >
        <SettingsPage />
      </div>
    </div>
  );
}
