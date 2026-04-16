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
import type {
  BudgetsResponse,
  CategoriesResponse,
  ExpensesResponse,
  RecurringResponse,
  SummaryResponse,
} from "../api/types";

export interface MainData {
  summary: SummaryResponse | null;
  budgets: BudgetsResponse | null;
  expenses: ExpensesResponse | null;
  categories: CategoriesResponse | null;
  recurring: RecurringResponse | null;
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
};

function monthBounds(offset: number): { since: string; until: string } {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth() + offset;
  const start = new Date(y, m, 1);
  const end = new Date(y, m + 1, 0); // last day of target month
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
      d.getDate(),
    ).padStart(2, "0")}`;
  return { since: iso(start), until: iso(end) };
}

function cacheKey(offset: number): string {
  return `main:${offset}`;
}

async function fetchBundle(monthOffset: number): Promise<MainData> {
  const { since, until } = monthBounds(monthOffset);
  const [summary, budgets, expenses, categories, recurring] = await Promise.all([
    fetchSummary("month", true, monthOffset),
    fetchBudgets(monthOffset),
    fetchExpenses({ since, until, limit: 200 }),
    fetchCategories(),
    fetchRecurring(),
  ]);
  return { summary, budgets, expenses, categories, recurring };
}

export function useMainData(monthOffset = 0): UseMainDataResult {
  const [data, setData] = useState<MainData>(EMPTY);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadFresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const bundle = await fetchBundle(monthOffset);
      setData(bundle);
      setCached(cacheKey(monthOffset), bundle);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setIsLoading(false);
    }
  }, [monthOffset]);

  const refetch = useCallback(async () => {
    clearCache();
    await loadFresh();
  }, [loadFresh]);

  useEffect(() => {
    const cached = getCached<MainData>(cacheKey(monthOffset));
    if (cached) {
      setData(cached);
      setError(null);
      setIsLoading(false);
      return;
    }
    setData(EMPTY);
    void loadFresh();
  }, [monthOffset, loadFresh]);

  return { ...data, isLoading, error, refetch };
}
