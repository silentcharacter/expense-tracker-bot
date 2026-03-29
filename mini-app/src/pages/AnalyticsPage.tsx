/** Analytics tab — daily spending chart, insights, and VS last month comparison. */

import { useMemo, useState } from "react";
import type { Period } from "../api/summary";
import type { BudgetsResponse, CategorySummary, SummaryResponse } from "../api/types";
import { useUser } from "../context/UserContext";
import { useSummary } from "../hooks/useSummary";
import { PeriodSelector } from "../components/dashboard/PeriodSelector";
import { DailyChart } from "../components/dashboard/DailyChart";
import { InsightCard } from "../components/analytics/InsightCard";
import { CategoryComparisonRow } from "../components/analytics/CategoryComparisonRow";
import { SkeletonBlock, SkeletonLine } from "../components/shared/Skeleton";
import { getCategoryEmoji, getCategoryLabel } from "../utils/categories";
import { formatAmount, formatAmountCompact, formatPercent } from "../utils/format";

// ── Skeleton ─────────────────────────────────────────────────────────────────

function AnalyticsSkeleton() {
  return (
    <>
      <SkeletonBlock height={180} className="rounded-xl mb-3" />
      <div className="card mb-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-3 py-3">
            <SkeletonBlock height={32} className="rounded-lg w-8" />
            <div className="flex-1">
              <SkeletonLine height={13} width="55%" className="mb-1" />
              <SkeletonLine height={11} width="75%" />
            </div>
            <SkeletonLine height={22} width="44px" className="rounded-full" />
          </div>
        ))}
      </div>
      <div className="card">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="flex items-center gap-3 py-3">
            <SkeletonLine height={12} width="100px" />
            <div className="flex-1">
              <SkeletonBlock height={6} className="rounded-full mb-1" />
              <SkeletonBlock height={6} className="rounded-full" />
            </div>
            <SkeletonLine height={12} width="36px" />
          </div>
        ))}
      </div>
    </>
  );
}

// ── Insights helper ───────────────────────────────────────────────────────────

interface Insight {
  emoji: string;
  title: string;
  subtitle: string;
  badge: string;
  badgePositive?: boolean;
}

function computeInsights(
  summary: SummaryResponse,
  budgets: BudgetsResponse | null,
  currency: string
): Insight[] {
  const insights: Insight[] = [];
  const cats = summary.by_category;

  // 1. Biggest increase vs previous period
  const withComparison = cats.filter(
    (c) => c.change_percent !== undefined && c.previous_amount_base !== undefined
  );
  const biggestIncrease = withComparison
    .filter((c) => (c.change_percent ?? 0) > 0)
    .sort((a, b) => (b.change_percent ?? 0) - (a.change_percent ?? 0))[0];

  if (biggestIncrease) {
    insights.push({
      emoji: getCategoryEmoji(biggestIncrease.category),
      title: `${getCategoryLabel(biggestIncrease.category)} up ${formatPercent(biggestIncrease.change_percent!)}`,
      subtitle: `${formatAmountCompact(biggestIncrease.previous_amount_base!, currency)} → ${formatAmountCompact(biggestIncrease.amount_base, currency)} vs last period`,
      badge: formatPercent(biggestIncrease.change_percent!, true),
      badgePositive: false,
    });
  }

  // 2. Biggest decrease vs previous period
  const biggestDecrease = withComparison
    .filter((c) => (c.change_percent ?? 0) < 0)
    .sort((a, b) => (a.change_percent ?? 0) - (b.change_percent ?? 0))[0];

  if (biggestDecrease) {
    insights.push({
      emoji: getCategoryEmoji(biggestDecrease.category),
      title: `${getCategoryLabel(biggestDecrease.category)} down ${formatPercent(Math.abs(biggestDecrease.change_percent!))}`,
      subtitle: "Spent less than last period",
      badge: formatPercent(biggestDecrease.change_percent!, true),
      badgePositive: true,
    });
  }

  // 3. Budget status — category with highest % used
  if (budgets?.budgets.length) {
    const topBudget = [...budgets.budgets]
      .filter((b) => b.budget > 0)
      .sort((a, b) => b.percentage - a.percentage)[0];
    if (topBudget) {
      const label = topBudget.percentage > 100 ? "over budget" : "on track";
      insights.push({
        emoji: getCategoryEmoji(topBudget.category),
        title: `${getCategoryLabel(topBudget.category)} ${label}`,
        subtitle: `${formatAmountCompact(topBudget.spent, currency)} of ${formatAmountCompact(topBudget.budget, currency)} budget used`,
        badge: `${Math.round(topBudget.percentage)}%`,
        badgePositive: topBudget.percentage <= 100,
      });
    }
  }

  // 4. Biggest share of total spend
  const topSpend = [...cats].sort((a, b) => b.percentage - a.percentage)[0];
  if (topSpend && !insights.some((ins) => ins.emoji === getCategoryEmoji(topSpend.category))) {
    insights.push({
      emoji: getCategoryEmoji(topSpend.category),
      title: `${getCategoryLabel(topSpend.category)}: ${formatAmountCompact(topSpend.amount_base, currency)} this period`,
      subtitle: `That's ${formatPercent(topSpend.percentage)} of your total spending`,
      badge: formatAmount(topSpend.amount_base, currency, 0),
    });
  }

  return insights;
}

