/** Overview page — summary, categories, and recent transactions. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Period } from "../api/summary";
import type { CategoryInfo, Expense } from "../api/types";
import { fetchExpenses } from "../api/expenses";
import { fetchCategories } from "../api/categories";
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
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);
  const [excludedCategories, setExcludedCategories] = useState<Set<string>>(new Set());
  const [showArrow, setShowArrow] = useState(false);

  const toggleExclude = useCallback((slug: string) => {
    setExcludedCategories((prev) => {
      const next = new Set(prev);
      next.has(slug) ? next.delete(slug) : next.add(slug);
      return next;
    });
  }, []);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!summary) return;
    const { start, end } = summary.date_range;
    fetchExpenses({ since: start, until: end, limit: 200 })
      .then((res) => setExpenses(res.expenses))
      .catch(() => setExpenses([]));
  }, [summary]);

  useEffect(() => {
    fetchCategories()
      .then((res) => setCategories(res.categories))
      .catch(() => setCategories([]));
  }, []);

  const currency = summary?.base_currency ?? user?.base_currency ?? "USD";

  const visibleSummary = useMemo(() => {
    if (!summary || excludedCategories.size === 0) return summary;
    const visibleCats = summary.by_category.filter((c) => !excludedCategories.has(c.category));
    const visibleTotal = visibleCats.reduce((s, c) => s + c.amount_base, 0);
    const start = new Date(summary.date_range.start + "T00:00:00");
    const end = new Date(summary.date_range.end + "T00:00:00");
    const days = Math.max(1, Math.round((end.getTime() - start.getTime()) / 86400000) + 1);
    const visibleTxCount = expenses.filter((e) => !excludedCategories.has(e.category)).length;
    return {
      ...summary,
      total_base: visibleTotal,
      daily_average: visibleTotal / days,
      transaction_count: visibleTxCount,
      by_category: visibleCats.map((c) => ({
        ...c,
        percentage: visibleTotal > 0 ? (c.amount_base / visibleTotal) * 100 : 0,
      })),
    };
  }, [summary, excludedCategories, expenses]);

  const budgetUsedPercent = useMemo(() => {
    if (!budgets?.budgets.length) return undefined;
    const visibleBudgets = excludedCategories.size > 0
      ? budgets.budgets.filter((b) => !excludedCategories.has(b.category))
      : budgets.budgets;
    if (!visibleBudgets.length) return undefined;
    const totalBudget = visibleBudgets.reduce((s, b) => s + b.budget, 0);
    const totalSpent = visibleBudgets.reduce((s, b) => s + b.spent, 0);
    if (totalBudget <= 0) return undefined;
    return (totalSpent / totalBudget) * 100;
  }, [budgets, excludedCategories]);

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

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const check = () => {
      setShowArrow(el.scrollHeight - el.scrollTop - el.clientHeight > 40);
    };
    check();
    el.addEventListener("scroll", check, { passive: true });
    return () => el.removeEventListener("scroll", check);
  }, [filteredExpenses]);

  return (
    <div className="page-content py-4" ref={scrollRef}>
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
                total={visibleSummary?.total_base ?? summary.total_base}
                currency={currency}
                transactionCount={visibleSummary?.transaction_count ?? summary.transaction_count}
                dailyAverage={visibleSummary?.daily_average ?? summary.daily_average}
                budgetUsedPercent={budgetUsedPercent}
                dateRange={summary.date_range}
                period={period}
                comparison={summary.comparison}
                excludedCount={excludedCategories.size}
              />
              <CategoryDonut
                data={visibleSummary?.by_category ?? summary.by_category}
                allCategories={summary.by_category}
                expenses={expenses}
                categories={categories}
                currency={currency}
                total={visibleSummary?.total_base ?? summary.total_base}
                selectedCategory={categoryFilter}
                onCategoryChange={setCategoryFilter}
                excludedCategories={excludedCategories}
                onToggleExclude={toggleExclude}
              />
              <SearchBar value={search} onChange={setSearch} />
              <CategoryFilter categories={summary.by_category} selected={categoryFilter} onChange={setCategoryFilter} />
              <TransactionList expenses={filteredExpenses} />
            </>
          )}
        </>
      )}
      <div
        style={{
          position: "fixed",
          bottom: "72px",
          left: "50%",
          transform: "translateX(-50%)",
          opacity: showArrow ? 1 : 0,
          transition: "opacity 300ms",
          pointerEvents: "none",
          zIndex: 10,
        }}
      >
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: "50%",
            backgroundColor: "var(--app-accent)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            opacity: 0.85,
          }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M4 6l4 4 4-4" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      </div>
    </div>
  );
}
