/** API response types for the Mini App REST API. */

// ── Summary ──────────────────────────────────────────────────────────────────

export interface CategorySummary {
  category: string;
  amount_base: number;
  amount_default: number;
  percentage: number;
  transaction_count: number;
  previous_amount_base?: number;
  change_percent?: number;
}

export interface CurrencySummary {
  currency: string;
  amount_local: number;
  amount_base: number;
}

export interface DailyTotal {
  date: string;
  amount_base: number;
  amount_default: number;
}

export interface PeriodComparison {
  previous_total: number;
  change_percent: number;
  direction: "up" | "down";
}

export interface SpendingPace {
  days_elapsed: number;
  days_in_month: number;
  total_spent: number;
  recurring_spent: number;
  recurring_spent_default?: number;
  discretionary_spent: number;
  discretionary_spent_default?: number;
  recurring_total: number;
  discretionary_budget: number;
  budget_total: number;
  projected_discretionary: number;
  projected_discretionary_default?: number;
  available_per_day: number;
  available_per_day_default?: number | null;
  status: "on_track" | "over_pace";
}

export interface SummaryResponse {
  period: string;
  date_range: { start: string; end: string };
  total_base: number;
  total_default: number;
  base_currency: string;
  transaction_count: number;
  daily_average: number | null;
  daily_average_default?: number | null;
  by_category: CategorySummary[];
  by_currency: CurrencySummary[];
  daily_totals: DailyTotal[];
  comparison?: PeriodComparison;
  days_remaining?: number;
  spending_pace?: SpendingPace;
  default_currency?: string;
  default_currency_rate?: number | null;
}

// ── Expenses ─────────────────────────────────────────────────────────────────

export interface Expense {
  id: string;
  timestamp: string;
  amount_local: number;
  local_currency: string;
  amount_base: number;
  amount_default: number;
  base_currency: string;
  fx_rate: number;
  category: string;
  subcategory: string;
  description: string;
  source: "voice" | "text" | "photo";
  is_recurring?: boolean;
}

export interface ExpensesResponse {
  expenses: Expense[];
  total: number;
  limit: number;
  offset: number;
}

export interface DeleteExpenseResponse {
  deleted: boolean;
  expense: Expense;
}

export interface UpdateExpenseRequest {
  description: string;
  amount_local: number;
  local_currency: string;
  category: string;
  subcategory: string;
  date: string; // YYYY-MM-DD
}

// ── Budgets ───────────────────────────────────────────────────────────────────

export interface SubcategoryBudgetEntry {
  slug: string;
  label: string;
  budget: number;
  spent: number;
  remaining: number;
  percentage: number;
  status: "normal" | "warning" | "exceeded";
}

export interface BudgetEntry {
  category: string;
  label: string;
  budget: number;
  spent: number;
  remaining: number;
  percentage: number;
  status: "normal" | "warning" | "exceeded";
  subcategories: SubcategoryBudgetEntry[];
}

export interface BudgetsResponse {
  base_currency: string;
  month: string;
  total_budget: number;
  total_spent: number;
  budgets: BudgetEntry[];
}

// ── Settings ──────────────────────────────────────────────────────────────────

export interface UserSettings {
  telegram_id: number;
  display_name: string;
  username: string;
  email: string;
  base_currency: string;
  default_currency: string;
  spreadsheet_id: string;
  role: string;
  created_at: string;
  budget_alerts: boolean;
  weekly_summary: boolean;
  insights: boolean;
}

export interface UpdateSettingsRequest {
  base_currency?: string;
  default_currency?: string;
  budget_alerts?: boolean;
  weekly_summary?: boolean;
  insights?: boolean;
}

export interface ExportParams {
  start?: string;
  end?: string;
}

export interface UpdateBudgetsRequest {
  budgets: Record<string, number>;
}

// ── Categories ────────────────────────────────────────────────────────────────

export interface SubcategoryInfo {
  slug: string;
  label: string;
}

export interface CategoryInfo {
  slug: string;
  label: string;
  subcategories: SubcategoryInfo[];
}

export interface CategoriesResponse {
  categories: CategoryInfo[];
}

export interface CreateCategoryRequest {
  label: string;
}

// ── Recurring ─────────────────────────────────────────────────────────────────

export interface RecurringItem {
  id: string;
  category: string;
  subcategory: string;
  description: string;
  amount_base: number;
  amount_local: number;
  local_currency: string;
  day_of_month: number;
}

export interface RecurringResponse {
  base_currency: string;
  default_currency: string;
  items: RecurringItem[];
  /** Sum of items, in base currency. */
  total: number;
}

export interface AddRecurringRequest {
  description: string;
  amount_local: number;
  local_currency?: string;
  day_of_month?: number;
  category?: string;
  subcategory?: string;
}
