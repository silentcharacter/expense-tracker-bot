# Mini App UI Redesign Plan

## Context

The current mini-app has 4 bottom tabs (Overview, Analytics, Budget, Settings) as separate routed pages. The new design consolidates everything into a single scrollable page with 3 sub-tabs (Overview, Trends, Budget) and a settings gear icon in the header. Key additions: spending pace projection, daily activity heatmap, currency toggle (base/default), and integrated budget-per-category view in Overview.

**Recurring expenses architecture:** Recurring items in the `Reccuring` sheet are templates only. A daily cron job iterates them and inserts an `ExpenseRecord` (with `recurring=TRUE` flag) into the Transactions sheet for items whose `day_of_month` matches today. Therefore:
- `recurring_spent` for the month = SUM of `ExpenseRecord` where `recurring=TRUE` in current month
- `recurring_total` for the month = SUM of all items in `Reccuring` sheet (the monthly template total)
- The `recurring` flag on transactions enables exact (not heuristic) detection of recurring expenses

---

## Phase 1: Backend Changes

### 1.1 Add `recurring` column to `ExpenseRecord` and Transactions sheet
**File:** [expense.py](models/expense.py) — `ExpenseRecord` (line 72)

- Add field: `recurring: bool = Field(default=False)`
- Append `"TRUE"`/`"FALSE"` string at end of `to_sheet_row()`
- Append `"recurring"` to `sheet_headers()`

**File:** [sheets.py](services/sheets.py) — `get_transactions()` and related parsers
- When reading rows, parse `recurring` cell as bool (`"TRUE" -> True`)
- Handle legacy rows without the column (default False)
- Existing user spreadsheets: add header detection / lazy migration when missing — append column header on first write if absent

### 1.2 Create daily cron job to materialize recurring expenses
**New file:** `jobs/recurring_cron.py` (or extend existing entry)

- HTTP-triggered Cloud Function (called by Cloud Scheduler daily)
- Iterates Master Registry, for each user:
  - Fetch `Reccuring` sheet items
  - For items where `day_of_month == today.day`:
    - Build `ExpenseRecord` with `recurring=True`, source=`text` (or new `recurring` source enum), description from template, amounts via `CurrencyService` if conversion needed
    - Append to user's Transactions sheet via `sheets.append_transaction()`
- Idempotency: check if a recurring transaction with the same template id + month already exists before inserting (store `recurring_template_id` in description metadata, OR add a separate column)
- Add `deploy_recurring_cron.sh` script and Cloud Scheduler config

**Note on idempotency:** simplest approach — add a `recurring_template_id` field/column to `ExpenseRecord`, and on cron run check if any record exists for `(template_id, year, month)` before inserting.

### 1.3 Add `spending_pace` to `GET /api/summary`
**File:** [routes.py](api/routes.py) — `_api_summary()` (line 237)

When `period=month` and `offset=0`, compute and return:
```python
"spending_pace": {
    "days_elapsed": today.day,
    "days_in_month": monthrange(year, month)[1],
    "total_spent": total_base,
    "recurring_spent": <SUM of records where recurring=True>,
    "discretionary_spent": total_base - recurring_spent,
    "recurring_total": <SUM of items in Reccuring sheet>,
    "discretionary_budget": budget_total - recurring_total,  # day-to-day budget
    "budget_total": <SUM of all category budgets>,
    "projected_discretionary": (discretionary_spent / days_elapsed * days_in_month),
    "available_per_day": max(0, discretionary_budget - discretionary_spent) / max(1, days_remaining),
    "status": "on_track" | "over_pace"
}
```
**Key formula** (per spec §1.2): `projected = (discretionary_spent / days_elapsed) × days_in_month`. Recurring is **excluded** from projection because it doesn't scale linearly with time.
- `recurring_spent` is a trivial sum over records with `recurring=True`
- `recurring_total` from `sheets.get_recurring(spreadsheet_id)` — used for the recurring row (no progress bar)
- Status: `on_track` if `projected_discretionary ≤ discretionary_budget × 1.1`, else `over_pace`
- Return `null` for non-current-month requests

### 1.4 Add `default_currency_rate` to summary response
**File:** [routes.py](api/routes.py) — `_api_summary()`

