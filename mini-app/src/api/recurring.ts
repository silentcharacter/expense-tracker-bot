import { api } from "./client";
import type { RecurringResponse, AddRecurringRequest } from "./types";

export function fetchRecurring(): Promise<RecurringResponse> {
  return api.get<RecurringResponse>("/recurring");
}

export function addRecurring(entry: AddRecurringRequest): Promise<RecurringResponse> {
  return api.post<RecurringResponse>("/recurring", entry);
}

export function deleteRecurring(id: string): Promise<RecurringResponse> {
  return api.delete<RecurringResponse>(`/recurring/${id}`);
}
