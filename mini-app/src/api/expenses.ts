import { api } from "./client";
import type { DeleteExpenseResponse, ExpensesResponse } from "./types";

export interface FetchExpensesParams {
  since?: string;
  until?: string;
  category?: string;
  limit?: number;
  offset?: number;
}

export function fetchExpenses(params: FetchExpensesParams = {}): Promise<ExpensesResponse> {
  const query: Record<string, string> = {};
  if (params.since) query.since = params.since;
  if (params.until) query.until = params.until;
  if (params.category) query.category = params.category;
  if (params.limit !== undefined) query.limit = String(params.limit);
  if (params.offset !== undefined) query.offset = String(params.offset);
  return api.get<ExpensesResponse>("/expenses", query);
}

export function deleteExpense(id: string): Promise<DeleteExpenseResponse> {
  return api.delete<DeleteExpenseResponse>(`/expenses/${id}`);
}