Add to response:
```python
"default_currency": user.default_currency,
"default_currency_rate": <float>  # 1 base = X default
```
Use `CurrencyService.get_rate(base_currency, default_currency)` to get the rate.

### 1.5 Expose `recurring` flag in expenses API
**File:** [routes.py](api/routes.py) — `_record_to_dict()` (line 219)

Add `"is_recurring": record.recurring` directly from the model. No heuristic needed.

---

## Phase 2: Frontend Types & Infrastructure

### 2.1 Update API types
**File:** [types.ts](mini-app/src/api/types.ts)

Add:
```typescript
export interface SpendingPace {
  days_elapsed: number;
  days_in_month: number;
  total_spent: number;
  recurring_spent: number;
  discretionary_spent: number;
  recurring_total: number;
  discretionary_budget: number;
  budget_total: number;
  projected_discretionary: number;
  available_per_day: number;
  status: "on_track" | "over_pace";
}
```

Extend `SummaryResponse`:
```typescript
spending_pace?: SpendingPace;
default_currency?: string;
default_currency_rate?: number;
```

Extend `Expense`:
```typescript
is_recurring?: boolean;
```

### 2.2 Create `CurrencyContext`
**New file:** `mini-app/src/context/CurrencyContext.tsx`

```typescript
interface CurrencyContextValue {
  displayMode: "base" | "default";
  baseCurrency: string;
  defaultCurrency: string;
  rate: number;
  toggle: () => void;
  convert: (amountBase: number) => number;
  format: (amountBase: number) => string;
}
```
- Reads user settings for currency codes, summary for rate
- `convert()` returns `amountBase * rate` in default mode, `amountBase` in base mode
- `format()` calls `formatAmount(convert(amount), activeCurrency)`

### 2.3 Create `useMainData` hook
**New file:** `mini-app/src/hooks/useMainData.ts`

Fetches all data once on mount (parallel):
- `fetchSummary("month", true, 0)` — with compare=true for Trends tab
- `fetchBudgets()`
- `fetchExpenses({ since: monthStart, until: monthEnd, limit: 200 })`
- `fetchCategories()`
- `fetchRecurring()`

Returns: `{ summary, budgets, expenses, categories, recurring, isLoading, error, refetch }`

### 2.4 Update globals.css
**File:** [globals.css](mini-app/src/styles/globals.css)

- Remove `bottom: 56px` from `.page-content` (no more TabBar)
- Add heatmap color variables (Less→More gradient + recurring purple swatch) and spending pace bar styles

### 2.5 Currency formatting helper
**File:** `mini-app/src/utils/format.ts` (extend existing or create)

Per spec implementation note: keep a single `fmt(usdAmount, currency, decimals)` helper. **Never** hardcode `$` or `฿` in JSX. All JSX amount rendering must go through `CurrencyContext.format()` (which internally uses `fmt`).

---

## Phase 3: Shared UI Components

### 3.1 `NewHeader`
**New file:** `mini-app/src/components/layout/NewHeader.tsx`

- Left: "April 2026" (month/year), "Day N of M" subtitle
- Right: currency toggle (2 buttons with symbols), gear icon -> opens Settings
- Fixed at top

### 3.2 `SubTabBar`
**New file:** `mini-app/src/components/layout/SubTabBar.tsx`

- 3 pill-style tabs: Overview / Trends / Budget
- Active tab highlighted with accent
- Haptic feedback on switch

### 3.3 Modify `TotalCard`
**File:** [TotalCard.tsx](mini-app/src/components/dashboard/TotalCard.tsx)

- Remove period/dateRange props (always current month)
- Use `CurrencyContext` for all amounts
- Keep: purple gradient, total, comparison %, AVG/DAY, TXNS, BUDGET %

### 3.4 `SettingsModal`
**New file:** `mini-app/src/components/settings/SettingsModal.tsx`

- Full-screen overlay with slide-in animation
- Reuses existing `SettingsPage` content as-is
- Close button at top

---

## Phase 4: Overview Tab

### 4.1 `DailyHeatmap`
**New file:** `mini-app/src/components/overview/DailyHeatmap.tsx`

