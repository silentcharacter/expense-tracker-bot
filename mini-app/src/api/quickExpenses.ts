import { api } from "./client";
import type { QuickExpense, QuickExpensesResponse } from "./types";

export function fetchQuickExpenses(): Promise<QuickExpensesResponse> {
  return api.get<QuickExpensesResponse>("/quick-expenses");
}

/** Replace the whole list (order included); the bot then refreshes the chat keyboard. */
export function saveQuickExpenses(items: QuickExpense[]): Promise<QuickExpensesResponse> {
  return api.put<QuickExpensesResponse>("/quick-expenses", { items });
}
