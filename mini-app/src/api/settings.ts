import { api } from "./client";
import type { ExportParams, UpdateSettingsRequest, UserSettings } from "./types";

export function fetchSettings(): Promise<UserSettings> {
  return api.get<UserSettings>("/settings");
}

export function updateSettings(data: UpdateSettingsRequest): Promise<UserSettings> {
  return api.put<UserSettings>("/settings", data);
}

export async function exportExpenses(params?: ExportParams): Promise<void> {
  const queryParams: Record<string, string> = {};
  if (params?.start) queryParams.start = params.start;
  if (params?.end) queryParams.end = params.end;

  const { blob, filename } = await api.getBlob("/export", queryParams);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function clearAllExpenses(): Promise<{ deleted: number }> {
  return api.delete<{ deleted: number }>("/expenses");
}
