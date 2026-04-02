import { useState, useEffect, useRef } from "react";
import type { BudgetEntry, SubcategoryBudgetEntry } from "../api/types";
import { fetchBudgets, updateBudgets } from "../api/budgets";
import { createCategory } from "../api/categories";
import { getCategoryEmoji } from "../utils/categories";
import { formatAmount } from "../utils/format";

// ── Summary ring ─────────────────────────────────────────────────────────────

function SummaryRing({ pct }: { pct: number }) {
  const r = 54;
  const circ = 2 * Math.PI * r;
  const fill = Math.min(pct, 100);
  const offset = circ * (1 - fill / 100);
  const color =
    pct > 100 ? "var(--app-danger)" : pct >= 80 ? "#fbbf24" : "var(--app-accent)";

  return (
    <svg width={130} height={130} viewBox="0 0 130 130">
      <circle cx={65} cy={65} r={r} fill="none" stroke="var(--app-secondary-bg)" strokeWidth={10} />
      <circle
        cx={65} cy={65} r={r} fill="none"
        stroke={color} strokeWidth={10} strokeLinecap="round"
        strokeDasharray={circ} strokeDashoffset={offset}
        transform="rotate(-90 65 65)"
        style={{ transition: "stroke-dashoffset 0.5s ease" }}
      />
      <text x={65} y={60} textAnchor="middle" dominantBaseline="middle" fill={color} fontSize={20} fontWeight={700}>
        {Math.round(fill)}%
      </text>
      <text x={65} y={80} textAnchor="middle" dominantBaseline="middle" fill="var(--app-text-secondary)" fontSize={10}>
        used
      </text>
    </svg>
  );
}

// ── Subcategory budget row ────────────────────────────────────────────────────

interface SubRowProps {
  catSlug: string;
  entry: SubcategoryBudgetEntry;
  currency: string;
  onEdit: (catSlug: string, subSlug: string, value: string) => void;
}

