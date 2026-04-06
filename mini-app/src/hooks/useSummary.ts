import { useCallback, useEffect, useState } from "react";
import { fetchSummary } from "../api/summary";
import { fetchBudgets } from "../api/budgets";
import type { Period } from "../api/summary";
import type { SummaryResponse, BudgetsResponse } from "../api/types";

interface UseSummaryResult {
  summary: SummaryResponse | null;
  budgets: BudgetsResponse | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useSummary(period: Period, offset = 0): UseSummaryResult {
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [budgets, setBudgets] = useState<BudgetsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(() => {
    setIsLoading(true);
    setError(null);

    Promise.all([fetchSummary(period, true, offset), fetchBudgets()])
      .then(([summaryData, budgetsData]) => {
        setSummary(summaryData);
        setBudgets(budgetsData);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load data");
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [period, offset]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { summary, budgets, isLoading, error, refetch: fetch };
}
