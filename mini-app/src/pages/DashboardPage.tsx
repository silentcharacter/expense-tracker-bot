/** Overview page — summary, categories, and recent transactions. */

import { useEffect, useMemo, useState } from "react";
import type { Period } from "../api/summary";
import type { Expense } from "../api/types";
import { fetchExpenses } from "../api/expenses";
import { useUser } from "../context/UserContext";
import { useSummary } from "../hooks/useSummary";
import { PeriodSelector } from "../components/dashboard/PeriodSelector";
import { TotalCard } from "../components/dashboard/TotalCard";
import { CategoryDonut } from "../components/dashboard/CategoryDonut";
import { SearchBar } from "../components/dashboard/SearchBar";
import { CategoryFilter } from "../components/dashboard/CategoryFilter";
import { TransactionList } from "../components/dashboard/TransactionList";
import { SkeletonBlock, SkeletonLine } from "../components/shared/Skeleton";

function DashboardSkeleton() {
  return (
    <>
      <SkeletonBlock height={180} className="rounded-xl mb-3" />
      <div className="card">
        <SkeletonLine height={12} width="80px" className="mb-3" />
        <SkeletonBlock height={130} />
      </div>
      <SkeletonBlock height={44} className="rounded-xl mb-3" />
      <SkeletonBlock height={36} className="rounded-full mb-3" />
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex items-center gap-3 py-3">
          <SkeletonBlock height={40} className="rounded-xl" />
          <div className="flex-1">
            <SkeletonLine height={14} width="60%" className="mb-1" />
            <SkeletonLine height={11} width="40%" />
          </div>
          <SkeletonLine height={14} width="60px" />
        </div>
      ))}
    </>
  );
}

export function DashboardPage() {
  const [period, setPeriod] = useState<Period>("month");
  const { summary, budgets, isLoading, error, refetch } = useSummary(period);
  const { user } = useUser();

  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);

  useEffect(() => {
    if (!summary) return;
    const { start, end } = summary.date_range;
    fetchExpenses({ since: start, until: end, limit: 200 })
      .then((res) => setExpenses(res.expenses))
      .catch(() => setExpenses([]));
  }, [summary]);

  const currency = summary?.base_currency ?? user?.base_currency ?? "USD";

  const budgetUsedPercent = useMemo(() => {
    if (!budgets?.budgets.length) return undefined;
    const totalBudget = budgets.budgets.reduce((s, b) => s + b.budget, 0);
    const totalSpent = budgets.budgets.reduce((s, b) => s + b.spent, 0);
    if (totalBudget <= 0) return undefined;
    return (totalSpent / totalBudget) * 100;
  }, [budgets]);

  const filteredExpenses = useMemo(() => {
    let result = expenses;
    if (categoryFilter) {
      result = result.filter((e) => e.category === categoryFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (e) =>
          e.description.toLowerCase().includes(q) ||
          e.category.toLowerCase().includes(q)
      );
    }
    return result;
  }, [expenses, categoryFilter, search]);

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

      {isLoading && !error && <DashboardSkeleton />}

      {!isLoading && !error && summary && (
        <>
          {summary.total_base === 0 && !expenses.length ? (
            <div className="card text-center py-8">
              <p className="text-2xl mb-2">📭</p>
              <p className="text-sm" style={{ color: "var(--app-text-secondary)" }}>
                No expenses for this period
              </p>
            </div>
          ) : (
            <>
              <TotalCard
                total={summary.total_base}
                currency={currency}
                transactionCount={summary.transaction_count}
                dailyAverage={summary.daily_average}
                budgetUsedPercent={budgetUsedPercent}
                dateRange={summary.date_range}
                period={period}
                comparison={summary.comparison}
              />
              <CategoryDonut
                data={summary.by_category}
                currency={currency}
                total={summary.total_base}
              />
              <SearchBar value={search} onChange={setSearch} />
              <CategoryFilter categories={summary.by_category} selected={categoryFilter} onChange={setCategoryFilter} />
              <TransactionList expenses={filteredExpenses} />
            </>
          )}
        </>
      )}
    </div>
  );
}
