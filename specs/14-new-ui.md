# Expense Tracker — Specification

A personal expense tracking mobile web app with budget management, recurring expenses, and interactive analytics. Dark theme, single-user, optimized for mobile.

## Screen Structure

The app has a fixed header and three tabs: **Overview**, **Trends**, **Budget**.

### Header (always visible)
- Month label ("April 2026") and "Day N of 30" subtitle
- Currency toggle (฿ / $)
- Summary card (purple gradient): total spent, % vs last month, three stats (avg/day, transaction count, % of budget used)

---

### Tab 1: Overview

The Overview tab is the default landing screen. It supports two independent filters that compose: **day filter** (from the heatmap) and **category filter** (from the category list).

#### 1.1 Daily Activity (Heatmap Calendar)
- A GitHub-style 30-day grid for the current month
- Each day is a small square (~18px). Color intensity reflects amount spent that day
- Recurring transactions (e.g., rent) are colored differently (purple) so they don't dominate the scale
- Future days are dimmed and non-interactive
- **Tap a day** to select it. The selected square scales up and gets a white outline. Tapping again deselects
- A banner above the grid shows the selected day's date, total amount, and transaction count. When nothing is selected, it shows "Tap a day to see details"
- Legend below: Less → More gradient and a "Recurring" swatch

#### 1.2 Spending Pace
**Only shown when no day is selected.** Hidden in day-detail mode.

The pace card splits spending into two tracks:
- **Day-to-day** (discretionary): excludes recurring expenses. Has a progress bar with:
  - Filled portion = actual spent so far
  - Vertical marker = projected end-of-month spending (`spent / daysElapsed * totalDays`)
  - End marker = budget limit
  - Status badge: ON TRACK (green) if projected ≤ budget × 1.1, else OVER PACE (red)
- **Recurring**: shown as a single line (no progress bar — recurring is always either fully paid or not, so a bar adds no information). Just `spent / budget`.

Below: a callout box showing **"You can spend per day"** — the daily allowance for the remaining days to stay within the discretionary budget.

#### 1.3 Category Breakdown (expandable, selectable)
A card titled "By Category" (or "Spending · Apr N" in day mode).

- **Header right side**: Total amount (in day mode) and an **Expand/Collapse** pill button that opens or closes all categories with subcategories at once
- **Each category row** shows:
  - Expand arrow ▶ (only if category has subs)
  - Icon, name, optional percentage of total (in day mode)
  - Spent amount + budget % (in month mode)
  - Progress bar relative to category budget (month mode) or relative to day total (day mode). Bar turns red when >90% of budget
- **Click behavior** has two zones:
  - Click on the **arrow** → expand/collapse subcategories
  - Click on the **rest of the row** → select this category as transaction filter (toggles)
- **Selected category** has a highlighted background (`COLORS.cardAlt`)
- **Subcategories** appear indented with a left border. Each shows: name, spent, budget, and a mini progress bar. Subcategories without budget show "no budget"
- **Click on a subcategory** → selects it as a more specific filter (overrides category filter)

#### 1.4 Transactions
List of transactions filtered by both day filter AND category filter (when active).

- Header shows context: "Transactions" / "Transactions · Apr N"
- When a category filter is active, a removable **chip** appears on the right showing the filter name with an × button to clear it
- Each transaction row: icon, name, optional `↻ auto` badge for recurring, category + date, amount in selected currency
- Empty state when filters yield nothing: "No transactions match this filter"

---

### Tab 2: Trends

#### 2.1 Vs Last Month
For each category, two stacked horizontal bars:
- Top bar: current month spending (full color)
- Bottom bar: previous month spending (40% opacity)
- Bars are normalized to the larger of the two values
- Right side: percentage change badge (green if down, red if up)
- Below each pair: "Now: $X" / "Prev: $Y" labels
- Legend at the bottom

#### 2.2 Insights
A card with bullet-style insights (emoji + text):
- "Food spending is 88% below March pace"
- "Housing is stable — within 3% of last month"
- "You've saved ~$1,750 so far vs March"

These should be generated from real data with simple heuristics (significant deltas, budget proximity, etc.).

---

### Tab 3: Budget

#### 3.1 Budget Overview Card
- Top row: total monthly budget (left) and remaining (right, green)
- Center: arc gauge showing % of total budget used
- Bottom row: three pills — On Track / Warning / Over — with counts of subcategories in each state
  - On track: <70% used
  - Warning: 70–90%
  - Over: >90%

#### 3.2 Budget Allocation (Donut Chart)
A donut showing how the total budget is divided across categories. Sorted by budget descending. Center label shows total budget. Legend on the right with percentage per category.

#### 3.3 Categories Section
Section card titled "CATEGORIES" with a pill **+ Add** button in the header (matches the Recurring section style).

Inside, an expandable list of all categories:
- **Each category row**:
  - Expand arrow (only if has subs)
  - Icon, name
  - Right side: % used badge (color-coded), spent / budget
  - Progress bar
  - **+ button** on the right edge to add a new subcategory
- Category budget = **sum of subcategory budgets** (not directly editable)
- **When expanded**, subcategories appear in a darker nested area:
  - Name, % used, spent / budget, mini progress bar
  - **✎ button** on the right to edit subcategory budget
  - Subcategories without budget show "no budget"

#### 3.4 Recurring Section
Section card titled "↻ RECURRING" with a pill **+ Add** button in the header.
- Each recurring item: icon, name, frequency, amount, **🗑️ delete button** (red on hover)
- Footer: "Total recurring: $X/mo"

---

## Filter Composition

The Overview tab has two filter dimensions that combine via AND:

| Day filter | Category filter | Behavior |
|---|---|---|
| none | none | Show full month |
| Apr 3 | none | Show transactions and categories for Apr 3 only |
| none | Food & Drinks | Show all month, list filtered to Food & Drinks |
| Apr 3 | Food & Drinks > Grocery | Show Apr 3 categories, list filtered to Grocery items on Apr 3 |

Spending Pace is hidden when a day is selected (it's only meaningful for the full month).
The category list always shows breakdown for the day filter context (or full month). The category filter affects only the transaction list.

## Interactions Summary

| Element | Action | Result |
|---|---|---|
| Heatmap day square | Tap | Toggle day filter |
| Category arrow ▶ | Tap | Expand/collapse that category |
| Category row body | Tap | Toggle category filter |
| Subcategory row | Tap | Toggle subcategory filter (overrides parent) |
| Filter chip × | Tap | Clear category filter |
| Expand/Collapse pill | Tap | Toggle all categories at once |
| Currency toggle | Tap ฿ or $ | Switch displayed currency app-wide |
| Tab buttons | Tap | Switch screen |
| Budget category + | Tap | Open "Add subcategory" dialog (TODO) |
| Subcategory ✎ | Tap | Open "Edit budget" dialog (TODO) |
| Recurring + Add | Tap | Open "Add recurring" dialog (TODO) |
| Recurring 🗑️ | Tap | Confirm + delete recurring rule |
| Categories + Add | Tap | Open "Add category" dialog (TODO) |



## Implementation Notes

- Keep a single `fmt(usd, currency, decimals)` helper. **Never** hardcode `$` or `฿` in JSX
- Computing subcategory spending from transactions: build a `subSpent[catName][subName]` map by iterating transactions once
- The Expand/Collapse-all button must check whether all expandable categories are currently expanded to decide its label and action
- All budget percentages are computed as `spent / budget * 100`. Cap visual bar widths at 100% but show actual percentage in text
- The pace projection formula: `projected = (spentDiscretionary / daysElapsed) * totalDays`. Recurring is excluded because it doesn't scale linearly with time

