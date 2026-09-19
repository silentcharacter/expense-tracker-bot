/** Overview sub-tab: active trip → heatmap → pace → category breakdown → transactions. */

import type {
  BudgetsResponse,
  ExpensesResponse,
  SummaryResponse,
  TripEntry,
  UpdateExpenseRequest,
} from "../../api/types";
import { TransactionList } from "../dashboard/TransactionList";
import { CategoryBudgetList } from "../overview/CategoryBudgetList";
import type { CategoryFilter } from "../overview/CategoryBudgetList";
import { DailyHeatmap } from "../overview/DailyHeatmap";
import { SpendingPace } from "../overview/SpendingPace";
import { ActiveTripBanner } from "../trips/ActiveTripBanner";

interface OverviewTabProps {
  summary: SummaryResponse | null;
  budgets: BudgetsResponse | null;
  expenses: ExpensesResponse | null;
  /** 4-digit year of the viewed month. */
  referenceYear: number;
  /** Month index (0-11) of the viewed month. */
  referenceMonth: number;
  /** Trip that new expenses are being tagged with, if any. */
  activeTrip?: TripEntry | null;
  /** Switch to the Trips tab. */
  onOpenTrips?: () => void;
  /** trip id → trip name, for the 🧳 badge on transactions. */
  tripNames?: Record<string, string>;
  filterDay: string | null;
  filterCategory: CategoryFilter | null;
  onSelectDay: (day: string | null) => void;
  onSelectCategory: (filter: CategoryFilter | null) => void;
  onDeleteExpense?: (id: string) => Promise<void>;
  onEditExpense?: (id: string, data: UpdateExpenseRequest) => Promise<void>;
}

export function OverviewTab({
  summary,
  budgets,
  expenses,
  referenceYear,
  referenceMonth,
  activeTrip = null,
  onOpenTrips,
  tripNames,
  filterDay,
  filterCategory,
  onSelectDay,
  onSelectCategory,
  onDeleteExpense,
  onEditExpense,
}: OverviewTabProps) {
  const expenseList = expenses?.expenses ?? [];
  const budgetEntries = budgets?.budgets ?? [];
  const pace = summary?.spending_pace;

  return (
    <div className="flex flex-col">
      {activeTrip && onOpenTrips && (
        <ActiveTripBanner trip={activeTrip} onOpen={onOpenTrips} />
      )}

      <DailyHeatmap
        expenses={expenseList}
        referenceYear={referenceYear}
        referenceMonth={referenceMonth}
        selectedDay={filterDay}
        onDaySelect={onSelectDay}
      />

      {filterDay === null && pace && <SpendingPace pace={pace} />}

      <CategoryBudgetList
        budgets={budgetEntries}
        expenses={expenseList}
        filterDay={filterDay}
        selected={filterCategory}
        onSelect={onSelectCategory}
      />

      <TransactionList
        expenses={expenseList}
        filterDay={filterDay}
        filterCategory={filterCategory}
        onClearCategoryFilter={() => onSelectCategory(null)}
        onDeleteExpense={onDeleteExpense}
        onEditExpense={onEditExpense}
        tripNames={tripNames}
        showHeader
      />
    </div>
  );
}
