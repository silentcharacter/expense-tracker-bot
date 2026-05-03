/** Budget sub-tab: summary + allocation chart + categories + recurring.
 *
 * Mutation flows (add/edit/delete category, subcategory, recurring) are handled
 * with lightweight drawer components inline here. After each mutation we call
 * `refetch` on MainPage's useMainData so the rest of the app sees fresh data.
 */

import { useRef, useState } from "react";
import { updateBudgets } from "../../api/budgets";
import { createCategory, createSubcategory, deleteCategory, deleteSubcategory } from "../../api/categories";
import { addRecurring, deleteRecurring, logRecurring } from "../../api/recurring";
import type {
  AddRecurringRequest,
  BudgetsResponse,
  RecurringResponse,
} from "../../api/types";
import { useTelegram } from "../../hooks/useTelegram";
import { getCategoryEmoji } from "../../utils/categories";
import { BudgetAllocationChart } from "../budget/BudgetAllocationChart";
import { BudgetCategories } from "../budget/BudgetCategories";
import { BudgetSummaryCard } from "../budget/BudgetSummaryCard";
import { RecurringSection } from "../budget/RecurringSection";

interface BudgetTabProps {
  budgets: BudgetsResponse | null;
  recurring: RecurringResponse | null;
  refetch: () => Promise<void>;
}

export function BudgetTab({ budgets, recurring, refetch }: BudgetTabProps) {
  const [showAddCategory, setShowAddCategory] = useState(false);
  const [addSubFor, setAddSubFor] = useState<{ slug: string; label: string } | null>(null);
  const [showAddRecurring, setShowAddRecurring] = useState(false);
  const { showConfirm } = useTelegram();

  const entries = budgets?.budgets ?? [];

  async function handleEditSub(catSlug: string, subSlug: string, amount: number) {
    await updateBudgets({ [`${catSlug}/${subSlug}`]: amount });
    await refetch();
  }

  async function handleDeleteSub(catSlug: string, subSlug: string) {
    const ok = await showConfirm("Delete this subcategory?");
    if (!ok) return;
    await deleteSubcategory(catSlug, subSlug);
    await refetch();
  }

  async function handleDeleteCat(catSlug: string) {
    const ok = await showConfirm("Delete this category and all its subcategories?");
    if (!ok) return;
    await deleteCategory(catSlug);
    await refetch();
  }

  async function handleCreateCategory(label: string) {
    await createCategory(label);
    await refetch();
  }

  async function handleCreateSub(catSlug: string, label: string) {
    await createSubcategory(catSlug, label);
    await refetch();
  }

  async function handleAddRecurring(entry: AddRecurringRequest) {
    await addRecurring(entry);
    await refetch();
  }

  async function handleDeleteRecurring(id: string) {
    await deleteRecurring(id);
    await refetch();
  }

  async function handleLogRecurring(id: string): Promise<'ok' | 'already_logged'> {
    const result = await logRecurring(id);
    if (result === 'ok') await refetch();
    return result;
  }

  return (
    <div className="flex flex-col">
      <BudgetSummaryCard
        budgets={entries}
        totalBudget={budgets?.total_budget ?? 0}
        totalSpent={budgets?.total_spent ?? 0}
      />
      <BudgetAllocationChart budgets={entries} />
      <BudgetCategories
        budgets={entries}
        onEditSubcategory={handleEditSub}
        onAddCategory={() => setShowAddCategory(true)}
        onAddSubcategory={(slug, label) => setAddSubFor({ slug, label })}
        onDeleteSubcategory={handleDeleteSub}
        onDeleteCategory={handleDeleteCat}
      />
      {recurring && (
        <RecurringSection
          data={recurring}
          onAdd={() => setShowAddRecurring(true)}
          onDelete={handleDeleteRecurring}
          onLog={handleLogRecurring}
        />
      )}

      {showAddCategory && (
        <SimpleInputDrawer
          title="New category"
          placeholder="Category name"
          confirmLabel="Create category"
          onConfirm={handleCreateCategory}
          onClose={() => setShowAddCategory(false)}
        />
      )}

      {addSubFor && (
        <SimpleInputDrawer
          title={`Add subcategory to ${getCategoryEmoji(addSubFor.slug)} ${addSubFor.label}`}
          placeholder="Subcategory name"
          confirmLabel="Add subcategory"
          onConfirm={(label) => handleCreateSub(addSubFor.slug, label)}
          onClose={() => setAddSubFor(null)}
        />
      )}

      {showAddRecurring && recurring && (
        <AddRecurringDrawer
          defaultCurrency={recurring.default_currency}
          baseCurrency={recurring.base_currency}
          categories={entries.map((b) => ({
            slug: b.category,
            label: b.label,
            subcategories: b.subcategories.map((s) => ({ slug: s.slug, label: s.label })),
          }))}
          onConfirm={handleAddRecurring}
          onClose={() => setShowAddRecurring(false)}
        />
      )}
    </div>
  );
}

