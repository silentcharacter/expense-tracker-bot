import { api } from "./client";
import type { BudgetsResponse, UpdateBudgetsRequest } from "./types";

export function fetchBudgets(): Promise<BudgetsResponse> {
  return api.get<BudgetsResponse>("/budgets");
}

export function updateBudgets(budgets: Record<string, number>): Promise<BudgetsResponse> {
  const body: UpdateBudgetsRequest = { budgets };
  return api.put<BudgetsResponse>("/budgets", body);
}
