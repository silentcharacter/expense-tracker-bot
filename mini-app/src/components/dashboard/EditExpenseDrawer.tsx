import { useEffect, useRef, useState } from "react";
import { fetchCategories } from "../../api/categories";
import type { CategoryInfo, Expense, UpdateExpenseRequest } from "../../api/types";
import { getCategoryEmoji } from "../../utils/categories";

interface EditExpenseDrawerProps {
  expense: Expense;
  onConfirm: (data: UpdateExpenseRequest) => Promise<void>;
  onClose: () => void;
}

const CURRENCY_OPTIONS = ["USD", "EUR", "THB", "RUB", "GBP", "SGD", "CNY"];

export function EditExpenseDrawer({ expense, onConfirm, onClose }: EditExpenseDrawerProps) {
  const [description, setDescription] = useState(expense.description);
  const [amount, setAmount] = useState(String(expense.amount_local));
  const [currency, setCurrency] = useState(expense.local_currency);
  const [category, setCategory] = useState(expense.category);
  const [subcategory, setSubcategory] = useState(expense.subcategory ?? "");
  const [date, setDate] = useState(expense.timestamp.slice(0, 10));
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const descRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchCategories()
      .then((r) => setCategories(r.categories))
      .catch(() => {});
  }, []);

  const currencyOptions = Array.from(
    new Set([currency, ...CURRENCY_OPTIONS].map((c) => c.toUpperCase())),
  );

  const subcategories = categories.find((c) => c.slug === category)?.subcategories ?? [];

  function handleCategoryChange(slug: string) {
    setCategory(slug);
    setSubcategory("");
  }

  const needsSubcategory = category && subcategories.length > 0;
  const valid =
    description.trim().length > 0 &&
    parseFloat(amount) > 0 &&
    !!category &&
    !!date &&
    (!needsSubcategory || !!subcategory);

  async function confirm() {
    if (!valid) return;
    setSaving(true);
    setError(null);
    try {
      await onConfirm({
        description: description.trim(),
        amount_local: parseFloat(amount),
        local_currency: currency,
        category,
        subcategory,
        date,
      });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col justify-end"
      style={{ background: "rgba(0,0,0,0.5)" }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="rounded-t-2xl p-4 flex flex-col gap-3 max-h-[90vh] overflow-y-auto"
        style={{ background: "var(--app-bg)" }}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
            Edit transaction
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
          placeholder="Description"
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

        <div
          className="flex items-center rounded-xl overflow-hidden"
          style={{ background: "var(--app-secondary-bg)", border: "1px solid var(--app-border)" }}
        >
          <input
            type="number"
            min={0}
            step="any"
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

        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
          style={{
            background: "var(--app-secondary-bg)",
            color: date ? "var(--app-text-primary)" : "var(--app-text-secondary)",
            border: "1px solid var(--app-border)",
          }}
        />

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

        {needsSubcategory && (
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

        {error && (
          <p className="text-xs px-1" style={{ color: "var(--app-danger)" }}>
            {error}
          </p>
        )}

        <button
          disabled={!valid || saving}
          onClick={() => void confirm()}
          className="w-full py-3 rounded-xl text-sm font-semibold"
          style={{
            background: valid ? "#22c55e" : "var(--app-secondary-bg)",
            color: valid ? "#fff" : "var(--app-text-secondary)",
            border: "none",
          }}
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
