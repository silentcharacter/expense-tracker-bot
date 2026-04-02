/** API response types for the Mini App REST API. */

// ── Summary ──────────────────────────────────────────────────────────────────

export interface CategorySummary {
  category: string;
  amount_base: number;
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
}

export interface PeriodComparison {
  previous_total: number;
  change_percent: number;
  direction: "up" | "down";
}

export interface SummaryResponse {
  period: string;
  date_range: { start: string; end: string };
  total_base: number;
  base_currency: string;
  transaction_count: number;
  daily_average: number;
  by_category: CategorySummary[];
  by_currency: CurrencySummary[];
  daily_totals: DailyTotal[];
  comparison?: PeriodComparison;
  days_remaining?: number;
}

// ── Expenses ─────────────────────────────────────────────────────────────────

export interface Expense {
  id: string;
  timestamp: string;
  amount_local: number;
  local_currency: string;
  amount_base: number;
  base_currency: string;
  fx_rate: number;
  category: string;
  subcategory: string;
  description: string;
  source: "voice" | "text" | "photo";
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