Per spec §1.1 — GitHub-style 30-day grid:
- Grid of ~18px squares for every day in the current month
- Color intensity reflects amount spent that day (4 levels based on quartiles of non-recurring spend)
- **Recurring days are colored differently (purple)** — entirely, not a dot — so they don't dominate the scale. A day is "recurring-dominant" when its spend comes mostly from records with `is_recurring=true`
- Future days are dimmed and **non-interactive** (no tap)
- **Selected day**: scales up + white outline. Tap again to deselect (toggle)
- **Banner above the grid**: shows selected day's date, total amount, transaction count. When nothing is selected, shows "Tap a day to see details"
- **Legend below**: Less → More gradient swatch + a "Recurring" purple swatch
- Click a day → calls `onDaySelect(date)` (toggles)

### 4.2 `SpendingPace`
**New file:** `mini-app/src/components/overview/SpendingPace.tsx`

Per spec §1.2 — **only shown when no day is selected**. Hidden in day-detail mode (rendered conditionally by OverviewTab based on `filterDay`).

Two tracks:
- **Day-to-day (discretionary)**:
  - Status badge: **ON TRACK** (green) if `projected_discretionary ≤ discretionary_budget × 1.1`, else **OVER PACE** (red)
  - Progress bar with three visual elements:
    - Filled portion = `discretionary_spent` so far
    - Vertical marker on the bar = `projected_discretionary` (end-of-month projection)
    - End of bar = `discretionary_budget` (limit)
  - Spent / Projected / Budget labels under the bar
- **Recurring**: shown as a single line `{recurring_spent} / {recurring_total}` — **no progress bar** (recurring is binary: paid or not, a bar adds no information)

Below the two tracks: a callout box **"You can spend per day"** showing `available_per_day` for the remaining days to stay within the discretionary budget.

All amounts via `CurrencyContext.format()`.

### 4.3 `CategoryBudgetList`
**New file:** `mini-app/src/components/overview/CategoryBudgetList.tsx`

Per spec §1.3:
- **Header**:
  - Title: `"By Category"` in month mode, **`"Spending · Apr N"`** in day mode
  - Right side: total amount (in day mode only) and an **Expand/Collapse pill button** that toggles all expandable categories at once. The button label/action is computed by checking whether *all* expandable categories are currently expanded
- **Each category row**:
  - Expand arrow `▶` (only if category has subcategories)
  - Icon, name
  - In day mode: percentage of day total
  - In month mode: spent amount + budget % text (e.g., "฿1,200 · 45%")
  - Progress bar — relative to category budget (month mode) or relative to day total (day mode). Bar **turns red when >90% of budget**
- **Two click zones**:
  - Click on the **arrow** → expand/collapse this category's subcategories
  - Click on the **rest of the row** → toggle this category as the transaction filter
- **Selected category** has a highlighted background (`COLORS.cardAlt` equivalent CSS variable)
- **Subcategories** appear indented under the parent with a left border. Each shows: name, spent, budget, mini progress bar. Subcategories without a budget show **"no budget"** instead of a bar
- **Click on a subcategory** → selects it as a more specific filter and **overrides the parent category filter**
- Data source: merge `budgets` + `summary.by_category` (and per-day breakdown derived from filtered expenses when `filterDay` is set)

### 4.4 Enhance `TransactionList`
**File:** [TransactionList.tsx](mini-app/src/components/dashboard/TransactionList.tsx)

Per spec §1.4:
- **Header context**: `"Transactions"` in month mode, **`"Transactions · Apr N"`** when day filter is active
- **Filter chip**: when a category filter is active, show a removable chip on the right side of the header with the filter name and an `×` button to clear it (only the category filter — day filter is cleared via the heatmap)
- **Each transaction row**: icon, name, **`↻ auto` badge** for recurring (per spec wording — not "recurring"), category + date, amount in selected currency
- Use `CurrencyContext.format()` for all amounts (no hardcoded `$`/`฿`)
- Accept `filterDay` and `filterCategory` props; filter via AND
- **Empty state** when filters yield no results: `"No transactions match this filter"`
- Keep existing: emoji square, description, category+date, amount, stagger animation

### 4.5 `OverviewTab` composition
**New file:** `mini-app/src/components/tabs/OverviewTab.tsx`

