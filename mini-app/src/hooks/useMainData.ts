/** Fetch every piece of data the single-page redesign needs, in parallel.
 *
 * MainPage renders Overview / Trends / Budget sub-tabs from the same data set,
 * so it's cheaper (and simpler) to load everything once on mount instead of
 * each sub-tab re-fetching what it needs.
 */

import { useCallback, useEffect, useState } from "react";
import { fetchBudgets } from "../api/budgets";
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

export function useMainData(monthOffset = 0): UseMainDataResult {
  const [data, setData] = useState<MainData>({
    summary: null,
    budgets: null,
    expenses: null,
    categories: null,
    recurring: null,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    const { since, until } = monthBounds(monthOffset);
    try {
      const [summary, budgets, expenses, categories, recurring] = await Promise.all([
        fetchSummary("month", true, monthOffset),
        fetchBudgets(monthOffset),
        fetchExpenses({ since, until, limit: 200 }),
        fetchCategories(),
        fetchRecurring(),
      ]);
      setData({ summary, budgets, expenses, categories, recurring });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setIsLoading(false);
    }
  }, [monthOffset]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { ...data, isLoading, error, refetch };
}
