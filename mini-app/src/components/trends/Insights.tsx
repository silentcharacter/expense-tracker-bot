/** Auto-generated insight cards derived from summary comparison data. */

import { useMemo } from "react";
import type { SummaryResponse } from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";
import { getCategoryEmoji, getCategoryLabel } from "../../utils/categories";
import { formatPercent } from "../../utils/format";
import { InsightCard } from "../analytics/InsightCard";

interface InsightsProps {
  summary: SummaryResponse;
}

interface InsightEntry {
  emoji: string;
  title: string;
  subtitle: string;
  badge: string;
  badgePositive?: boolean;
}

function previousMonthName(dateRange: { start: string }): string {
  const d = new Date(dateRange.start + "T12:00:00");
  d.setMonth(d.getMonth() - 1);
  return d.toLocaleDateString(undefined, { month: "long" });
}

function buildInsights(
  summary: SummaryResponse,
  format: (amount: number, decimals?: number) => string,
): InsightEntry[] {
  const prevMonth = previousMonthName(summary.date_range);
  const insights: InsightEntry[] = [];

  const withComparison = summary.by_category.filter(
    (c) => c.change_percent !== undefined && c.previous_amount_base !== undefined,
  );

  // 1. Biggest decrease (below last month's pace)
  const biggestDecrease = [...withComparison]
    .filter((c) => (c.change_percent ?? 0) < -5)
    .sort((a, b) => (a.change_percent ?? 0) - (b.change_percent ?? 0))[0];
  if (biggestDecrease) {
    const pct = Math.abs(biggestDecrease.change_percent ?? 0);
    insights.push({
      emoji: getCategoryEmoji(biggestDecrease.category),
      title: `${getCategoryLabel(biggestDecrease.category)} is ${pct.toFixed(0)}% below ${prevMonth} pace`,
      subtitle: `${format(biggestDecrease.previous_amount_base ?? 0, 0)} → ${format(biggestDecrease.amount_base, 0)}`,
      badge: formatPercent(biggestDecrease.change_percent ?? 0, true, 0),
      badgePositive: true,
    });
  }

  // 2. Biggest increase
  const biggestIncrease = [...withComparison]
    .filter((c) => (c.change_percent ?? 0) > 5)
    .sort((a, b) => (b.change_percent ?? 0) - (a.change_percent ?? 0))[0];
  if (biggestIncrease) {
    const pct = biggestIncrease.change_percent ?? 0;
    insights.push({
      emoji: getCategoryEmoji(biggestIncrease.category),
      title: `${getCategoryLabel(biggestIncrease.category)} up ${pct.toFixed(0)}% vs ${prevMonth}`,
      subtitle: `${format(biggestIncrease.previous_amount_base ?? 0, 0)} → ${format(biggestIncrease.amount_base, 0)}`,
      badge: formatPercent(pct, true, 0),
      badgePositive: false,
    });
  }

  // 3. Stable category (within 5%)
  const stable = withComparison.find(
    (c) => Math.abs(c.change_percent ?? 0) <= 5 && (c.previous_amount_base ?? 0) > 0,
  );
  if (stable) {
    insights.push({
      emoji: getCategoryEmoji(stable.category),
      title: `${getCategoryLabel(stable.category)} is stable`,
      subtitle: `Within ${Math.abs(stable.change_percent ?? 0).toFixed(0)}% of ${prevMonth}`,
      badge: formatPercent(stable.change_percent ?? 0, true, 0),
    });
  }

  // 4. Net savings (if total < previous total)
  if (summary.comparison) {
    const { previous_total, change_percent } = summary.comparison;
    const delta = previous_total - summary.total_base;
    if (delta > 0 && change_percent < 0) {
      insights.push({
        emoji: "💰",
        title: `You've saved ~${format(delta, 0)} so far vs ${prevMonth}`,
        subtitle: `Total spend ${formatPercent(change_percent, true, 0)}`,
        badge: formatPercent(change_percent, true, 0),
        badgePositive: true,
      });
    } else if (delta < 0 && change_percent > 0) {
      insights.push({
        emoji: "⚠️",
        title: `Spending ${format(-delta, 0)} more than ${prevMonth}`,
        subtitle: `Total spend ${formatPercent(change_percent, true, 0)}`,
        badge: formatPercent(change_percent, true, 0),
        badgePositive: false,
      });
    }
  }

  return insights;
}

export function Insights({ summary }: InsightsProps) {
  const { formatLive: format } = useCurrency();
  const insights = useMemo(() => buildInsights(summary, format), [summary, format]);

  if (insights.length === 0) return null;

  return (
    <div className="card">
      <p
        className="text-xs font-semibold tracking-widest mb-2"
        style={{ color: "var(--app-text-secondary)" }}
      >
        INSIGHTS
      </p>
      {insights.map((insight, i) => (
        <InsightCard key={i} {...insight} />
      ))}
    </div>
  );
}
