/** Currency display context: toggles between base and default currency app-wide.
 *
 * The backend returns pre-computed amounts in both base and default currencies.
 * This context lets the UI toggle which one to display.  Components pass
 * ``{ base, default }`` pairs to ``pick()`` / ``format()`` — no FX math here.
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

export interface Amounts {
  base: number;
  default: number;
}

interface CurrencyContextValue {
  displayMode: CurrencyDisplayMode;
  baseCurrency: string;
  defaultCurrency: string;
  /** 1 unit of base currency = `rate` units of default currency (kept for budget/pace live conversion). */
  rate: number;
  activeCurrency: string;
  toggle: () => void;
  setMode: (mode: CurrencyDisplayMode) => void;
  /** Pick the right pre-computed amount for the active display mode. */
  pick: (amounts: Amounts) => number;
  /** Format a pre-computed {base, default} pair in the currently active currency. */
  format: (amounts: Amounts, decimals?: number) => string;
  /** Convert a base-only value using the live rate (for budgets / projections that have no stored default). */
  convertLive: (amountBase: number) => number;
  /** Format a base-only value using live conversion (for budgets / projections). */
  formatLive: (amountBase: number, decimals?: number) => string;
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

  const pick = useCallback(
    (amounts: Amounts): number => {
      return actualMode === "default" ? amounts.default : amounts.base;
    },
    [actualMode],
  );

  const format = useCallback(
    (amounts: Amounts, decimals = 2): string => {
      return fmt(pick(amounts), activeCurrency, decimals);
    },
    [pick, activeCurrency],
  );

  const convertLive = useCallback(
    (amountBase: number): number => {
      return actualMode === "default" ? amountBase * effectiveRate : amountBase;
    },
    [actualMode, effectiveRate],
  );

  const formatLive = useCallback(
    (amountBase: number, decimals = 2): string => {
      return fmt(convertLive(amountBase), activeCurrency, decimals);
    },
    [convertLive, activeCurrency],
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
      pick,
      format,
      convertLive,
      formatLive,
    }),
    [
      actualMode,
      baseCurrency,
      defaultCurrency,
      effectiveRate,
      activeCurrency,
      toggle,
      setMode,
      pick,
      format,
      convertLive,
      formatLive,
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
