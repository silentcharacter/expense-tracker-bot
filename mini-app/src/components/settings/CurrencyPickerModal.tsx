/** Bottom-sheet modal for picking an ISO 4217 currency code. */

import { useState, useRef, useEffect } from "react";

const COMMON_CURRENCIES = [
  { code: "USD", label: "US Dollar" },
  { code: "EUR", label: "Euro" },
  { code: "GBP", label: "British Pound" },
  { code: "THB", label: "Thai Baht" },
  { code: "ILS", label: "Israeli Shekel" },
  { code: "JPY", label: "Japanese Yen" },
  { code: "CNY", label: "Chinese Yuan" },
  { code: "AED", label: "UAE Dirham" },
  { code: "SGD", label: "Singapore Dollar" },
  { code: "AUD", label: "Australian Dollar" },
  { code: "CAD", label: "Canadian Dollar" },
  { code: "CHF", label: "Swiss Franc" },
  { code: "RUB", label: "Russian Ruble" },
  { code: "INR", label: "Indian Rupee" },
  { code: "BRL", label: "Brazilian Real" },
  { code: "MXN", label: "Mexican Peso" },
  { code: "IDR", label: "Indonesian Rupiah" },
  { code: "TRY", label: "Turkish Lira" },
  { code: "KRW", label: "South Korean Won" },
  { code: "MYR", label: "Malaysian Ringgit" },
];

interface CurrencyPickerModalProps {
  title: string;
  current: string;
  onSelect: (code: string) => void;
  onCancel: () => void;
}

export function CurrencyPickerModal({
  title,
  current,
  onSelect,
  onCancel,
}: CurrencyPickerModalProps) {
  const [query, setQuery] = useState("");
  const [customCode, setCustomCode] = useState("");
  const [customError, setCustomError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 150);
  }, []);

  const filtered = query
    ? COMMON_CURRENCIES.filter(
        (c) =>
          c.code.includes(query.toUpperCase()) ||
          c.label.toLowerCase().includes(query.toLowerCase())
      )
    : COMMON_CURRENCIES;

  function handleCustomSubmit() {
    const code = customCode.trim().toUpperCase();
    if (!/^[A-Z]{3}$/.test(code)) {
      setCustomError("Enter a valid 3-letter currency code (e.g. USD)");
      return;
    }
    onSelect(code);
  }

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
        {/* Header */}
        <div className="flex items-center justify-between px-4 pt-4 pb-2 flex-shrink-0">
          <p className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
            {title}
          </p>
          <button
            className="text-sm"
            style={{ color: "var(--app-accent)" }}
            onClick={onCancel}
          >
            Cancel
          </button>
        </div>

        {/* Search */}
        <div className="px-4 pb-2 flex-shrink-0">
          <input
            ref={inputRef}
            type="text"
            placeholder="Search (USD, Euro…)"
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

        {/* Currency list */}
        <div className="overflow-y-auto flex-1 px-4 pb-2">
          {filtered.map((c) => (
            <button
              key={c.code}
              className="w-full flex items-center justify-between py-3 border-b text-left"
              style={{ borderColor: "var(--app-border)" }}
              onClick={() => onSelect(c.code)}
            >
              <div>
                <span className="text-sm font-medium" style={{ color: "var(--app-text-primary)" }}>
                  {c.code}
                </span>
                <span className="text-xs ml-2" style={{ color: "var(--app-text-secondary)" }}>
                  {c.label}
                </span>
              </div>
              {c.code === current && (
                <svg width={16} height={16} viewBox="0 0 16 16" fill="none">
                  <path
                    d="M3 8l4 4 6-7"
                    stroke="var(--app-accent)"
                    strokeWidth={1.8}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
            </button>
          ))}

          {/* Custom code entry */}
          <div className="pt-3 pb-4">
            <p className="text-xs mb-2" style={{ color: "var(--app-text-secondary)" }}>
              Other currency (ISO 4217 code)
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="e.g. NGN"
                maxLength={3}
                value={customCode}
                onChange={(e) => {
                  setCustomCode(e.target.value.toUpperCase());
                  setCustomError("");
                }}
                onKeyDown={(e) => e.key === "Enter" && handleCustomSubmit()}
                className="flex-1 rounded-xl px-3 py-2.5 text-sm uppercase outline-none"
                style={{
                  background: "var(--app-secondary-bg)",
                  color: "var(--app-text-primary)",
                  border: customError ? "1px solid var(--app-danger)" : "1px solid var(--app-border)",
                  letterSpacing: "0.1em",
                }}
              />
              <button
                onClick={handleCustomSubmit}
                className="px-4 py-2.5 rounded-xl text-sm font-semibold"
                style={{
                  background: customCode.length === 3 ? "var(--app-accent)" : "var(--app-secondary-bg)",
                  color: customCode.length === 3 ? "#fff" : "var(--app-text-secondary)",
                }}
              >
                Use
              </button>
            </div>
            {customError && (
              <p className="text-xs mt-1" style={{ color: "var(--app-danger)" }}>
                {customError}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
