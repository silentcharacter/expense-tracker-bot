/** Bottom-sheet modal for picking an IANA timezone (or the server default). */

import { useEffect, useMemo, useRef, useState } from "react";
import { timezoneOptions } from "../../utils/timezones";
import type { TimezoneOption } from "../../utils/timezones";

interface TimezonePickerModalProps {
  /** Currently effective IANA zone. */
  current: string;
  /** True when the user has no personal timezone: "Default" shows as selected. */
  isDefault: boolean;
  /** Called with an IANA name, or "" to reset to the default. */
  onSelect: (tz: string) => void;
  onCancel: () => void;
}

function Check() {
  return (
    <svg width={16} height={16} viewBox="0 0 16 16" fill="none">
      <path
        d="M3 8l4 4 6-7"
        stroke="var(--app-accent)"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function TimezonePickerModal({
  current,
  isDefault,
  onSelect,
  onCancel,
}: TimezonePickerModalProps) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 150);
  }, []);

  const options = useMemo<TimezoneOption[]>(() => {
    const base = timezoneOptions();
    // Keep an unlisted current zone visible and selected.
    if (current && !base.some((o) => o.id === current)) {
      return [{ id: current, label: current }, ...base];
    }
    return base;
  }, [current]);

  const q = query.trim().toLowerCase();
  const qUnderscore = q.replace(/\s+/g, "_");
  const filtered = q
    ? options.filter(
        (o) => o.id.toLowerCase().includes(qUnderscore) || o.label.toLowerCase().includes(q),
      )
    : options;
  const showDefault = !q || "default".includes(q);
  const rowStyle = { borderColor: "var(--app-border)" };

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col justify-end"
      style={{ background: "rgba(0,0,0,0.5)" }}
      onClick={(e) => e.target === e.currentTarget && onCancel()}
    >
      <div
        className="rounded-t-2xl flex flex-col"
        style={{ background: "var(--app-bg)", maxHeight: "80vh" }}
      >
        <div className="flex items-center justify-between px-4 pt-4 pb-2 flex-shrink-0">
          <p className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
            Timezone
          </p>
          <button className="text-sm" style={{ color: "var(--app-accent)" }} onClick={onCancel}>
            Cancel
          </button>
        </div>

        <div className="px-4 pb-2 flex-shrink-0">
          <input
            ref={inputRef}
            type="text"
            placeholder="Search (Kyiv, Asia/Tokyo…)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
            style={{
              background: "var(--app-secondary-bg)",
              color: "var(--app-text-primary)",
              border: "1px solid var(--app-border)",
            }}
          />
        </div>

        <div className="overflow-y-auto flex-1 px-4 pb-4">
          {showDefault && (
            <button
              className="w-full flex items-center justify-between py-3 border-b text-left"
              style={rowStyle}
              onClick={() => onSelect("")}
            >
              <div>
                <span className="text-sm font-medium" style={{ color: "var(--app-text-primary)" }}>
                  Default
                </span>
                <span className="text-xs ml-2" style={{ color: "var(--app-text-secondary)" }}>
                  Server default zone
                </span>
              </div>
              {isDefault && <Check />}
            </button>
          )}
          {filtered.map((o) => (
            <button
              key={o.id}
              className="w-full flex items-center justify-between py-3 border-b text-left"
              style={rowStyle}
              onClick={() => onSelect(o.id)}
            >
              <span className="text-sm" style={{ color: "var(--app-text-primary)" }}>
                {o.label}
              </span>
              {!isDefault && o.id === current && <Check />}
            </button>
          ))}
          {filtered.length === 0 && !showDefault && (
            <p className="text-xs py-4 text-center" style={{ color: "var(--app-text-secondary)" }}>
              No matching timezone
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
