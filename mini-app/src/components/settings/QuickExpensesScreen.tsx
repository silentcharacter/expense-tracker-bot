/** Full-screen editor for quick expenses — the one-tap buttons in the bot chat. */

import { useEffect, useState } from "react";
import { fetchCategories } from "../../api/categories";
import { ApiError } from "../../api/client";
import { fetchQuickExpenses, saveQuickExpenses } from "../../api/quickExpenses";
import type { CategoryInfo, QuickExpense } from "../../api/types";
import { CATEGORY_CONFIG, getCategoryLabel } from "../../utils/categories";
import { ConfirmDialog } from "./ConfirmDialog";

const NAME_MAX_LEN = 16;
const ROW_SIZE = 3;
const SYMBOL_RE = /^\p{So}/u;

// ── Button text — mirrors QuickExpense.button_text in models/quick_expense.py ──

function formatAmount(amount: number): string {
  if (Number.isInteger(amount)) return String(amount);
  return amount.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

function quickEmoji(item: QuickExpense): string {
  const emoji = item.emoji.trim();
  if (emoji && SYMBOL_RE.test(emoji)) return emoji;
  return CATEGORY_CONFIG[item.category]?.emoji ?? "⚡";
}

export function quickButtonText(item: QuickExpense, defaultCurrency: string): string {
  const label = `${quickEmoji(item)} ${item.name.trim()}`;
  if (item.amount === null) return `${label}…`;
  let text = `${label} ${formatAmount(item.amount)}`;
  const currency = (item.currency || defaultCurrency).toUpperCase();
  if (currency !== defaultCurrency.toUpperCase()) text += ` ${currency}`;
  return text;
}

// ── Screen ────────────────────────────────────────────────────────────────────

interface QuickExpensesScreenProps {
  defaultCurrency: string;
  baseCurrency: string;
  onClose: () => void;
}

export function QuickExpensesScreen({ defaultCurrency, baseCurrency, onClose }: QuickExpensesScreenProps) {
  const [items, setItems] = useState<QuickExpense[]>([]);
  const [limit, setLimit] = useState(9);
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ index: number | null; item: QuickExpense } | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchQuickExpenses(), fetchCategories()])
      .then(([quick, cats]) => {
        if (cancelled) return;
        setItems(quick.items);
        setLimit(quick.limit);
        setCategories(cats.categories);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(
          err instanceof ApiError && err.status === 501
            ? "Quick expenses are not available on this server."
            : "Could not load quick expenses.",
        );
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  function update(next: QuickExpense[]) {
    setItems(next);
    setDirty(true);
    setSaveError(null);
  }

  function move(index: number, delta: number) {
    const target = index + delta;
    if (target < 0 || target >= items.length) return;
    const next = [...items];
    [next[index], next[target]] = [next[target], next[index]];
    update(next);
  }

  function handleFormSave(item: QuickExpense) {
    if (!editing) return;
    if (editing.index === null) update([...items, item]);
    else update(items.map((it, i) => (i === editing.index ? item : it)));
    setEditing(null);
  }

  function handleFormDelete() {
    if (!editing || editing.index === null) return;
    update(items.filter((_, i) => i !== editing.index));
    setEditing(null);
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await saveQuickExpenses(items);
      setItems(saved.items);
      setDirty(false);
      setToast("Saved — the bot sent you the new buttons");
      setTimeout(() => setToast(null), 3000);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  function handleClose() {
    if (dirty) setConfirmDiscard(true);
    else onClose();
  }

  const newItem: QuickExpense = {
    name: "",
    emoji: "",
    category: categories[0]?.slug ?? "",
    subcategory: "",
    description: "",
    amount: null,
    currency: defaultCurrency,
  };

  const previewRows: QuickExpense[][] = [];
  for (let i = 0; i < items.length; i += ROW_SIZE) previewRows.push(items.slice(i, i + ROW_SIZE));

  return (
    <div className="fixed inset-0 z-50 flex flex-col" style={{ background: "var(--app-bg)" }}>
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 flex-shrink-0"
        style={{ borderBottom: "1px solid var(--app-border)" }}
      >
        <button
          onClick={handleClose}
          className="text-sm"
          style={{ color: "var(--app-accent)", background: "transparent", border: "none" }}
        >
          ‹ Back
        </button>
        <p className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
          Quick expenses
        </p>
        <button
          onClick={handleSave}
          disabled={!dirty || saving}
          className="text-sm font-semibold disabled:opacity-40"
          style={{ color: "var(--app-accent)", background: "transparent", border: "none" }}
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-4">
        <p className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
          These buttons sit under the input field in the bot chat. One tap saves the expense;
          buttons without an amount ask for it. You can also tap ⚡ Quick button under any saved
          expense in the chat.
        </p>

        {loading ? (
          <p className="text-sm text-center py-8" style={{ color: "var(--app-text-secondary)" }}>
            Loading…
          </p>
        ) : loadError ? (
          <p className="text-sm text-center py-8" style={{ color: "var(--app-danger)" }}>
            {loadError}
          </p>
        ) : (
          <>
            {/* Chat keyboard preview */}
            {items.length > 0 && (
              <div>
                <p
                  className="text-[11px] font-semibold uppercase tracking-wider mb-2"
                  style={{ color: "var(--app-text-secondary)" }}
                >
                  In the chat
                </p>
                <div
                  className="rounded-xl p-1.5 flex flex-col gap-1.5"
                  style={{ background: "var(--app-secondary-bg)" }}
                >
                  {previewRows.map((row, ri) => (
                    <div key={ri} className="flex gap-1.5">
                      {row.map((item, ci) => (
                        <div
                          key={item.id ?? `new-${ri}-${ci}`}
                          className="flex-1 min-w-0 rounded-lg px-1 py-2 text-xs text-center truncate"
                          style={{ background: "var(--app-bg)", color: "var(--app-text-primary)" }}
                        >
                          {quickButtonText(item, defaultCurrency)}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* List */}
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <p
                  className="text-[11px] font-semibold uppercase tracking-wider"
                  style={{ color: "var(--app-text-secondary)" }}
                >
                  ⚡ Buttons · {items.length}/{limit}
                </p>
                <button
                  onClick={() => setEditing({ index: null, item: newItem })}
                  disabled={items.length >= limit || categories.length === 0}
                  className="text-xs px-3 py-1 rounded-full font-medium disabled:opacity-40"
                  style={{ background: "var(--app-secondary-bg)", color: "var(--app-accent)", border: "none" }}
                >
                  + Add
                </button>
              </div>

              {items.length === 0 ? (
                <p className="text-sm text-center py-4" style={{ color: "var(--app-text-secondary)" }}>
                  No quick buttons yet
                </p>
              ) : (
                <div className="flex flex-col divide-y" style={{ borderColor: "var(--app-border)" }}>
                  {items.map((item, i) => (
                    <div key={item.id ?? `new-${i}`} className="flex items-center gap-2 py-2.5">
                      <button
                        className="flex-1 min-w-0 text-left"
                        style={{ background: "transparent", border: "none" }}
                        onClick={() => setEditing({ index: i, item })}
                      >
                        <p className="text-sm font-medium truncate" style={{ color: "var(--app-text-primary)" }}>
                          {quickButtonText(item, defaultCurrency)}
                        </p>
                        <p className="text-xs truncate" style={{ color: "var(--app-text-secondary)" }}>
                          {getCategoryLabel(item.category)}
                          {item.subcategory
                            ? ` / ${
                                categories
                                  .find((c) => c.slug === item.category)
                                  ?.subcategories.find((sc) => sc.slug === item.subcategory)?.label ??
                                item.subcategory
                              }`
                            : ""}
                          {item.amount === null ? " · asks amount" : ""}
                        </p>
                      </button>
                      <ReorderButton label="▲" disabled={i === 0} onClick={() => move(i, -1)} />
                      <ReorderButton label="▼" disabled={i === items.length - 1} onClick={() => move(i, 1)} />
                    </div>
                  ))}
                </div>
              )}
            </div>

            {saveError && (
              <p className="text-xs text-center" style={{ color: "var(--app-danger)" }}>
                {saveError}
              </p>
            )}
          </>
        )}
      </div>

      {toast && (
        <div
          className="fixed bottom-8 left-1/2 -translate-x-1/2 px-4 py-2 rounded-xl text-sm font-medium text-white z-50 whitespace-nowrap"
          style={{ background: "rgba(0,0,0,0.75)" }}
        >
          {toast}
        </div>
      )}

      {editing && (
        <QuickExpenseForm
          key={editing.index ?? "new"}
          initial={editing.item}
          isNew={editing.index === null}
          categories={categories}
          defaultCurrency={defaultCurrency}
          baseCurrency={baseCurrency}
          otherButtons={items
            .filter((_, i) => i !== editing.index)
            .map((it) => quickButtonText(it, defaultCurrency))}
          onSave={handleFormSave}
          onDelete={handleFormDelete}
          onClose={() => setEditing(null)}
        />
      )}

      {confirmDiscard && (
        <ConfirmDialog
          title="Discard changes?"
          message="Your edits to quick expenses have not been saved."
          confirmLabel="Discard"
          danger
          onConfirm={onClose}
          onCancel={() => setConfirmDiscard(false)}
        />
      )}
    </div>
  );
}

function ReorderButton({ label, disabled, onClick }: { label: string; disabled: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label === "▲" ? "Move up" : "Move down"}
      className="w-8 h-8 rounded-lg text-xs flex items-center justify-center disabled:opacity-30 flex-shrink-0"
      style={{ background: "var(--app-secondary-bg)", color: "var(--app-text-secondary)", border: "none" }}
    >
      {label}
    </button>
  );
}

// ── Form drawer ───────────────────────────────────────────────────────────────

interface QuickExpenseFormProps {
  initial: QuickExpense;
  isNew: boolean;
  categories: CategoryInfo[];
  defaultCurrency: string;
  baseCurrency: string;
  /** Button texts of the other presets — two buttons must not look the same. */
  otherButtons: string[];
  onSave: (item: QuickExpense) => void;
  onDelete: () => void;
  onClose: () => void;
}

const inputStyle = {
  background: "var(--app-secondary-bg)",
  color: "var(--app-text-primary)",
  border: "1px solid var(--app-border)",
};

function QuickExpenseForm({
  initial,
  isNew,
  categories,
  defaultCurrency,
  baseCurrency,
  otherButtons,
  onSave,
  onDelete,
  onClose,
}: QuickExpenseFormProps) {
  const [emoji, setEmoji] = useState(initial.emoji);
  const [name, setName] = useState(initial.name);
  const [category, setCategory] = useState(initial.category);
  const [subcategory, setSubcategory] = useState(initial.subcategory);
  const [amount, setAmount] = useState(initial.amount === null ? "" : String(initial.amount));
  const [currency, setCurrency] = useState((initial.currency || defaultCurrency).toUpperCase());

  const currencyOptions = Array.from(
    new Set([currency, defaultCurrency, baseCurrency, "USD", "EUR", "THB", "RUB"].map((c) => c.toUpperCase())),
  );
  const subcategories = categories.find((c) => c.slug === category)?.subcategories ?? [];

  const parsedAmount = amount.trim() === "" ? null : parseFloat(amount.replace(",", "."));
  const amountValid = parsedAmount === null || (!isNaN(parsedAmount) && parsedAmount > 0);

  const draft: QuickExpense = {
    ...initial,
    emoji: emoji.trim(),
    name: name.trim(),
    category,
    subcategory,
    amount: amountValid ? parsedAmount : null,
    currency,
  };
  const buttonText = quickButtonText(draft, defaultCurrency);
  const duplicate = otherButtons.includes(buttonText);
  const valid = draft.name.length > 0 && !!category && amountValid && !duplicate;

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
            {isNew ? "New quick button" : "Edit quick button"}
          </p>
          <button
            className="text-xs px-2 py-1 rounded"
            style={{ color: "var(--app-text-secondary)", border: "none", background: "transparent" }}
            onClick={onClose}
          >
            Cancel
          </button>
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            placeholder={quickEmoji({ ...draft, emoji: "" })}
            value={emoji}
            onChange={(e) => setEmoji(e.target.value)}
            maxLength={4}
            aria-label="Emoji"
            className="w-14 rounded-xl px-2 py-2.5 text-center text-lg outline-none"
            style={inputStyle}
          />
          <input
            type="text"
            placeholder="Name (e.g. Cafe)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={NAME_MAX_LEN}
            autoFocus={isNew}
            className="flex-1 min-w-0 rounded-xl px-3 py-2.5 text-sm outline-none"
            style={inputStyle}
          />
        </div>

        <div
          className="flex items-center rounded-xl overflow-hidden"
          style={{ background: "var(--app-secondary-bg)", border: "1px solid var(--app-border)" }}
        >
          <input
            type="text"
            inputMode="decimal"
            placeholder="Amount — empty to ask every time"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="flex-1 min-w-0 px-3 py-2.5 text-sm outline-none bg-transparent"
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

        <select
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setSubcategory("");
          }}
          className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
          style={inputStyle}
        >
          {categories.map((c) => (
            <option key={c.slug} value={c.slug}>
              {CATEGORY_CONFIG[c.slug]?.emoji ?? "⚡"} {c.label}
            </option>
          ))}
        </select>

        {subcategories.length > 0 && (
          <select
            value={subcategory}
            onChange={(e) => setSubcategory(e.target.value)}
            className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
            style={{ ...inputStyle, color: subcategory ? "var(--app-text-primary)" : "var(--app-text-secondary)" }}
          >
            <option value="">Subcategory (optional)</option>
            {subcategories.map((s) => (
              <option key={s.slug} value={s.slug}>
                {s.label}
              </option>
            ))}
          </select>
        )}

        <div className="flex items-center justify-between text-xs" style={{ color: "var(--app-text-secondary)" }}>
          <span>Button</span>
          <span
            className="px-3 py-1.5 rounded-lg"
            style={{ background: "var(--app-secondary-bg)", color: "var(--app-text-primary)" }}
          >
            {draft.name ? buttonText : "—"}
          </span>
        </div>
        {!amountValid && (
          <p className="text-xs" style={{ color: "var(--app-danger)" }}>
            Amount must be a positive number
          </p>
        )}
        {duplicate && (
          <p className="text-xs" style={{ color: "var(--app-danger)" }}>
            Another button already looks exactly like this
          </p>
        )}

        <button
          disabled={!valid}
          onClick={() => onSave(draft)}
          className="w-full py-3 rounded-xl text-sm font-semibold disabled:opacity-40"
          style={{ background: "var(--app-accent)", color: "#fff", border: "none" }}
        >
          {isNew ? "Add" : "Done"}
        </button>
        {!isNew && (
          <button
            onClick={onDelete}
            className="w-full py-2 text-sm font-medium"
            style={{ color: "var(--app-danger)", background: "transparent", border: "none" }}
          >
            Delete button
          </button>
        )}
      </div>
    </div>
  );
}
