import { api, ApiError } from "./client";
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

export async function logRecurring(id: string): Promise<'ok' | 'already_logged'> {
  try {
    await api.post<{ ok: boolean }>(`/recurring/${id}/log`, {});
    return 'ok';
  } catch (err: unknown) {
    if (err instanceof ApiError && err.status === 409) {
      return 'already_logged';
    }
    throw err;
  }
}