// ── Simple text-input drawer ────────────────────────────────────────────────

interface SimpleInputDrawerProps {
  title: string;
  placeholder: string;
  confirmLabel: string;
  onConfirm: (value: string) => Promise<void>;
  onClose: () => void;
}

function SimpleInputDrawer({ title, placeholder, confirmLabel, onConfirm, onClose }: SimpleInputDrawerProps) {
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    if (!value.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onConfirm(value.trim());
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter") void confirm();
    if (e.key === "Escape") onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col justify-end"
      style={{ background: "rgba(0,0,0,0.5)" }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="rounded-t-2xl p-4 flex flex-col gap-3"
        style={{ background: "var(--app-bg)" }}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
            {title}
          </p>
          <button
            className="text-xs px-2 py-1 rounded"
            style={{ color: "var(--app-text-secondary)", border: "none", background: "transparent" }}
            onClick={onClose}
          >
            Cancel
          </button>
        </div>
        <input
          type="text"
          placeholder={placeholder}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKey}
          autoFocus
          className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
          style={{
            background: "var(--app-secondary-bg)",
            color: "var(--app-text-primary)",
            border: "1px solid var(--app-border)",
          }}
        />
        {error && (
          <p className="text-xs text-center" style={{ color: "var(--app-danger)" }}>
            {error}
          </p>
        )}
        <button
          disabled={!value.trim() || saving}
          onClick={confirm}
          className="w-full py-3 rounded-xl text-sm font-semibold"
          style={{
            background: value.trim() ? "var(--app-accent)" : "var(--app-secondary-bg)",
            color: value.trim() ? "#fff" : "var(--app-text-secondary)",
            border: "none",
          }}
        >
          {saving ? "Saving…" : confirmLabel}
        </button>
      </div>
    </div>
  );
}

// ── Add recurring drawer ────────────────────────────────────────────────────

interface AddRecurringDrawerProps {
  defaultCurrency: string;
  baseCurrency: string;
  categories: { slug: string; label: string; subcategories: { slug: string; label: string }[] }[];
  onConfirm: (entry: AddRecurringRequest) => Promise<void>;
  onClose: () => void;
}

