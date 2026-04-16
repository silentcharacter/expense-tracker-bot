/** CATEGORIES section: list of all categories with expandable subcategories.
 *
 * Per spec §3.3: category budget is the sum of its subs and is NOT editable —
 * only subcategories get a ✎ edit button. Each category row has a + button
 * that opens "Add subcategory". The section header has a pill "+ Add" button
 * for creating a new category.
 */

import { useRef, useState } from "react";
import type { BudgetEntry, SubcategoryBudgetEntry } from "../../api/types";
import { useCurrency } from "../../context/CurrencyContext";
import { useTelegram } from "../../hooks/useTelegram";
import { getCategoryColor, getCategoryEmoji, getCategoryLabel } from "../../utils/categories";

interface BudgetCategoriesProps {
  budgets: BudgetEntry[];
  onEditSubcategory: (catSlug: string, subSlug: string, amount: number) => Promise<void>;
  onAddCategory: () => void;
  onAddSubcategory: (catSlug: string, catLabel: string) => void;
  onDeleteSubcategory: (catSlug: string, subSlug: string) => Promise<void>;
  onDeleteCategory: (catSlug: string) => Promise<void>;
}

function pctColor(pct: number): string {
  if (pct > 90) return "var(--app-danger)";
  if (pct >= 70) return "#fbbf24";
  return "var(--app-success)";
}

const HIDE_UNSET_STORAGE_KEY = "budget_hide_unset";

