/** Settings page — profile, currencies, data export, notifications, account. */

import { useState } from "react";
import { useUser } from "../context/UserContext";
import { updateSettings, exportExpenses, clearAllExpenses } from "../api/settings";
import { SettingsRow } from "../components/settings/SettingsRow";
import { ToggleRow } from "../components/settings/ToggleRow";
import { CurrencyPickerModal } from "../components/settings/CurrencyPickerModal";
import { ConfirmDialog } from "../components/settings/ConfirmDialog";
import { SkeletonLine } from "../components/shared/Skeleton";
import type { UserSettings } from "../api/types";

const APP_VERSION = "1.0.0";

// ── Avatar ────────────────────────────────────────────────────────────────────

function Avatar({ name }: { name: string }) {
  const initials = name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <div
      className="flex items-center justify-center rounded-full text-white font-bold text-xl flex-shrink-0"
      style={{
        width: 64,
        height: 64,
        background: "linear-gradient(135deg, #6c3fc5 0%, #4a1fa0 100%)",
      }}
    >
      {initials}
    </div>
  );
}

// ── Section header ────────────────────────────────────────────────────────────

function SectionHeader({ label }: { label: string }) {
  return (
    <p
      className="text-xs font-semibold uppercase tracking-widest px-1 mt-5 mb-1"
      style={{ color: "var(--app-text-secondary)" }}
    >
      {label}
    </p>
  );
}

// ── Date range picker (inline) ────────────────────────────────────────────────