function AddRecurringDrawer({
  defaultCurrency,
  baseCurrency,
  categories,
  onConfirm,
  onClose,
}: AddRecurringDrawerProps) {
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState(defaultCurrency);
  const [dayOfMonth, setDayOfMonth] = useState("1");
  const [category, setCategory] = useState("");
  const [subcategory, setSubcategory] = useState("");
  const [saving, setSaving] = useState(false);
  const descRef = useRef<HTMLInputElement>(null);

  const currencyOptions = Array.from(
    new Set([defaultCurrency, baseCurrency, "USD", "EUR", "THB", "RUB"].map((c) => c.toUpperCase())),
  );

  const subcategories = categories.find((c) => c.slug === category)?.subcategories ?? [];

  function handleCategoryChange(slug: string) {
    setCategory(slug);
    setSubcategory("");
  }

  async function confirm() {
    const amt = parseFloat(amount);
    const needsCategory = categories.length > 0;
    const needsSubcategory = category && subcategories.length > 0;
    if (!description.trim() || isNaN(amt) || amt <= 0) return;
    if (needsCategory && !category) return;
    if (needsSubcategory && !subcategory) return;
    setSaving(true);
    try {
      await onConfirm({
        description: description.trim(),
        amount_local: amt,
        local_currency: currency,
        day_of_month: parseInt(dayOfMonth, 10) || 1,
        category,
        subcategory,
      });
      onClose();
    } finally {
      setSaving(false);
    }
  }

  const needsCategory = categories.length > 0;
  const needsSubcategory = category && subcategories.length > 0;
  const valid =
    description.trim().length > 0 &&
    parseFloat(amount) > 0 &&
    (!needsCategory || !!category) &&
    (!needsSubcategory || !!subcategory);

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col justify-end"
      style={{ background: "rgba(0,0,0,0.5)" }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="rounded-t-2xl p-4 flex flex-col gap-3 max-h-[85vh] overflow-y-auto"
        style={{ background: "var(--app-bg)" }}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
            Add recurring expense
          </p>
          <button
            className="text-xs px-2 py-1 rounded"
            style={{ color: "var(--app-text-secondary)", border: "none", background: "transparent" }}
            onClick={onClose}
          >
            Cancel
          </button>
        </div>

        <input
          ref={descRef}
          type="text"
          placeholder="Description (e.g. Netflix)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          autoFocus
          className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
          style={{
            background: "var(--app-secondary-bg)",
            color: "var(--app-text-primary)",
            border: "1px solid var(--app-border)",
          }}
        />

        <div className="flex gap-2">
          <div
            className="flex-1 flex items-center rounded-xl overflow-hidden"
            style={{ background: "var(--app-secondary-bg)", border: "1px solid var(--app-border)" }}
          >
            <input
              type="number"
              min={0}
              placeholder="Amount"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="flex-1 px-3 py-2.5 text-sm outline-none bg-transparent"
              style={{ color: "var(--app-text-primary)" }}
            />
            <select
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              className="pr-2 text-xs font-medium outline-none bg-transparent cursor-pointer"
              style={{ color: "var(--app-text-secondary)", border: "none" }}
            >
              {currencyOptions.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <div
            className="flex items-center gap-1 rounded-xl px-3"
            style={{ background: "var(--app-secondary-bg)", border: "1px solid var(--app-border)" }}
          >
            <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
              Day
            </span>
            <input
              type="number"
              min={1}
              max={31}
              value={dayOfMonth}
              onChange={(e) => setDayOfMonth(e.target.value)}
              className="w-10 text-center text-sm outline-none bg-transparent"
              style={{ color: "var(--app-text-primary)" }}
            />
          </div>
        </div>

        {categories.length > 0 && (
          <select
            value={category}
            onChange={(e) => handleCategoryChange(e.target.value)}
            className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
            style={{
              background: "var(--app-secondary-bg)",
              color: category ? "var(--app-text-primary)" : "var(--app-text-secondary)",
              border: "1px solid var(--app-border)",
            }}
          >
            <option value="">Category</option>
            {categories.map((c) => (
              <option key={c.slug} value={c.slug}>
                {getCategoryEmoji(c.slug)} {c.label}
              </option>
            ))}
          </select>
        )}

        {category && subcategories.length > 0 && (
          <select
            value={subcategory}
            onChange={(e) => setSubcategory(e.target.value)}
            className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
            style={{
              background: "var(--app-secondary-bg)",
              color: subcategory ? "var(--app-text-primary)" : "var(--app-text-secondary)",
              border: "1px solid var(--app-border)",
            }}
          >
            <option value="">Subcategory</option>
            {subcategories.map((s) => (
              <option key={s.slug} value={s.slug}>
                {s.label}
              </option>
            ))}
          </select>
        )}

        <button
          disabled={!valid || saving}
          onClick={confirm}
          className="w-full py-3 rounded-xl text-sm font-semibold"
          style={{
            background: valid ? "var(--app-accent)" : "var(--app-secondary-bg)",
            color: valid ? "#fff" : "var(--app-text-secondary)",
            border: "none",
          }}
        >
          {saving ? "Adding…" : "Add recurring"}
        </button>
      </div>
    </div>
  );
}