Composition order:
1. `DailyHeatmap`
2. `SpendingPace` — **rendered only when `filterDay === null`** (hidden in day-detail mode per spec §1.2)
3. `CategoryBudgetList` — always rendered, shows breakdown for the day filter context (or full month). The category filter affects only the transaction list, not the breakdown
4. `TransactionList` — filtered by both `filterDay` AND `filterCategory` (composed via AND per spec Filter Composition table)

Filter state (`filterDay`, `filterCategory`) managed in parent `MainPage`, passed down. Subcategory selection overrides category selection (single `filterCategory` slot, with sub slug taking precedence).

---

## Phase 5: Trends Tab

### 5.1 `VsLastMonth`
**New file:** `mini-app/src/components/trends/VsLastMonth.tsx`

- "VS LAST MONTH" header
- Each category: emoji + name, change % badge (green=decrease, red=increase)
- Dual horizontal bars: current (solid) vs previous (40% opacity)
- "Now: {amount}" / "Prev: {amount}" below bars
- Legend: "Current" / "{prev month name}"
- Data from `summary.by_category` with `previous_amount_base` and `change_percent`

### 5.2 `Insights`
**New file:** `mini-app/src/components/trends/Insights.tsx`

- Pace-based auto-generated insight cards with emojis
- Computed from summary comparison data:
  - "{Category} spending is X% below {month} pace"
  - "{Category} is stable - within X% of last month"
  - "You've saved ~{amount} so far vs {month}"
- Reuses existing `InsightCard` component for rendering

### 5.3 `TrendsTab` composition
**New file:** `mini-app/src/components/tabs/TrendsTab.tsx`

Composes: VsLastMonth -> Insights

---

## Phase 6: Budget Tab

### 6.1 `BudgetSummaryCard`
**New file:** `mini-app/src/components/budget/BudgetSummaryCard.tsx`

Per spec §3.1:
- Top row: total monthly budget (left) and remaining (right, green)
- Center: arc gauge showing % of total budget used
- Bottom row: three pills with **counts of subcategories in each state**:
  - **On Track**: `<70%` used (green)
  - **Warning**: `70–90%` used (yellow)
  - **Over**: `>90%` used (red)
- Extract from current `BudgetDonut` / `SummaryRing` in BudgetPage but rebucket the thresholds (current code uses different cutoffs)

### 6.2 `BudgetAllocationChart`
**New file:** `mini-app/src/components/budget/BudgetAllocationChart.tsx`

- Donut chart: budget allocation by category
- Total budget in center
- Legend: category names + percentages
- Extract from existing `BudgetDonut` in BudgetPage

### 6.3 `BudgetCategories`
Extract existing `CategorySection` + `SubRow` + edit/add drawers from BudgetPage into:
**New file:** `mini-app/src/components/budget/BudgetCategories.tsx`

Per spec §3.3:
- Section card titled **"CATEGORIES"** with a pill **+ Add** button in the section header (matches Recurring section style)
- **Each category row**:
  - Expand arrow (only if has subs)
  - Icon, name
  - Right side: % used badge (color-coded by 70/90 thresholds), `spent / budget`
  - Progress bar
  - **+ button** on the right edge → opens "Add subcategory" dialog
  - **No ✎ edit pencil on the category itself** — category budget is **the sum of its subcategory budgets** and is **not directly editable** per spec
- **When expanded**, subcategories appear in a darker nested area:
  - Name, % used, `spent / budget`, mini progress bar
  - **✎ edit button** on the right → opens "Edit budget" dialog (subcategory only)
  - Subcategories without budget show **"no budget"**
- The existing `BudgetPage` allows editing category budgets directly — that flow must be removed; only subcategory editing remains

### 6.4 `RecurringSection`
Extract recurring management from BudgetPage into:
**New file:** `mini-app/src/components/budget/RecurringSection.tsx`

Per spec §3.4:
- Section card titled **"↻ RECURRING"** with a pill **+ Add** button in the header
- Each recurring item: icon, name, frequency (e.g., "Monthly · Nth"), amount, **🗑️ delete button** (red on hover, with confirm)
- Footer: **"Total recurring: $X/mo"**

### 6.5 `BudgetTab` composition
**New file:** `mini-app/src/components/tabs/BudgetTab.tsx`

