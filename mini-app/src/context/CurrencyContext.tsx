/** Currency display context: toggles between base and default currency app-wide.
 *
 * All amounts stored in the backend live in the user's base currency. This
 * context lets the UI toggle between displaying them in the base currency or
 * converted to the default currency using the latest FX rate from the summary
 * endpoint. Components should never hardcode `$` / `฿` — use `format()`.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import { fmt } from "../utils/format";

export type CurrencyDisplayMode = "base" | "default";

interface CurrencyContextValue {
  displayMode: CurrencyDisplayMode;
  baseCurrency: string;
  defaultCurrency: string;
  /** 1 unit of base currency = `rate` units of default currency. */
  rate: number;
  activeCurrency: string;
  toggle: () => void;
  setMode: (mode: CurrencyDisplayMode) => void;
  /** Convert a base-currency amount to the currently active currency. */
  convert: (amountBase: number) => number;
  /** Format a base-currency amount in the currently active currency. */
  format: (amountBase: number, decimals?: number) => string;
}

const CurrencyContext = createContext<CurrencyContextValue | null>(null);

interface CurrencyProviderProps {
  children: ReactNode;
  baseCurrency: string;
  defaultCurrency: string;
  rate: number | null | undefined;
  initialMode?: CurrencyDisplayMode;
}

const STORAGE_KEY = "currency-display-mode";

function readStoredMode(): CurrencyDisplayMode | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "base" || v === "default" ? v : null;
  } catch {
    return null;
  }
}

function writeStoredMode(mode: CurrencyDisplayMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // ignore quota / privacy-mode errors
  }
}

export function CurrencyProvider({
  children,
  baseCurrency,
  defaultCurrency,
  rate,
  initialMode,
}: CurrencyProviderProps) {
  const [displayMode, setDisplayMode] = useState<CurrencyDisplayMode>(() => {
    return readStoredMode() ?? initialMode ?? "base";
  });

  const effectiveRate = rate && rate > 0 ? rate : 1;
  // If base and default are identical, toggling is a no-op; force base.
  const sameCurrency = baseCurrency.toUpperCase() === defaultCurrency.toUpperCase();
  const actualMode: CurrencyDisplayMode = sameCurrency ? "base" : displayMode;

  const setMode = useCallback((mode: CurrencyDisplayMode) => {
    setDisplayMode(mode);
    writeStoredMode(mode);
  }, []);

  const toggle = useCallback(() => {
    setDisplayMode((prev) => {
      const next: CurrencyDisplayMode = prev === "base" ? "default" : "base";
      writeStoredMode(next);
      return next;
    });
  }, []);

  const activeCurrency = actualMode === "default" ? defaultCurrency : baseCurrency;

  const convert = useCallback(
    (amountBase: number): number => {
      return actualMode === "default" ? amountBase * effectiveRate : amountBase;
    },
    [actualMode, effectiveRate],
  );

  const format = useCallback(
    (amountBase: number, decimals = 2): string => {
      return fmt(convert(amountBase), activeCurrency, decimals);
    },
    [convert, activeCurrency],
  );

  const value = useMemo<CurrencyContextValue>(
    () => ({
      displayMode: actualMode,
      baseCurrency,
      defaultCurrency,
      rate: effectiveRate,
      activeCurrency,
      toggle,
      setMode,
      convert,
      format,
    }),
    [
      actualMode,
      baseCurrency,
      defaultCurrency,
      effectiveRate,
      activeCurrency,
      toggle,
      setMode,
      convert,
      format,
    ],
  );

  return <CurrencyContext.Provider value={value}>{children}</CurrencyContext.Provider>;
}

export function useCurrency(): CurrencyContextValue {
  const ctx = useContext(CurrencyContext);
  if (!ctx) {
    throw new Error("useCurrency must be used inside a <CurrencyProvider>");
  }
  return ctx;
}

/** Non-throwing variant: returns null when no CurrencyProvider is mounted above. */
export function useCurrencyOptional(): CurrencyContextValue | null {
  return useContext(CurrencyContext);
}
