import { api } from "./client";
import type { UpdateSettingsRequest, UserSettings } from "./types";

export function fetchSettings(): Promise<UserSettings> {
  return api.get<UserSettings>("/settings");
}

export function updateSettings(data: UpdateSettingsRequest): Promise<UserSettings> {
  return api.put<UserSettings>("/settings", data);
}
