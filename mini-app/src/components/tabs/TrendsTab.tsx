/** Trends sub-tab: current-vs-previous comparison + auto-generated insights. */

import type { SummaryResponse } from "../../api/types";
import { Insights } from "../trends/Insights";
import { VsLastMonth } from "../trends/VsLastMonth";

interface TrendsTabProps {
  summary: SummaryResponse | null;
}

export function TrendsTab({ summary }: TrendsTabProps) {
  if (!summary) return null;

  const hasData = summary.total_base > 0;

  if (!hasData) {
    return (
      <div className="card text-center py-8">
        <p className="text-2xl mb-2">📭</p>
        <p className="text-sm" style={{ color: "var(--app-text-secondary)" }}>
          No expenses to compare yet
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <VsLastMonth summary={summary} />
      <Insights summary={summary} />
    </div>
  );
}