function SubRow({ catSlug, entry, currency, onEdit }: SubRowProps) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(entry.budget > 0 ? String(entry.budget) : "");
  const inputRef = useRef<HTMLInputElement>(null);

  const hasBudget = entry.budget > 0;
  const fillPct = Math.min(entry.percentage, 100);
  const barColor =
    entry.status === "exceeded" ? "var(--app-danger)" :
    entry.status === "warning" ? "#fbbf24" : "var(--app-accent)";

  function startEdit() {
    setVal(entry.budget > 0 ? String(entry.budget) : "");
    setEditing(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  }

  function commit() {
    setEditing(false);
    const amount = parseFloat(val);
    if (!isNaN(amount) && amount >= 0) {
      onEdit(catSlug, entry.slug, val);
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter") commit();
    if (e.key === "Escape") setEditing(false);
  }

  return (
    <div className="py-2 pl-5 cursor-pointer" onClick={() => !editing && startEdit()}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm" style={{ color: "var(--app-text-primary)" }}>
          {entry.label}
        </span>
        <div className="flex items-center gap-1">
          {editing ? (
            <input
              ref={inputRef}
              type="number"
              min={0}
              value={val}
              onChange={(e) => setVal(e.target.value)}
              onBlur={commit}
              onKeyDown={handleKey}
              onClick={(e) => e.stopPropagation()}
              className="w-24 text-right text-xs rounded px-1.5 py-0.5 outline-none"
              style={{
                background: "var(--app-secondary-bg)",
                color: "var(--app-text-primary)",
                border: "1px solid var(--app-accent)",
              }}
            />
          ) : hasBudget ? (
            <>
              <span className="text-xs font-medium" style={{ color: barColor }}>
                {formatAmount(entry.spent, currency, 0)}
              </span>
              <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
                / {formatAmount(entry.budget, currency, 0)}
              </span>
            </>
          ) : (
            <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
              tap to set
            </span>
          )}
        </div>
      </div>
      {hasBudget && (
        <div className="h-1 rounded-full overflow-hidden" style={{ background: "var(--app-secondary-bg)" }}>
          <div
            className="h-full rounded-full"
            style={{ width: `${fillPct}%`, background: barColor, transition: "width 0.4s ease" }}
          />
        </div>
      )}
      {entry.status === "exceeded" && hasBudget && (
        <p className="text-xs mt-0.5" style={{ color: "var(--app-danger)" }}>
          Over by {formatAmount(Math.abs(entry.remaining), currency, 0)}
        </p>
      )}
    </div>
  );
}

// ── Category section ──────────────────────────────────────────────────────────

interface CategorySectionProps {
  entry: BudgetEntry;
  currency: string;
  onEdit: (catSlug: string, subSlug: string, value: string) => void;
}

function CategorySection({ entry, currency, onEdit }: CategorySectionProps) {
  const emoji = getCategoryEmoji(entry.category);
  const hasBudget = entry.budget > 0;
  const fillPct = Math.min(entry.percentage, 100);
  const barColor =
    entry.status === "exceeded" ? "var(--app-danger)" :
    entry.status === "warning" ? "#fbbf24" : "var(--app-accent)";

  return (
    <div className="mb-1">
      {/* Category header */}
      <div className="flex items-center justify-between py-2">
        <span className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
          {emoji} {entry.label}
        </span>
        {hasBudget && (
          <div className="flex items-center gap-1">
            <span className="text-xs font-semibold" style={{ color: barColor }}>
              {formatAmount(entry.spent, currency, 0)}
            </span>
            <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
              / {formatAmount(entry.budget, currency, 0)}
            </span>
          </div>
        )}
      </div>
      {/* Category aggregate progress bar */}
      {hasBudget && (
        <div className="h-1 rounded-full overflow-hidden mb-1" style={{ background: "var(--app-secondary-bg)" }}>
          <div
            className="h-full rounded-full"
            style={{ width: `${fillPct}%`, background: barColor, transition: "width 0.4s ease" }}
          />
        </div>
      )}
      {/* Subcategory rows */}
      <div className="flex flex-col divide-y" style={{ borderColor: "var(--app-secondary-bg)" }}>
        {entry.subcategories.map((sub) => (
          <SubRow
            key={sub.slug}
            catSlug={entry.category}
            entry={sub}
            currency={currency}
            onEdit={onEdit}
          />
        ))}
      </div>
    </div>
  );
}

// ── Bottom drawer ─────────────────────────────────────────────────────────────

interface DrawerSubItem {
  catSlug: string;
  catLabel: string;
  sub: SubcategoryBudgetEntry;
}

interface DrawerProps {
  unbudgetedSubs: DrawerSubItem[];
  currency: string;
  onSetBudget: (key: string, amount: number) => Promise<void>;
  onCreateCategory: (label: string) => Promise<void>;
  onClose: () => void;
}

function BudgetDrawer({ unbudgetedSubs, currency, onSetBudget, onCreateCategory, onClose }: DrawerProps) {
  const [selected, setSelected] = useState<DrawerSubItem | null>(null);
  const [amount, setAmount] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newLabel, setNewLabel] = useState("");
  const [saving, setSaving] = useState(false);
  const amountRef = useRef<HTMLInputElement>(null);
  const labelRef = useRef<HTMLInputElement>(null);

  function selectSub(item: DrawerSubItem) {
    setSelected(item);
    setAmount("");
    setTimeout(() => amountRef.current?.focus(), 0);
  }

  async function confirmBudget() {
    if (!selected) return;
    const val = parseFloat(amount);
    if (isNaN(val) || val < 0) return;
    setSaving(true);
    await onSetBudget(`${selected.catSlug}/${selected.sub.slug}`, val);
    setSaving(false);
    onClose();
  }

  async function confirmCreate() {
    if (!newLabel.trim()) return;
    setSaving(true);
    await onCreateCategory(newLabel.trim());
    setSaving(false);
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col justify-end"
      style={{ background: "rgba(0,0,0,0.5)" }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="rounded-t-2xl p-4 flex flex-col gap-3 max-h-[80vh] overflow-y-auto"
        style={{ background: "var(--app-bg)" }}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
            {showCreate ? "New category" : selected ? "Set budget" : "Set budget for a subcategory"}
          </p>
          <button
            className="text-xs px-2 py-1 rounded"
            style={{ color: "var(--app-text-secondary)" }}
            onClick={onClose}
          >
            Cancel
          </button>
        </div>

        {showCreate ? (
          <div className="flex flex-col gap-3">
            <input
              ref={labelRef}
              type="text"
              placeholder="Category name"
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              autoFocus
              className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
              style={{
                background: "var(--app-secondary-bg)",
                color: "var(--app-text-primary)",
                border: "1px solid var(--app-border, #333)",
              }}
            />
            <button
              disabled={!newLabel.trim() || saving}
              onClick={confirmCreate}
              className="w-full py-3 rounded-xl text-sm font-semibold"
              style={{
                background: newLabel.trim() ? "var(--app-accent)" : "var(--app-secondary-bg)",
                color: newLabel.trim() ? "#fff" : "var(--app-text-secondary)",
              }}
            >
              {saving ? "Creating…" : "Create category"}
            </button>
            <button
              onClick={() => setShowCreate(false)}
              className="text-xs text-center"
              style={{ color: "var(--app-text-secondary)" }}
            >
              Back
            </button>
          </div>
        ) : selected ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm" style={{ color: "var(--app-text-secondary)" }}>
              {getCategoryEmoji(selected.catSlug)} {selected.catLabel} / {selected.sub.label}
            </p>
            <input
              ref={amountRef}
              type="number"
              min={0}
              placeholder={`Amount in ${currency}`}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
              style={{
                background: "var(--app-secondary-bg)",
                color: "var(--app-text-primary)",
                border: "1px solid var(--app-accent)",
              }}
            />
            <button
              disabled={!amount || saving}
              onClick={confirmBudget}
              className="w-full py-3 rounded-xl text-sm font-semibold"
              style={{
                background: amount ? "var(--app-accent)" : "var(--app-secondary-bg)",
                color: amount ? "#fff" : "var(--app-text-secondary)",
              }}
            >
              {saving ? "Saving…" : "Set budget"}
            </button>
            <button
              onClick={() => setSelected(null)}
              className="text-xs text-center"
              style={{ color: "var(--app-text-secondary)" }}
            >
              Back
            </button>
          </div>
        ) : (
          <div className="flex flex-col">
            {unbudgetedSubs.map((item) => (
              <button
                key={`${item.catSlug}/${item.sub.slug}`}
                onClick={() => selectSub(item)}
                className="flex items-center gap-3 py-3 text-left border-b last:border-b-0"
                style={{ borderColor: "var(--app-secondary-bg)" }}
              >
                <span className="text-lg">{getCategoryEmoji(item.catSlug)}</span>
                <span className="text-sm" style={{ color: "var(--app-text-primary)" }}>
                  {item.catLabel} / {item.sub.label}
                </span>
              </button>
            ))}
            {unbudgetedSubs.length === 0 && (
              <p className="text-sm py-3 text-center" style={{ color: "var(--app-text-secondary)" }}>
                All subcategories have budgets set
              </p>
            )}
            <button
              onClick={() => { setShowCreate(true); setTimeout(() => labelRef.current?.focus(), 0); }}
              className="flex items-center gap-3 py-3 text-left"
            >
              <span className="text-lg">➕</span>
              <span className="text-sm font-medium" style={{ color: "var(--app-accent)" }}>
                Create new category
              </span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function BudgetPage() {
  const [budgets, setBudgets] = useState<BudgetEntry[]>([]);
  const [currency, setCurrency] = useState("USD");
  const [isLoading, setIsLoading] = useState(true);
  const [showDrawer, setShowDrawer] = useState(false);

  async function load() {
    try {
      const data = await fetchBudgets();
      setBudgets(data.budgets);
      setCurrency(data.base_currency);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleEdit(catSlug: string, subSlug: string, value: string) {
    const amount = parseFloat(value);
    if (isNaN(amount) || amount < 0) return;
    const data = await updateBudgets({ [`${catSlug}/${subSlug}`]: amount });
    setBudgets(data.budgets);
    setCurrency(data.base_currency);
  }

  async function handleSetBudget(key: string, amount: number) {
    const data = await updateBudgets({ [key]: amount });
    setBudgets(data.budgets);
    setCurrency(data.base_currency);
  }

  async function handleCreateCategory(label: string) {
    await createCategory(label);
    await load();
  }

  // Categories with at least one budgeted subcategory
  const activeCats = budgets.filter((b) => b.budget > 0);

  // All subcategories without a budget (for the drawer)
  const unbudgetedSubs = budgets.flatMap((cat) =>
    cat.subcategories
      .filter((s) => s.budget === 0)
      .map((s) => ({ catSlug: cat.category, catLabel: cat.label, sub: s }))
  );

  // Summary numbers (category-level aggregates for overall view)
  const totalBudget = activeCats.reduce((s, c) => s + c.budget, 0);
  const totalSpent = activeCats.reduce((s, c) => s + c.spent, 0);
  const totalRemaining = totalBudget - totalSpent;
  const overallPct = totalBudget > 0 ? (totalSpent / totalBudget) * 100 : 0;

  // Status chips count subcategories
  const activeSubs = budgets.flatMap((c) => c.subcategories).filter((s) => s.budget > 0);
  const onTrack = activeSubs.filter((s) => s.status === "normal").length;
  const warning = activeSubs.filter((s) => s.status === "warning").length;
  const exceeded = activeSubs.filter((s) => s.status === "exceeded").length;

  if (isLoading) {
    return (
      <div className="page-content py-4">
        <div className="card text-center py-8">
          <p className="text-sm" style={{ color: "var(--app-text-secondary)" }}>Loading…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-content py-4 flex flex-col gap-4">
      {/* Summary card */}
      {activeCats.length > 0 ? (
        <div className="card flex flex-col items-center gap-3">
          <p className="text-xs font-medium" style={{ color: "var(--app-text-secondary)" }}>
            Total budget {formatAmount(totalBudget, currency, 0)}
          </p>
          <SummaryRing pct={overallPct} />
          <div className="text-center">
            <p className="text-xl font-bold" style={{ color: "var(--app-text-primary)" }}>
              {formatAmount(totalRemaining, currency, 0)}
            </p>
            <p className="text-xs mt-0.5" style={{ color: "var(--app-text-secondary)" }}>
              remaining this month
            </p>
          </div>
          <div className="flex gap-2 mt-1">
            <div className="flex flex-col items-center px-3 py-1.5 rounded-xl" style={{ background: "var(--app-secondary-bg)" }}>
              <span className="text-base font-bold" style={{ color: "var(--app-accent)" }}>{onTrack}</span>
              <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>On track</span>
            </div>
            <div className="flex flex-col items-center px-3 py-1.5 rounded-xl" style={{ background: "var(--app-secondary-bg)" }}>
              <span className="text-base font-bold" style={{ color: "#fbbf24" }}>{warning}</span>
              <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>Warning</span>
            </div>
            <div className="flex flex-col items-center px-3 py-1.5 rounded-xl" style={{ background: "var(--app-secondary-bg)" }}>
              <span className="text-base font-bold" style={{ color: "var(--app-danger)" }}>{exceeded}</span>
              <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>Over limit</span>
            </div>
          </div>
        </div>
      ) : (
        <div className="card text-center py-6">
          <p className="text-2xl mb-2">💰</p>
          <p className="text-sm font-medium" style={{ color: "var(--app-text-primary)" }}>No budgets set yet</p>
          <p className="text-xs mt-1" style={{ color: "var(--app-text-secondary)" }}>
            Tap the button below to set a budget for a subcategory
          </p>
        </div>
      )}

      {/* By category */}
      {activeCats.length > 0 && (
        <div className="card">
          <p className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--app-text-secondary)" }}>
            By category
          </p>
          <div className="flex flex-col divide-y" style={{ borderColor: "var(--app-secondary-bg)" }}>
            {activeCats.map((entry) => (
              <CategorySection
                key={entry.category}
                entry={entry}
                currency={currency}
                onEdit={handleEdit}
              />
            ))}
          </div>
        </div>
      )}

      {/* CTA */}
      <button
        onClick={() => setShowDrawer(true)}
        className="w-full py-3.5 rounded-2xl text-sm font-semibold"
        style={{ background: "var(--app-secondary-bg)", color: "var(--app-text-primary)" }}
      >
        Set budget for a subcategory
      </button>

      {/* Drawer */}
      {showDrawer && (
        <BudgetDrawer
          unbudgetedSubs={unbudgetedSubs}
          currency={currency}
          onSetBudget={handleSetBudget}
          onCreateCategory={handleCreateCategory}
          onClose={() => setShowDrawer(false)}
        />
      )}
    </div>
  );
}