// ── Section label ─────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: string }) {
  return (
    <p
      className="text-xs font-semibold tracking-widest mb-2 px-1"
      style={{ color: "var(--app-text-secondary)" }}
    >
      {children}
    </p>
  );
}

// ── Daily spending section ───────────────────────────────────────────────────

function monthName(dateRange: { start: string; end: string }): string {
  return new Date(dateRange.start + "T12:00:00").toLocaleDateString(undefined, {
    month: "long",
  }).toUpperCase();
}

interface DailySpendingSectionProps {
  summary: SummaryResponse;
  currency: string;
}

function DailySpendingSection({ summary, currency }: DailySpendingSectionProps) {
  const tiles = [
    { label: "Avg/day", value: formatAmountCompact(summary.daily_average, currency) },
    { label: "Total", value: formatAmountCompact(summary.total_base, currency) },
    { label: "Days left", value: String(summary.days_remaining ?? 0) },
    { label: "Transactions", value: String(summary.transaction_count) },
  ];

  return (
    <div className="card mb-3">
      <SectionLabel>{`DAILY SPENDING — ${monthName(summary.date_range)}`}</SectionLabel>
      <DailyChart data={summary.daily_totals} currency={currency} />
      <div className="grid grid-cols-4 gap-2 mt-3">
        {tiles.map(({ label, value }) => (
          <div key={label} className="text-center">
            <p className="amount text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
              {value}
            </p>
            <p className="text-[10px] mt-0.5" style={{ color: "var(--app-text-secondary)" }}>
              {label}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── VS Last Month section ────────────────────────────────────────────────────

function VsLastMonthSection({ categories }: { categories: CategorySummary[] }) {
  const hasComparison = categories.some((c) => c.previous_amount_base !== undefined);
  if (!hasComparison) return null;

  const sorted = [...categories].sort((a, b) => b.amount_base - a.amount_base);

  return (
    <div className="card">
      <SectionLabel>VS LAST PERIOD</SectionLabel>
      <div className="flex items-center gap-4 mb-2">
        <span className="text-[10px]" style={{ color: "var(--app-text-secondary)" }}>
          — current &nbsp; — previous
        </span>
      </div>
      {sorted.map((cat) => (
        <CategoryComparisonRow key={cat.category} category={cat} />
      ))}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function AnalyticsPage() {
  const [period, setPeriod] = useState<Period>("month");
  const { summary, budgets, isLoading, error, refetch } = useSummary(period);
  const { user } = useUser();

  const currency = summary?.base_currency ?? user?.base_currency ?? "USD";

  const insights = useMemo(
    () => (summary ? computeInsights(summary, budgets, currency) : []),
    [summary, budgets, currency]
  );

  return (
    <div className="page-content py-4">
      <PeriodSelector value={period} onChange={setPeriod} />

      {error && (
        <div className="card text-center">
          <p className="text-sm mb-3" style={{ color: "var(--app-text-secondary)" }}>
            Failed to load data
          </p>
          <button
            onClick={refetch}
            className="text-sm font-medium px-4 py-2 rounded-lg"
            style={{ backgroundColor: "var(--app-accent)", color: "var(--tg-theme-button-text-color, #fff)" }}
          >
            Retry
          </button>
        </div>
      )}

      {isLoading && !error && <AnalyticsSkeleton />}

      {!isLoading && !error && summary && (
        <>
          {summary.total_base === 0 ? (
            <div className="card text-center py-8">
              <p className="text-2xl mb-2">📭</p>
              <p className="text-sm" style={{ color: "var(--app-text-secondary)" }}>
                No expenses for this period
              </p>
            </div>
          ) : (
            <>
              <DailySpendingSection summary={summary} currency={currency} />

              {insights.length > 0 && (
                <div className="card mb-3">
                  <SectionLabel>INSIGHTS</SectionLabel>
                  {insights.map((insight, i) => (
                    <InsightCard key={i} {...insight} />
                  ))}
                </div>
              )}

              <VsLastMonthSection categories={summary.by_category} />
            </>
          )}
        </>
      )}
    </div>
  );
}