export function BudgetCategories({
  budgets,
  onEditSubcategory,
  onAddCategory,
  onAddSubcategory,
  onDeleteSubcategory,
  onDeleteCategory,
}: BudgetCategoriesProps) {
  const { hapticFeedback } = useTelegram();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [hideUnset, setHideUnset] = useState<boolean>(
    () => localStorage.getItem(HIDE_UNSET_STORAGE_KEY) === "true",
  );

  function toggleHideUnset() {
    hapticFeedback?.selectionChanged();
    setHideUnset((prev) => {
      const next = !prev;
      localStorage.setItem(HIDE_UNSET_STORAGE_KEY, String(next));
      return next;
    });
  }

  function toggleExpand(catSlug: string) {
    hapticFeedback?.selectionChanged();
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(catSlug)) next.delete(catSlug);
      else next.add(catSlug);
      return next;
    });
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <p
          className="text-[11px] font-semibold uppercase tracking-wider"
          style={{ color: "var(--app-text-secondary)" }}
        >
          Categories
        </p>
        <div className="flex items-center gap-2">
          <button
            onClick={toggleHideUnset}
            className="text-xs px-3 py-1 rounded-full font-medium"
            style={{
              background: hideUnset ? "var(--app-accent)" : "var(--app-secondary-bg)",
              color: hideUnset ? "#fff" : "var(--app-text-secondary)",
              border: "none",
            }}
          >
            {hideUnset ? "Show all" : "Hide unset"}
          </button>
          <button
            onClick={onAddCategory}
            className="text-xs px-3 py-1 rounded-full font-medium"
            style={{ background: "var(--app-secondary-bg)", color: "var(--app-accent)", border: "none" }}
          >
            + Add
          </button>
        </div>
      </div>

      {budgets.length === 0 && (
        <p className="text-sm text-center py-4" style={{ color: "var(--app-text-secondary)" }}>
          No categories yet. Tap + Add to create one.
        </p>
      )}

      <div className="flex flex-col">
        {[...budgets].sort((a, b) => b.spent - a.spent).map((entry) => {
          const visibleSubs = hideUnset
            ? entry.subcategories.filter((s) => s.budget > 0)
            : entry.subcategories;
          if (hideUnset && entry.budget === 0 && visibleSubs.length === 0) return null;
          const hasSubs = visibleSubs.length > 0;
          const isExpanded = expanded.has(entry.category);
          const hasBudget = entry.budget > 0;
          const pct = hasBudget ? entry.percentage : 0;
          const barPct = Math.min(pct, 100);
          const color = pctColor(pct);
          const catColor = getCategoryColor(entry.category);

          return (
            <div key={entry.category} className="py-1">
              <div className="flex items-center gap-2 py-2">
                <button
                  type="button"
                  onClick={() => hasSubs && toggleExpand(entry.category)}
                  className="w-5 h-5 flex items-center justify-center flex-shrink-0"
                  style={{
                    color: "var(--app-text-secondary)",
                    border: "none",
                    background: "transparent",
                    visibility: hasSubs ? "visible" : "hidden",
                    transform: isExpanded ? "rotate(90deg)" : "none",
                    transition: "transform 120ms ease",
                    fontSize: 10,
                  }}
                  aria-label={isExpanded ? "Collapse" : "Expand"}
                >
                  ▶
                </button>

                <span className="text-lg flex-shrink-0">{getCategoryEmoji(entry.category)}</span>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span
                      className="text-sm font-medium truncate"
                      style={{ color: "var(--app-text-primary)" }}
                    >
                      {getCategoryLabel(entry.category)}
                    </span>
                    {hasBudget && (
                      <div className="flex items-center gap-1.5 flex-shrink-0 text-xs">
                        <span
                          className="px-1.5 py-0.5 rounded-full font-semibold"
                          style={{ background: `${color}22`, color }}
                        >
                          {Math.round(pct)}%
                        </span>
                        <CategoryAmount spent={entry.spent} budget={entry.budget} />
                      </div>
                    )}
                  </div>
                  {hasBudget && (
                    <div
                      className="h-1 rounded-full overflow-hidden"
                      style={{ background: "var(--app-secondary-bg)" }}
                    >
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${barPct}%`,
                          background: pct > 90 ? "var(--app-danger)" : catColor,
                          transition: "width 0.4s ease",
                        }}
                      />
                    </div>
                  )}
                </div>

                <button
                  onClick={() => onAddSubcategory(entry.category, entry.label)}
                  className="flex items-center justify-center w-6 h-6 rounded-full text-sm font-bold flex-shrink-0"
                  style={{
                    background: "var(--app-secondary-bg)",
                    color: "var(--app-accent)",
                    border: "none",
                  }}
                  title="Add subcategory"
                >
                  +
                </button>

                <button
                  onClick={() => onDeleteCategory(entry.category)}
                  className="p-1 flex-shrink-0"
                  style={{ color: "var(--app-danger)", opacity: 0.3, border: "none", background: "transparent" }}
                  title="Delete category"
                >
                  <svg width={12} height={12} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5}>
                    <path d="M2 4h12M5 4V2h6v2M6 7v5M10 7v5M3 4l1 9h8l1-9" />
                  </svg>
                </button>
              </div>

              {hasSubs && isExpanded && (
                <div
                  className="ml-6 pl-3 py-2 rounded-lg"
                  style={{ background: "var(--app-secondary-bg)" }}
                >
                  {visibleSubs.map((sub) => (
                    <SubRow
                      key={sub.slug}
                      catSlug={entry.category}
                      sub={sub}
                      onEdit={onEditSubcategory}
                      onDelete={onDeleteSubcategory}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CategoryAmount({ spent, budget }: { spent: number; budget: number }) {
  const { format } = useCurrency();
  return (
    <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
      <span className="amount" style={{ color: "var(--app-text-primary)" }}>
        {format(spent, 0)}
      </span>
      {" / "}
      <span className="amount">{format(budget, 0)}</span>
    </span>
  );
}

interface SubRowProps {
  catSlug: string;
  sub: SubcategoryBudgetEntry;
  onEdit: (catSlug: string, subSlug: string, amount: number) => Promise<void>;
  onDelete: (catSlug: string, subSlug: string) => Promise<void>;
}

function SubRow({ catSlug, sub, onEdit, onDelete }: SubRowProps) {
  const { format, displayMode } = useCurrency();
  const canEdit = displayMode === "base";
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(sub.budget > 0 ? String(sub.budget) : "");
  const inputRef = useRef<HTMLInputElement>(null);

  const hasBudget = sub.budget > 0;
  const pct = hasBudget ? sub.percentage : 0;
  const barPct = Math.min(pct, 100);
  const color = pctColor(pct);

  function startEdit() {
    setVal(sub.budget > 0 ? String(sub.budget) : "");
    setEditing(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  }

  async function commit() {
    setEditing(false);
    const amount = parseFloat(val);
    if (!isNaN(amount) && amount >= 0) {
      await onEdit(catSlug, sub.slug, amount);
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter") void commit();
    if (e.key === "Escape") setEditing(false);
  }

  return (
    <div className="py-1.5 pl-2">
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="text-sm truncate" style={{ color: "var(--app-text-primary)" }}>
          {sub.label}
        </span>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {editing ? (
            <input
              ref={inputRef}
              type="number"
              min={0}
              value={val}
              onChange={(e) => setVal(e.target.value)}
              onBlur={commit}
              onKeyDown={handleKey}
              className="w-24 text-right text-xs rounded px-1.5 py-0.5 outline-none"
              style={{
                background: "var(--app-card-bg)",
                color: "var(--app-text-primary)",
                border: "1px solid var(--app-accent)",
              }}
            />
          ) : hasBudget ? (
            <>
              <span
                className="px-1.5 py-0.5 rounded-full text-[11px] font-semibold"
                style={{ background: `${color}22`, color }}
              >
                {Math.round(pct)}%
              </span>
              <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
                <span className="amount" style={{ color: "var(--app-text-primary)" }}>
                  {format(sub.spent, 0)}
                </span>
                {" / "}
                <span className="amount">{format(sub.budget, 0)}</span>
              </span>
              {canEdit && (
                <button
                  onClick={startEdit}
                  className="p-0.5 opacity-60"
                  style={{ color: "var(--app-text-secondary)", border: "none", background: "transparent" }}
                  title="Edit budget"
                >
                  <svg width={12} height={12} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5}>
                    <path d="M11.5 2.5l2 2-9 9H2.5v-2l9-9z" />
                  </svg>
                </button>
              )}
            </>
          ) : canEdit ? (
            <button
              onClick={startEdit}
              className="text-xs"
              style={{ color: "var(--app-text-secondary)", border: "none", background: "transparent" }}
            >
              no budget
            </button>
          ) : (
            <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
              no budget
            </span>
          )}
          <button
            onClick={() => onDelete(catSlug, sub.slug)}
            className="p-0.5 opacity-30"
            style={{ color: "var(--app-danger)", border: "none", background: "transparent" }}
            title="Delete subcategory"
          >
            <svg width={12} height={12} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5}>
              <path d="M2 4h12M5 4V2h6v2M6 7v5M10 7v5M3 4l1 9h8l1-9" />
            </svg>
          </button>
        </div>
      </div>
      {hasBudget && (
        <div
          className="h-0.5 rounded-full overflow-hidden"
          style={{ background: "var(--app-card-bg)" }}
        >
          <div
            className="h-full rounded-full"
            style={{ width: `${barPct}%`, background: color, transition: "width 0.4s ease" }}
          />
        </div>
      )}
    </div>
  );
}
