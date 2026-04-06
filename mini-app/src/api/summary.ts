import { api } from "./client";
import type { SummaryResponse } from "./types";

export type Period = "today" | "week" | "month" | "year";

export function fetchSummary(period: Period, compare = false, offset = 0): Promise<SummaryResponse> {
  return api.get<SummaryResponse>("/summary", {
    period,
    compare: String(compare),
    ...(offset !== 0 ? { offset: String(offset) } : {}),
  });
}