function DateRangePicker({
  onExport,
  onCancel,
}: {
  onExport: (start: string, end: string) => void;
  onCancel: () => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const firstOfMonth = today.slice(0, 8) + "01";
  const [start, setStart] = useState(firstOfMonth);
  const [end, setEnd] = useState(today);

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col justify-end"
      style={{ background: "rgba(0,0,0,0.5)" }}
      onClick={(e) => e.target === e.currentTarget && onCancel()}
    >
      <div
        className="rounded-t-2xl p-5 flex flex-col gap-4"
        style={{ background: "var(--app-bg)" }}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
            Export range
          </p>
          <button className="text-sm" style={{ color: "var(--app-accent)" }} onClick={onCancel}>
            Cancel
          </button>
        </div>

        <div className="flex flex-col gap-3">
          <div>
            <label className="text-xs mb-1 block" style={{ color: "var(--app-text-secondary)" }}>
              Start date
            </label>
            <input
              type="date"
              value={start}
              max={end}
              onChange={(e) => setStart(e.target.value)}
              className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
              style={{
                background: "var(--app-secondary-bg)",
                color: "var(--app-text-primary)",
                border: "1px solid var(--app-border)",
              }}
            />
          </div>
          <div>
            <label className="text-xs mb-1 block" style={{ color: "var(--app-text-secondary)" }}>
              End date
            </label>
            <input
              type="date"
              value={end}
              min={start}
              max={today}
              onChange={(e) => setEnd(e.target.value)}
              className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
              style={{
                background: "var(--app-secondary-bg)",
                color: "var(--app-text-primary)",
                border: "1px solid var(--app-border)",
              }}
            />
          </div>
        </div>

        <button
          onClick={() => onExport(start, end)}
          className="w-full py-3.5 rounded-xl text-sm font-semibold"
          style={{ background: "var(--app-accent)", color: "#fff" }}
        >
          Export CSV
        </button>
      </div>
    </div>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function SettingsSkeleton() {
  return (
    <div className="page-content py-4 flex flex-col gap-3">
      <div className="card flex items-center gap-4">
        <div className="rounded-full skeleton flex-shrink-0" style={{ width: 64, height: 64 }} />
        <div className="flex-1 flex flex-col gap-2">
          <SkeletonLine height={16} width="60%" />
          <SkeletonLine height={12} width="45%" />
        </div>
      </div>
      {[1, 2, 3].map((i) => (
        <div key={i} className="card flex flex-col gap-3">
          <SkeletonLine height={12} width="30%" />
          <SkeletonLine height={44} />
          <SkeletonLine height={44} />
        </div>
      ))}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

type CurrencyField = "base_currency" | "default_currency";
type Dialog = "clear" | "delete" | null;

export function SettingsPage() {
  const { user, isLoading, refreshUser } = useUser();

  // Local optimistic copy of mutable settings while saves are in flight
  const [local, setLocal] = useState<Partial<UserSettings>>({});

  // UI state
  const [currencyPicker, setCurrencyPicker] = useState<CurrencyField | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [showDateRange, setShowDateRange] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [clearLoading, setClearLoading] = useState(false);
  const [savingField, setSavingField] = useState<string | null>(null);

  if (isLoading && !user) return <SettingsSkeleton />;
  if (!user) {
    return (
      <div className="page-content py-4">
        <div className="card text-center py-8">
          <p className="text-sm" style={{ color: "var(--app-text-secondary)" }}>
            Could not load settings. Please try again.
          </p>
        </div>
      </div>
    );
  }

  // Merge server data with any in-flight local overrides
  const settings: UserSettings = { ...user, ...local };

  // ── Helpers ────────────────────────────────────────────────────────────────

  async function saveField(field: string, patch: Partial<UserSettings>) {
    setSavingField(field);
    setLocal((prev) => ({ ...prev, ...patch }));
    try {
      const updated = await updateSettings(patch);
      setLocal({});
      await refreshUser();
      // Keep updated values from server response (prevents flicker)
      void updated;
    } catch {
      // Roll back optimistic change
      setLocal((prev) => {
        const rolled = { ...prev };
        for (const k of Object.keys(patch)) delete rolled[k as keyof UserSettings];
        return rolled;
      });
    } finally {
      setSavingField(null);
    }
  }

  async function handleCurrencySelect(field: CurrencyField, code: string) {
    setCurrencyPicker(null);
    await saveField(field, { [field]: code } as Partial<UserSettings>);
  }

  async function handleToggle(field: "budget_alerts" | "weekly_summary" | "insights", value: boolean) {
    await saveField(field, { [field]: value } as Partial<UserSettings>);
  }

  async function handleExport(start?: string, end?: string) {
    setExportLoading(true);
    setShowDateRange(false);
    try {
      await exportExpenses(start && end ? { start, end } : undefined);
    } finally {
      setExportLoading(false);
    }
  }

  async function handleClearAll() {
    setClearLoading(true);
    try {
      await clearAllExpenses();
      setDialog(null);
      await refreshUser();
    } finally {
      setClearLoading(false);
    }
  }

  function handleDeleteAccount() {
    setDialog(null);
    // Direct to the bot to handle account deletion via Telegram deep-link
    const botUsername = import.meta.env.VITE_BOT_USERNAME as string | undefined;
    if (botUsername) {
      window.open(`https://t.me/${botUsername}?start=deleteaccount`, "_blank");
    }
  }

  const spreadsheetUrl = settings.spreadsheet_id
    ? `https://docs.google.com/spreadsheets/d/${settings.spreadsheet_id}`
    : null;

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="page-content py-4 flex flex-col">

      {/* ── Profile header ─────────────────────────────────────────────────── */}
      <div className="card flex items-center gap-4">
        <Avatar name={settings.display_name} />
        <div className="flex-1 min-w-0">
          <p className="text-base font-semibold truncate" style={{ color: "var(--app-text-primary)" }}>
            {settings.display_name}
          </p>
          {settings.username && (
            <p className="text-xs mt-0.5 truncate" style={{ color: "var(--app-text-secondary)" }}>
              @{settings.username}
            </p>
          )}
          {settings.email ? (
            <span
              className="inline-flex items-center gap-1 mt-1.5 px-2 py-0.5 rounded-full text-xs font-medium"
              style={{ background: "color-mix(in srgb, #22c55e 15%, transparent)", color: "#22c55e" }}
            >
              <svg width={10} height={10} viewBox="0 0 10 10" fill="none">
                <path d="M2 5l2.5 2.5L8 3" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Google Sheets linked
            </span>
          ) : (
            <span
              className="inline-flex items-center gap-1 mt-1.5 px-2 py-0.5 rounded-full text-xs font-medium"
              style={{ background: "color-mix(in srgb, var(--app-text-secondary) 15%, transparent)", color: "var(--app-text-secondary)" }}
            >
              Not linked
            </span>
          )}
        </div>
      </div>

      {/* ── Currencies ─────────────────────────────────────────────────────── */}
      <SectionHeader label="Currencies" />
      <div className="card">
        <div className="flex flex-col divide-y" style={{ borderColor: "var(--app-border)" }}>
          <SettingsRow
            icon="💱"
            label="Base currency"
            subtitle="Used for analytics and budgets"
            onClick={() => setCurrencyPicker("base_currency")}
            right={
              <span
                className="text-xs font-bold px-2.5 py-1 rounded-lg"
                style={{ background: "var(--app-accent)", color: "#fff", opacity: savingField === "base_currency" ? 0.6 : 1 }}
              >
                {settings.base_currency}
              </span>
            }
          />
          <SettingsRow
            icon="🏦"
            label="Default currency"
            subtitle="Used when currency not specified"
            onClick={() => setCurrencyPicker("default_currency")}
            right={
              <span
                className="text-xs font-bold px-2.5 py-1 rounded-lg"
                style={{ background: "color-mix(in srgb, var(--app-accent) 20%, transparent)", color: "var(--app-accent)", opacity: savingField === "default_currency" ? 0.6 : 1 }}
              >
                {settings.default_currency}
              </span>
            }
          />
        </div>
      </div>

      {/* ── Data ───────────────────────────────────────────────────────────── */}
      <SectionHeader label="Data" />
      <div className="card">
        <div className="flex flex-col divide-y" style={{ borderColor: "var(--app-border)" }}>
          <SettingsRow
            icon="📊"
            label="Google Sheets"
            subtitle={settings.email ? `Expenses — ${settings.display_name}` : "Not linked"}
            onClick={spreadsheetUrl ? () => window.open(spreadsheetUrl, "_blank") : undefined}
            right={
              spreadsheetUrl ? (
                <span className="text-sm font-medium" style={{ color: "var(--app-accent)" }}>
                  Open ↗
                </span>
              ) : undefined
            }
          />
          <SettingsRow
            icon="📥"
            label="Export CSV"
            subtitle="Download current month"
            onClick={exportLoading ? undefined : () => handleExport()}
            right={
              exportLoading ? (
                <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
                  Downloading…
                </span>
              ) : undefined
            }
          />
          <SettingsRow
            icon="📅"
            label="Export range"
            subtitle="Choose custom date range"
            onClick={() => setShowDateRange(true)}
          />
        </div>
      </div>

      {/* ── Notifications ──────────────────────────────────────────────────── */}
      <SectionHeader label="Notifications" />
      <div className="card">
        <div className="flex flex-col divide-y" style={{ borderColor: "var(--app-border)" }}>
          <ToggleRow
            icon="🔔"
            label="Budget alerts"
            subtitle="Notify when reaching 80%"
            checked={settings.budget_alerts}
            disabled={savingField === "budget_alerts"}
            onChange={(v) => handleToggle("budget_alerts", v)}
          />
          <ToggleRow
            icon="📈"
            label="Weekly summary"
            subtitle="Every Monday morning"
            checked={settings.weekly_summary}
            disabled={savingField === "weekly_summary"}
            onChange={(v) => handleToggle("weekly_summary", v)}
          />
          <ToggleRow
            icon="💡"
            label="Insights"
            subtitle="Spending pattern tips"
            checked={settings.insights}
            disabled={savingField === "insights"}
            onChange={(v) => handleToggle("insights", v)}
          />
        </div>
      </div>

      {/* ── Account ────────────────────────────────────────────────────────── */}
      <SectionHeader label="Account" />
      <div className="card">
        <div className="flex flex-col divide-y" style={{ borderColor: "var(--app-border)" }}>
          <SettingsRow
            icon="🗑️"
            label="Clear all expenses"
            subtitle="Permanently delete all transactions"
            onClick={() => setDialog("clear")}
            danger
          />
          <SettingsRow
            icon="⚠️"
            label="Delete account"
            subtitle="Remove your account and data"
            onClick={() => setDialog("delete")}
            danger
          />
        </div>
      </div>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <p className="text-center text-xs py-4" style={{ color: "var(--app-text-secondary)" }}>
        Expense Tracker · v{APP_VERSION}
      </p>

      {/* ── Modals ─────────────────────────────────────────────────────────── */}

      {currencyPicker && (
        <CurrencyPickerModal
          title={currencyPicker === "base_currency" ? "Base Currency" : "Default Currency"}
          current={settings[currencyPicker]}
          onSelect={(code) => handleCurrencySelect(currencyPicker, code)}
          onCancel={() => setCurrencyPicker(null)}
        />
      )}

      {showDateRange && (
        <DateRangePicker
          onExport={(start, end) => handleExport(start, end)}
          onCancel={() => setShowDateRange(false)}
        />
      )}

      {dialog === "clear" && (
        <ConfirmDialog
          title="Clear all expenses?"
          message="This will permanently delete all your transactions. Your budgets and categories will remain. This action cannot be undone."
          confirmLabel="Clear all expenses"
          danger
          loading={clearLoading}
          onConfirm={handleClearAll}
          onCancel={() => setDialog(null)}
        />
      )}

      {dialog === "delete" && (
        <ConfirmDialog
          title="Delete account?"
          message="This will remove your account and all associated data. You will be redirected to the bot to confirm this action."
          confirmLabel="Continue in bot"
          danger
          onConfirm={handleDeleteAccount}
          onCancel={() => setDialog(null)}
        />
      )}
    </div>
  );
}
