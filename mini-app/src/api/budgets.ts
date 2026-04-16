import { api } from "./client";
import type { BudgetsResponse, UpdateBudgetsRequest } from "./types";

export function fetchBudgets(offset = 0): Promise<BudgetsResponse> {
  return api.get<BudgetsResponse>(
    "/budgets",
    offset !== 0 ? { offset: String(offset) } : undefined,
  );
}

export function updateBudgets(budgets: Record<string, number>): Promise<BudgetsResponse> {
  const body: UpdateBudgetsRequest = { budgets };
  return api.put<BudgetsResponse>("/budgets", body);
}