Composes: BudgetSummaryCard -> BudgetAllocationChart -> BudgetCategories -> RecurringSection

---

## Phase 7: Integration

### 7.1 Build `MainPage`
**New file:** `mini-app/src/pages/MainPage.tsx`

```
CurrencyProvider
  NewHeader (currency toggle + settings gear)
  TotalCard
  SubTabBar (overview | trends | budget)
  {activeTab === "overview" && <OverviewTab />}
  {activeTab === "trends" && <TrendsTab />}
  {activeTab === "budget" && <BudgetTab />}
  {showSettings && <SettingsModal />}
```

State: `activeTab`, `showSettings`, `filterDay`, `filterCategory`

### 7.2 Rewrite `App.tsx`
**File:** [App.tsx](mini-app/src/App.tsx)

- Remove HashRouter, Routes, TabBar, PageTransition
- Single component: `ThemeProvider > UserProvider > MainPage`
- Keep `useTelegram()` init

### 7.3 Clean up deleted files
Remove:
- `components/layout/TabBar.tsx`
- `components/layout/PageTransition.tsx`
- `components/layout/Header.tsx`
- `components/dashboard/PeriodSelector.tsx`
- `components/dashboard/DailyChart.tsx`
- `components/dashboard/CategoryDonut.tsx`
- `components/dashboard/CategoryFilter.tsx`
- `components/dashboard/SearchBar.tsx`
- `pages/DashboardPage.tsx`
- `pages/AnalyticsPage.tsx`
- `pages/BudgetPage.tsx` (logic extracted to components)

Keep: `pages/SettingsPage.tsx` (reused inside SettingsModal)

---

## Phase 8: Polish

- Skeleton loading states per section (not blocking entire page)
- Sub-tab switch animation (fade/slide)
- Haptic feedback on: sub-tab switch, day tap, category tap, currency toggle
- Empty states for each section
- Dark theme consistency check (all new components use CSS variables)

---

## Implementation Order

1. **Backend schema** (Phase 1.1) — add `recurring` column to ExpenseRecord + sheets
2. **Cron job** (Phase 1.2) — daily recurring materialization (deploy + test before frontend depends on it)
3. **Backend API** (Phases 1.3–1.5) — spending_pace, default_currency_rate, is_recurring flag
4. **Types + Context + Hook** (Phase 2) — foundation for all frontend
5. **Shared UI** (Phase 3) — header, sub-tabs, total card, settings modal
6. **Overview tab** (Phase 4) — biggest new feature
7. **Trends tab** (Phase 5) — can parallel with Budget
8. **Budget tab** (Phase 6) — can parallel with Trends
9. **Integration** (Phase 7) — wire everything together
10. **Polish** (Phase 8)

---

## Verification

1. `pytest tests/` — backend tests pass with new `recurring` field
2. Manually trigger cron locally: insert a recurring item with today's `day_of_month`, run job, verify transaction appears with `recurring=True`
3. Run cron a second time same day → no duplicate (idempotency check)
4. `cd mini-app && npm run build` — no TypeScript errors
5. `npm run dev` — visual check of all 3 sub-tabs
6. Currency toggle switches all amounts on every tab
7. Click day in heatmap → transactions filtered to that day
8. Click category in By Category → transactions filtered to that category
9. Spending pace shows correct projection: manually verify `projected_discretionary = (discretionary_spent / days_elapsed) × days_in_month` (recurring excluded)
10. Spending Pace card is **hidden** when a day is selected in the heatmap
11. Heatmap: future days are non-interactive; recurring-dominant days are purple; selected day scales up with white outline
12. Category list: arrow toggles expand, row body toggles filter; subcategory click overrides parent; >90% bars are red
13. Filter chip with × appears in Transactions header when category filter is active
14. Settings modal opens/closes, changes persist
15. Budget tab: only subcategory ✎ edits budgets (category total = sum of subs); add/delete recurring, add subcategory all work
16. Budget summary pills bucket subcategories correctly: <70% on track, 70–90% warning, >90% over
17. Trends tab: comparison bars and insights show correct data
18. Recurring transactions show **`↻ auto`** badge in Overview transaction list
19. No `$` or `฿` literals in any new JSX — all amounts go through `CurrencyContext.format()` / `fmt()` helper
