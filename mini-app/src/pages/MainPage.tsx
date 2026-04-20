/** Single-page shell: header, total card, sub-tabs, active tab body, settings modal. */

import { useState } from "react";
import { CurrencyProvider } from "../context/CurrencyContext";
import { useUser } from "../context/UserContext";
import { useMainData } from "../hooks/useMainData";
import { NewHeader } from "../components/layout/NewHeader";
import { SubTabBar } from "../components/layout/SubTabBar";
import type { SubTab } from "../components/layout/SubTabBar";
import { TotalCard } from "../components/dashboard/TotalCard";
import { SettingsModal } from "../components/settings/SettingsModal";
import { OverviewTab } from "../components/tabs/OverviewTab";
import { TrendsTab } from "../components/tabs/TrendsTab";
import { BudgetTab } from "../components/tabs/BudgetTab";
import type { CategoryFilter } from "../components/overview/CategoryBudgetList";
import { SkeletonBlock, SkeletonLine } from "../components/shared/Skeleton";

function TotalCardSkeleton() {
  return <SkeletonBlock height={140} className="rounded-xl mb-3" />;
}

function OverviewSkeleton() {
  return (
    <>
      <div className="card">
        <SkeletonLine height={12} width="40%" className="mb-3" />
        <SkeletonBlock height={120} />
      </div>
      <div className="card">
        <SkeletonLine height={12} width="50%" className="mb-3" />
        <SkeletonBlock height={80} />
      </div>
      <div className="card">
        <SkeletonLine height={12} width="35%" className="mb-3" />
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-3 py-2">
            <SkeletonBlock height={32} className="rounded-lg" />
            <div className="flex-1">
              <SkeletonLine height={12} width="60%" />
            </div>
            <SkeletonLine height={12} width="60px" />
          </div>
        ))}
      </div>
    </>
  );
}

function TrendsSkeleton() {
  return (
    <div className="card">
      <SkeletonLine height={12} width="40%" className="mb-3" />
      {[1, 2, 3, 4].map((i) => (
        <SkeletonBlock key={i} height={40} className="rounded-lg mb-2" />
      ))}
    </div>
  );
}

function BudgetSkeleton() {
  return (
    <>
      <SkeletonBlock height={180} className="rounded-xl mb-3" />
      <SkeletonBlock height={220} className="rounded-xl mb-3" />
      <div className="card">
        <SkeletonLine height={12} width="40%" className="mb-3" />
        {[1, 2, 3].map((i) => (
          <SkeletonBlock key={i} height={48} className="rounded-lg mb-2" />
        ))}
      </div>
    </>
  );
}

export function MainPage() {
  const { user } = useUser();
  const [monthOffset, setMonthOffset] = useState(0);
  const {
    summary,
    budgets,
    expenses,
    recurring,
    isLoading,
    error,
    refetch,
  } = useMainData(monthOffset);

  const [activeTab, setActiveTab] = useState<SubTab>("overview");
  const [showSettings, setShowSettings] = useState(false);
  const [filterDay, setFilterDay] = useState<string | null>(null);
  const [filterCategory, setFilterCategory] = useState<CategoryFilter | null>(null);

  function handleMonthChange(next: number) {
    if (next === monthOffset) return;
    setMonthOffset(next);
    setFilterDay(null);
    setFilterCategory(null);
  }

  const baseCurrency = summary?.base_currency ?? user?.base_currency ?? "USD";
  const defaultCurrency =
    summary?.default_currency ?? user?.default_currency ?? baseCurrency;
  const rate = summary?.default_currency_rate ?? 1;

  const now = new Date();
  const viewedMonth = new Date(now.getFullYear(), now.getMonth() + monthOffset, 1);
  const viewedYear = viewedMonth.getFullYear();
  const viewedMonthIndex = viewedMonth.getMonth();
  const daysInMonth = new Date(viewedYear, viewedMonthIndex + 1, 0).getDate();
  const dayOfMonth = now.getDate();

  const budgetTotal = (budgets?.budgets ?? []).reduce((s, b) => s + b.budget, 0);
  const budgetUsedPercent =
    budgetTotal > 0 && summary ? (summary.total_base / budgetTotal) * 100 : undefined;

  return (
    <CurrencyProvider
      baseCurrency={baseCurrency}
      defaultCurrency={defaultCurrency}
      rate={rate}
    >
      <div
        className="page-content"
        style={{ backgroundColor: "var(--app-bg)", color: "var(--app-text-primary)" }}
      >
        <NewHeader
          dayOfMonth={dayOfMonth}
          daysInMonth={daysInMonth}
          monthOffset={monthOffset}
          onMonthOffsetChange={handleMonthChange}
          onOpenSettings={() => setShowSettings(true)}
        />

        {error && !summary ? (
          <div className="card text-center py-8">
            <p className="text-2xl mb-2">⚠️</p>
            <p className="text-sm mb-3" style={{ color: "var(--app-text-secondary)" }}>
              {error}
            </p>
            <button
              type="button"
              onClick={() => void refetch()}
              className="px-4 py-2 rounded-full text-sm font-semibold"
              style={{
                background: "var(--app-accent)",
                color: "#fff",
                border: "none",
              }}
            >
              Retry
            </button>
          </div>
        ) : (
          <>
            {summary ? (
              <TotalCard
                total={summary.total_base}
                totalDefault={summary.total_default}
                transactionCount={summary.transaction_count}
                dailyAverage={summary.daily_average}
                budgetUsedPercent={budgetUsedPercent}
                comparison={summary.comparison}
                dateRange={summary.date_range}
              />
            ) : (
              <TotalCardSkeleton />
            )}

            <SubTabBar active={activeTab} onChange={setActiveTab} />

            <div key={activeTab} className="subtab-enter">
              {activeTab === "overview" &&
                (isLoading && !summary ? (
                  <OverviewSkeleton />
                ) : (
                  <OverviewTab
                    summary={summary}
                    budgets={budgets}
                    expenses={expenses}
                    referenceYear={viewedYear}
                    referenceMonth={viewedMonthIndex}
                    filterDay={filterDay}
                    filterCategory={filterCategory}
                    onSelectDay={setFilterDay}
                    onSelectCategory={setFilterCategory}
                  />
                ))}

              {activeTab === "trends" &&
                (isLoading && !summary ? <TrendsSkeleton /> : <TrendsTab summary={summary} />)}

              {activeTab === "budget" &&
                (isLoading && !budgets ? (
                  <BudgetSkeleton />
                ) : (
                  <BudgetTab budgets={budgets} recurring={recurring} refetch={refetch} />
                ))}
            </div>
          </>
        )}
      </div>

      <SettingsModal open={showSettings} onClose={() => setShowSettings(false)} />
    </CurrencyProvider>
  );
}
