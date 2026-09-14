/** Create / edit a trip: name, emoji, dates, optional destination currency and budget. */

import { useState } from "react";
import type { CreateTripRequest, TripEntry, UpdateTripRequest } from "../../api/types";

interface TripFormModalProps {
  /** Omit to create a new trip. */
  trip?: TripEntry;
  onCreate?: (data: CreateTripRequest) => Promise<void>;
  onUpdate?: (data: UpdateTripRequest) => Promise<void>;
  onClose: () => void;
}

const EMOJI_OPTIONS = ["🧳", "✈️", "🏝️", "🏔️", "🚗", "⛺️", "🚆", "🛳️"];

function todayIso(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(
    now.getDate(),
  ).padStart(2, "0")}`;
}

export function TripFormModal({ trip, onCreate, onUpdate, onClose }: TripFormModalProps) {
  const isEdit = trip !== undefined;

  const [name, setName] = useState(trip?.name ?? "");
  const [emoji, setEmoji] = useState(trip?.emoji ?? "🧳");
  const [startDate, setStartDate] = useState(trip?.start_date ?? todayIso());
  const [endDate, setEndDate] = useState(trip?.end_date ?? "");
  const [tripCurrency, setTripCurrency] = useState(trip?.trip_currency ?? "");
  const [budget, setBudget] = useState(trip?.budget != null ? String(trip.budget) : "");
  const [assignExisting, setAssignExisting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const datesValid = !endDate || endDate >= startDate;
  const valid = name.trim().length > 0 && !!startDate && datesValid;

  async function submit() {
    if (!valid) return;
    setSaving(true);
    setError(null);
    try {
      const common = {
        name: name.trim(),
        emoji,
        start_date: startDate,
        end_date: endDate || null,
        trip_currency: tripCurrency.trim().toUpperCase(),
        budget: budget.trim() ? parseFloat(budget) : null,
      };
      if (isEdit) {
        await onUpdate?.(common);
      } else {
        await onCreate?.({ ...common, assign_existing: assignExisting });
      }
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save the trip");
    } finally {
      setSaving(false);
    }
  }

  const inputStyle = {
    background: "var(--app-secondary-bg)",
    color: "var(--app-text-primary)",
    border: "1px solid var(--app-border)",
  } as const;

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col justify-end"
      style={{ background: "rgba(0,0,0,0.5)" }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="rounded-t-2xl p-4 flex flex-col gap-3 max-h-[90vh] overflow-y-auto"
        style={{ background: "var(--app-bg)" }}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
            {isEdit ? "Edit trip" : "New trip"}
          </p>
          <button
            type="button"
            className="text-xs px-2 py-1 rounded"
            style={{ color: "var(--app-text-secondary)", border: "none", background: "transparent" }}
            onClick={onClose}
          >
            Cancel
          </button>
        </div>

        <input
          type="text"
          placeholder="Trip name, e.g. Georgia"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
          maxLength={60}
          className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
          style={inputStyle}
        />

        <div className="flex gap-2 flex-wrap">
          {EMOJI_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setEmoji(option)}
              className="w-10 h-10 rounded-xl text-lg"
              style={{
                background:
                  option === emoji ? "color-mix(in srgb, var(--app-accent) 20%, transparent)" : "var(--app-secondary-bg)",
                border: option === emoji ? "1px solid var(--app-accent)" : "1px solid var(--app-border)",
                cursor: "pointer",
              }}
            >
              {option}
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          <label className="flex-1">
            <span className="text-[11px] px-1" style={{ color: "var(--app-text-secondary)" }}>
              Start
            </span>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
              style={inputStyle}
            />
          </label>
          <label className="flex-1">
            <span className="text-[11px] px-1" style={{ color: "var(--app-text-secondary)" }}>
              End (optional)
            </span>
            <input
              type="date"
              value={endDate}
              min={startDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
              style={inputStyle}
            />
          </label>
        </div>

        <p className="text-[11px] px-1" style={{ color: "var(--app-text-secondary)" }}>
          Leave the end date empty while the trip is still running.
        </p>

        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Currency (GEL)"
            value={tripCurrency}
            maxLength={3}
            onChange={(e) => setTripCurrency(e.target.value.toUpperCase())}
            className="flex-1 rounded-xl px-3 py-2.5 text-sm outline-none"
            style={inputStyle}
          />
          <input
            type="number"
            min={0}
            step="any"
            placeholder="Budget (optional)"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            className="flex-1 rounded-xl px-3 py-2.5 text-sm outline-none"
            style={inputStyle}
          />
        </div>

        {!isEdit && (
          <button
            type="button"
            onClick={() => setAssignExisting((v) => !v)}
            className="flex items-start gap-2 text-left rounded-xl px-3 py-2.5"
            style={{ background: "var(--app-secondary-bg)", border: "1px solid var(--app-border)" }}
          >
            <span className="text-sm">{assignExisting ? "☑" : "☐"}</span>
            <span>
              <span className="text-sm block" style={{ color: "var(--app-text-primary)" }}>
                Pull in existing expenses
              </span>
              <span className="text-[11px]" style={{ color: "var(--app-text-secondary)" }}>
                Tags everything already recorded in these dates. Recurring payments are left alone.
              </span>
            </span>
          </button>
        )}

        {!datesValid && (
          <p className="text-xs px-1" style={{ color: "var(--app-danger)" }}>
            The end date cannot be before the start date.
          </p>
        )}
        {error && (
          <p className="text-xs px-1" style={{ color: "var(--app-danger)" }}>
            {error}
          </p>
        )}

        <button
          type="button"
          disabled={!valid || saving}
          onClick={() => void submit()}
          className="w-full py-3 rounded-xl text-sm font-semibold"
          style={{
            background: valid ? "#22c55e" : "var(--app-secondary-bg)",
            color: valid ? "#fff" : "var(--app-text-secondary)",
            border: "none",
          }}
        >
          {saving ? "Saving…" : isEdit ? "Save" : "Create trip"}
        </button>
      </div>
    </div>
  );
}
