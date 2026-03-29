import { api } from "./client";
import type { SummaryResponse } from "./types";

export type Period = "today" | "week" | "month" | "year";

export function fetchSummary(period: Period, compare = false): Promise<SummaryResponse> {
  return api.get<SummaryResponse>("/summary", {
    period,
    compare: String(compare),
  });
}
