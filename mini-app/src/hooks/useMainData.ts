/** Fetch every piece of data the single-page redesign needs, in parallel.
 *
 * MainPage renders Overview / Trends / Budget sub-tabs from the same data set,
 * so it's cheaper (and simpler) to load everything once on mount instead of
 * each sub-tab re-fetching what it needs.
 *
 * Bundles are cached per-monthOffset in sessionStorage (10-min TTL). Any
 * mutation calls `refetch()` which clears every cached month before reloading.
 */

import { useCallback, useEffect, useState } from "react";
import { fetchBudgets } from "../api/budgets";
import { clearCache, getCached, setCached } from "../api/cache";
import { fetchCategories } from "../api/categories";
import { fetchExpenses } from "../api/expenses";
import { fetchRecurring } from "../api/recurring";
import { fetchSummary } from "../api/summary";
import { fetchTrips } from "../api/trips";
import { useUser } from "../context/UserContext";
import { addMonths, monthEnd, monthStart } from "../utils/dates";
import type {
  BudgetsResponse,
  CategoriesResponse,
  ExpensesResponse,
  RecurringResponse,
  SummaryResponse,
  TripsResponse,
} from "../api/types";

export interface MainData {
  summary: SummaryResponse | null;
  budgets: BudgetsResponse | null;
  expenses: ExpensesResponse | null;
  categories: CategoriesResponse | null;
  recurring: RecurringResponse | null;
  trips: TripsResponse | null;
}

export interface UseMainDataResult extends MainData {
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

const EMPTY: MainData = {
  summary: null,
  budgets: null,
  expenses: null,
  categories: null,
  recurring: null,
  trips: null,
};

/** Month range for `offset` months from the user's current month (user "today"). */
function monthBounds(offset: number, today: string): { since: string; until: string } {
  const first = addMonths(monthStart(today), offset);
  return { since: first, until: monthEnd(first) };
}

function cacheKey(offset: number, tz: string, today: string): string {
  // Keyed by timezone and user-day so a zone change never serves stale months.
  return `main:${tz}:${today}:${offset}`;
}

async function fetchBundle(monthOffset: number, today: string): Promise<MainData> {
  const { since, until } = monthBounds(monthOffset, today);
  // Sequential requests: Cloud Function concurrency=1; parallel bursts cause 503s.
  const summary = await fetchSummary("month", true, monthOffset);
  const budgets = await fetchBudgets(monthOffset);
  const expenses = await fetchExpenses({ since, until, limit: 200 });
  const categories = await fetchCategories();
  const recurring = await fetchRecurring();
  // Trips are optional: the Sheets backend answers 501, and the rest of the
  // page must still render.
  const trips = await fetchTrips().catch(() => null);
  return { summary, budgets, expenses, categories, recurring, trips };
}

export function useMainData(monthOffset = 0): UseMainDataResult {
  const { timezone, today, isLoading: userLoading } = useUser();
  const [data, setData] = useState<MainData>(EMPTY);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadFresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const bundle = await fetchBundle(monthOffset, today);
      setData(bundle);
      setCached(cacheKey(monthOffset, timezone, today), bundle);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setIsLoading(false);
    }
  }, [monthOffset, timezone, today]);

  const refetch = useCallback(async () => {
    clearCache();
    await loadFresh();
  }, [loadFresh]);

  useEffect(() => {
    // Wait until settings have settled (success or failure) so the first
    // fetch uses the user's timezone, not a brief device-zone fallback.
    if (userLoading) return;
    const cached = getCached<MainData>(cacheKey(monthOffset, timezone, today));
    if (cached) {
      setData(cached);
      setError(null);
      setIsLoading(false);
      return;
    }
    setData(EMPTY);
    void loadFresh();
  }, [monthOffset, timezone, today, loadFresh, userLoading]);

  useEffect(() => {
    function onVisible() {
      if (document.visibilityState === "visible") void refetch();
    }
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [refetch]);

  return { ...data, isLoading, error, refetch };
}
