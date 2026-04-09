import { useState, useEffect, useRef } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import type { BudgetEntry, SubcategoryBudgetEntry, RecurringResponse, AddRecurringRequest } from "../api/types";
import { fetchBudgets, updateBudgets } from "../api/budgets";
import { createCategory, createSubcategory, deleteCategory, deleteSubcategory } from "../api/categories";
import { fetchRecurring, addRecurring, deleteRecurring } from "../api/recurring";
import { getCategoryColor, getCategoryEmoji, getCategoryLabel } from "../utils/categories";
import { formatAmount, formatPercent } from "../utils/format";

// ── Budget donut chart ────────────────────────────────────────────────────────

interface BudgetDonutEntry {
  key: string;
  displayName: string;
  budget: number;
  percentage: number;
  color: string;
}

interface BudgetTooltipProps {
  active?: boolean;
  payload?: { payload: BudgetDonutEntry }[];
}

function BudgetTooltip({ active, payload }: BudgetTooltipProps) {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  return (
    <div
      className="px-3 py-2 rounded-lg text-sm shadow-lg"
      style={{
        backgroundColor: "var(--tg-theme-bg-color, #1a1a2e)",
        border: "1px solid var(--app-border)",
        color: "var(--app-text-primary)",
        zIndex: 50,
        position: "relative",
      }}
    >
      <p className="font-medium">{item.displayName}</p>
      <p className="amount" style={{ color: "var(--app-text-secondary)" }}>
        {formatAmount(item.budget, "USD", 0)} · {formatPercent(item.percentage)}
      </p>
    </div>
  );
}

function BudgetDonut({ entries, currency, total, onTrack, warning, exceeded }: { entries: BudgetEntry[]; currency: string; total: number; onTrack: number; warning: number; exceeded: number }) {
  const chartData: BudgetDonutEntry[] = entries
    .filter((e) => e.budget > 0)
    .sort((a, b) => b.budget - a.budget)
    .map((e) => ({
      key: e.category,
      displayName: getCategoryLabel(e.category),
      budget: e.budget,
      percentage: total > 0 ? (e.budget / total) * 100 : 0,
      color: getCategoryColor(e.category),
    }));

  if (!chartData.length) return null;

  return (
    <div className="card">
      <p className="text-[11px] font-semibold uppercase tracking-wider mb-3" style={{ color: "var(--app-text-secondary)" }}>
        By Category
      </p>
      <div className="flex items-center gap-3">
        <div className="relative flex-shrink-0" style={{ width: 130, height: 130 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartData}
                dataKey="budget"
                nameKey="key"
                innerRadius="55%"
                outerRadius="85%"
                paddingAngle={2}
                stroke="none"
              >
                {chartData.map((entry) => (
                  <Cell key={entry.key} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip content={<BudgetTooltip />} wrapperStyle={{ zIndex: 50 }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <span className="amount text-[13px] font-bold leading-tight" style={{ color: "var(--app-text-primary)" }}>
              {formatAmount(total, currency, 0)}
            </span>
            <span className="text-[9px] leading-tight" style={{ color: "var(--app-text-secondary)" }}>
              budget
            </span>
          </div>
        </div>
        <div className="flex flex-col gap-1.5 flex-1 min-w-0">
          {chartData.map((entry) => (
            <div key={entry.key} className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: entry.color }} />
              <span className="text-xs truncate flex-1" style={{ color: "var(--app-text-primary)" }}>
                {getCategoryEmoji(entry.key)} {entry.displayName}
              </span>
              <span className="amount text-xs font-medium flex-shrink-0" style={{ color: "var(--app-text-primary)" }}>
                {formatAmount(entry.budget, currency, 0)}
              </span>
              <span className="text-[11px] w-9 text-right flex-shrink-0" style={{ color: "var(--app-text-secondary)" }}>
                {formatPercent(entry.percentage)}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div className="flex gap-2 mt-3">
        <div className="flex flex-col items-center px-3 py-1.5 rounded-xl flex-1" style={{ background: "var(--app-secondary-bg)" }}>
          <span className="text-base font-bold" style={{ color: "var(--app-accent)" }}>{onTrack}</span>
          <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>On track</span>
        </div>
        <div className="flex flex-col items-center px-3 py-1.5 rounded-xl flex-1" style={{ background: "var(--app-secondary-bg)" }}>
          <span className="text-base font-bold" style={{ color: "#fbbf24" }}>{warning}</span>
          <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>Warning</span>
        </div>
        <div className="flex flex-col items-center px-3 py-1.5 rounded-xl flex-1" style={{ background: "var(--app-secondary-bg)" }}>
          <span className="text-base font-bold" style={{ color: "var(--app-danger)" }}>{exceeded}</span>
          <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>Over limit</span>
        </div>
      </div>
    </div>
  );
}

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
  onDelete: (catSlug: string, subSlug: string) => void;
}

function SubRow({ catSlug, entry, currency, onEdit, onDelete }: SubRowProps) {
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
    <div
      className="py-2 pl-5 cursor-pointer"
      onClick={() => !editing && !hasBudget && startEdit()}
    >
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
              <span className="text-xs" style={{ color: barColor }}>
                {Math.round(entry.percentage)}%
              </span>
              <span className="text-xs font-medium" style={{ color: barColor }}>
                {formatAmount(entry.spent, currency, 0)}
              </span>
              <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
                / {formatAmount(entry.budget, currency, 0)}
              </span>
              <button
                onClick={(e) => { e.stopPropagation(); startEdit(); }}
                className="ml-1 p-0.5 rounded opacity-50 hover:opacity-100"
                title="Edit budget"
                style={{ color: "var(--app-text-secondary)" }}
              >
                <svg width={12} height={12} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5}>
                  <path d="M11.5 2.5l2 2-9 9H2.5v-2l9-9z" />
                </svg>
              </button>
            </>
          ) : (
            <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
              tap to set
            </span>
          )}
          {!editing && (
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(catSlug, entry.slug); }}
              className="ml-1 p-0.5 rounded opacity-30 hover:opacity-100"
              title="Delete subcategory"
              style={{ color: "var(--app-danger)" }}
            >
              <svg width={12} height={12} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5}>
                <path d="M2 4h12M5 4V2h6v2M6 7v5M10 7v5M3 4l1 9h8l1-9" />
              </svg>
            </button>
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
  hideUnbudgeted: boolean;
  onEdit: (catSlug: string, subSlug: string, value: string) => void;
  onAddSubcategory: (catSlug: string, catLabel: string) => void;
  onDeleteCategory: (catSlug: string) => void;
  onDeleteSubcategory: (catSlug: string, subSlug: string) => void;
}

function CategorySection({ entry, currency, hideUnbudgeted, onEdit, onAddSubcategory, onDeleteCategory, onDeleteSubcategory }: CategorySectionProps) {
  const emoji = getCategoryEmoji(entry.category);
  const hasBudget = entry.budget > 0;
  const fillPct = Math.min(entry.percentage, 100);
  const barColor =
    entry.status === "exceeded" ? "var(--app-danger)" :
    entry.status === "warning" ? "#fbbf24" : "var(--app-accent)";

  const visibleSubs = hideUnbudgeted
    ? entry.subcategories.filter((s) => s.budget > 0)
    : entry.subcategories;

  return (
    <div className="mb-1">
      {/* Category header */}
      <div className="flex items-center justify-between py-2">
        <span className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
          {emoji} {entry.label}
        </span>
        <div className="flex items-center gap-2">
          {hasBudget && (
            <div className="flex items-center gap-1">
              <span className="text-xs" style={{ color: barColor }}>
                {Math.round(entry.percentage)}%
              </span>
              <span className="text-xs font-semibold" style={{ color: barColor }}>
                {formatAmount(entry.spent, currency, 0)}
              </span>
              <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
                / {formatAmount(entry.budget, currency, 0)}
              </span>
            </div>
          )}
          <button
            onClick={() => onAddSubcategory(entry.category, entry.label)}
            className="flex items-center justify-center w-5 h-5 rounded-full text-xs font-bold"
            style={{ background: "var(--app-secondary-bg)", color: "var(--app-accent)" }}
            title="Add subcategory"
          >
            +
          </button>
          <button
            onClick={() => onDeleteCategory(entry.category)}
            className="flex items-center justify-center w-5 h-5 rounded opacity-30 hover:opacity-100"
            title="Delete category"
            style={{ color: "var(--app-danger)" }}
          >
            <svg width={12} height={12} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5}>
              <path d="M2 4h12M5 4V2h6v2M6 7v5M10 7v5M3 4l1 9h8l1-9" />
            </svg>
          </button>
        </div>
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
        {visibleSubs.map((sub) => (
          <SubRow
            key={sub.slug}
            catSlug={entry.category}
            entry={sub}
            currency={currency}
            onEdit={onEdit}
            onDelete={onDeleteSubcategory}
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
  initialView?: "list" | "create";
  onSetBudget: (key: string, amount: number) => Promise<void>;
  onCreateCategory: (label: string) => Promise<void>;
  onClose: () => void;
}

function BudgetDrawer({ unbudgetedSubs, currency, initialView = "list", onSetBudget, onCreateCategory, onClose }: DrawerProps) {
  const [selected, setSelected] = useState<DrawerSubItem | null>(null);
  const [amount, setAmount] = useState("");
  const [showCreate, setShowCreate] = useState(initialView === "create");
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
      className="fixed inset-x-0 top-0 bottom-14 z-50 flex flex-col justify-end"
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
            {initialView !== "create" && (
              <button
                onClick={() => setShowCreate(false)}
                className="text-xs text-center"
                style={{ color: "var(--app-text-secondary)" }}
              >
                Back
              </button>
            )}
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

// ── Add subcategory mini-drawer ───────────────────────────────────────────────

interface AddSubDrawerProps {
  catSlug: string;
  catLabel: string;
  onConfirm: (catSlug: string, label: string) => Promise<void>;
  onClose: () => void;
}

function AddSubDrawer({ catSlug, catLabel, onConfirm, onClose }: AddSubDrawerProps) {
  const [label, setLabel] = useState("");
  const [saving, setSaving] = useState(false);

  async function confirm() {
    if (!label.trim()) return;
    setSaving(true);
    await onConfirm(catSlug, label.trim());
    setSaving(false);
    onClose();
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter") confirm();
    if (e.key === "Escape") onClose();
  }

  return (
    <div
      className="fixed inset-x-0 top-0 bottom-14 z-50 flex flex-col justify-end"
      style={{ background: "rgba(0,0,0,0.5)" }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="rounded-t-2xl p-4 flex flex-col gap-3"
        style={{ background: "var(--app-bg)" }}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
            Add subcategory to {getCategoryEmoji(catSlug)} {catLabel}
          </p>
          <button
            className="text-xs px-2 py-1 rounded"
            style={{ color: "var(--app-text-secondary)" }}
            onClick={onClose}
          >
            Cancel
          </button>
        </div>
        <input
          type="text"
          placeholder="Subcategory name"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onKeyDown={handleKey}
          autoFocus
          className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
          style={{
            background: "var(--app-secondary-bg)",
            color: "var(--app-text-primary)",
            border: "1px solid var(--app-border, #333)",
          }}
        />
        <button
          disabled={!label.trim() || saving}
          onClick={confirm}
          className="w-full py-3 rounded-xl text-sm font-semibold"
          style={{
            background: label.trim() ? "var(--app-accent)" : "var(--app-secondary-bg)",
            color: label.trim() ? "#fff" : "var(--app-text-secondary)",
          }}
        >
          {saving ? "Adding…" : "Add subcategory"}
        </button>
      </div>
    </div>
  );
}

// ── Add recurring drawer ──────────────────────────────────────────────────────

function ordinalSuffix(n: number): string {
  if (n >= 11 && n <= 13) return `${n}th`;
  switch (n % 10) {
    case 1: return `${n}st`;
    case 2: return `${n}nd`;
    case 3: return `${n}rd`;
    default: return `${n}th`;
  }
}

interface AddRecurringDrawerProps {
  defaultCurrency: string;
  categories: { slug: string; label: string; subcategories: { slug: string; label: string }[] }[];
  onConfirm: (entry: AddRecurringRequest) => Promise<void>;
  onClose: () => void;
}

function AddRecurringDrawer({ defaultCurrency, categories, onConfirm, onClose }: AddRecurringDrawerProps) {
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [dayOfMonth, setDayOfMonth] = useState("1");
  const [category, setCategory] = useState("");
  const [subcategory, setSubcategory] = useState("");
  const [saving, setSaving] = useState(false);

  const subcategories = categories.find((c) => c.slug === category)?.subcategories ?? [];

  function handleCategoryChange(slug: string) {
    setCategory(slug);
    setSubcategory("");
  }

  async function confirm() {
    const amt = parseFloat(amount);
    if (!description.trim() || isNaN(amt) || amt <= 0) return;
    setSaving(true);
    await onConfirm({
      description: description.trim(),
      amount: amt,
      amount_local: amt,
      local_currency: defaultCurrency,
      day_of_month: parseInt(dayOfMonth, 10) || 1,
      category,
      subcategory,
    });
    setSaving(false);
    onClose();
  }

  const valid = description.trim().length > 0 && parseFloat(amount) > 0;

  return (
    <div
      className="fixed inset-x-0 top-0 bottom-14 z-50 flex flex-col justify-end"
      style={{ background: "rgba(0,0,0,0.5)" }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="rounded-t-2xl p-4 flex flex-col gap-3"
        style={{ background: "var(--app-bg)" }}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
            Add recurring expense
          </p>
          <button
            className="text-xs px-2 py-1 rounded"
            style={{ color: "var(--app-text-secondary)" }}
            onClick={onClose}
          >
            Cancel
          </button>
        </div>

        <input
          type="text"
          placeholder="Description (e.g. Netflix)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          autoFocus
          className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
          style={{
            background: "var(--app-secondary-bg)",
            color: "var(--app-text-primary)",
            border: "1px solid var(--app-border, #333)",
          }}
        />

        <div className="flex gap-2">
          <div className="flex-1 flex items-center rounded-xl overflow-hidden" style={{ background: "var(--app-secondary-bg)", border: "1px solid var(--app-border, #333)" }}>
            <input
              type="number"
              min={0}
              placeholder="Amount"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="flex-1 px-3 py-2.5 text-sm outline-none bg-transparent"
              style={{ color: "var(--app-text-primary)" }}
            />
            <span className="pr-3 text-xs font-medium" style={{ color: "var(--app-text-secondary)" }}>
              {defaultCurrency}
            </span>
          </div>
          <div className="flex items-center gap-1 rounded-xl px-3" style={{ background: "var(--app-secondary-bg)", border: "1px solid var(--app-border, #333)" }}>
            <span className="text-xs" style={{ color: "var(--app-text-secondary)" }}>Day</span>
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
              border: "1px solid var(--app-border, #333)",
            }}
          >
            <option value="">Category (optional)</option>
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
              border: "1px solid var(--app-border, #333)",
            }}
          >
            <option value="">Subcategory (optional)</option>
            {subcategories.map((s) => (
              <option key={s.slug} value={s.slug}>{s.label}</option>
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
          }}
        >
          {saving ? "Adding…" : "Add recurring"}
        </button>
      </div>
    </div>
  );
}

// ── Recurring section ─────────────────────────────────────────────────────────

interface RecurringSectionProps {
  data: RecurringResponse;
  onDelete: (id: string) => Promise<void>;
  onAdd: () => void;
}

function RecurringSection({ data, onDelete, onAdd }: RecurringSectionProps) {
  const { items, default_currency } = data;
  const localTotal = items.reduce((s, i) => s + i.amount_local, 0);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--app-text-secondary)" }}>
          ↺ Recurring
        </p>
        <button
          onClick={onAdd}
          className="text-xs px-2 py-1 rounded-lg font-medium"
          style={{ background: "var(--app-secondary-bg)", color: "var(--app-accent)" }}
        >
          + Add
        </button>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-center py-4" style={{ color: "var(--app-text-secondary)" }}>
          No recurring expenses yet
        </p>
      ) : (
        <div className="flex flex-col divide-y" style={{ borderColor: "var(--app-secondary-bg)" }}>
          {items.map((item) => (
            <div key={item.id} className="flex items-center gap-3 py-3">
              <span className="text-2xl flex-shrink-0">
                {item.category ? getCategoryEmoji(item.category) : "🔄"}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: "var(--app-text-primary)" }}>
                  {item.description}
                </p>
                <p className="text-xs" style={{ color: "var(--app-text-secondary)" }}>
                  Monthly · {ordinalSuffix(item.day_of_month)}
                </p>
              </div>
              <span className="text-sm font-semibold flex-shrink-0 amount" style={{ color: "var(--app-text-primary)" }}>
                {formatAmount(item.amount_local, item.local_currency)}
              </span>
              <button
                onClick={() => onDelete(item.id)}
                className="p-1.5 rounded opacity-40 hover:opacity-100 flex-shrink-0"
                title="Delete"
                style={{ color: "var(--app-danger)" }}
              >
                <svg width={14} height={14} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5}>
                  <path d="M2 4h12M5 4V2h6v2M6 7v5M10 7v5M3 4l1 9h8l1-9" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      {items.length > 0 && (
        <div className="mt-3 pt-3" style={{ borderTop: "1px solid var(--app-secondary-bg)" }}>
          <p className="text-xs text-center" style={{ color: "var(--app-text-secondary)" }}>
            Total recurring:{" "}
            <span className="font-semibold amount" style={{ color: "var(--app-accent)" }}>
              {formatAmount(localTotal, default_currency)}/mo
            </span>
          </p>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function BudgetPage() {
  const [budgets, setBudgets] = useState<BudgetEntry[]>([]);
  const [currency, setCurrency] = useState("USD");
  const [isLoading, setIsLoading] = useState(true);
  const [showDrawer, setShowDrawer] = useState(false);
  const [drawerView, setDrawerView] = useState<"list" | "create">("list");
  const [hideUnbudgeted, setHideUnbudgeted] = useState<boolean>(
    () => localStorage.getItem("budget_hide_unset") === "true"
  );
  const [addSubForCat, setAddSubForCat] = useState<{ slug: string; label: string } | null>(null);
  const [recurringData, setRecurringData] = useState<RecurringResponse>({ base_currency: "USD", default_currency: "USD", items: [], total: 0 });
  const [showAddRecurring, setShowAddRecurring] = useState(false);
  const categoriesEndRef = useRef<HTMLDivElement>(null);

  async function load() {
    try {
      const budgetData = await fetchBudgets();
      setBudgets(budgetData.budgets);
      setCurrency(budgetData.base_currency);
    } finally {
      setIsLoading(false);
    }
    fetchRecurring().then(setRecurringData).catch((e) => console.warn("fetchRecurring failed:", e));
  }

  useEffect(() => { load(); }, []);

  async function handleEdit(catSlug: string, subSlug: string, value: string) {
    const amount = parseFloat(value);
    if (isNaN(amount) || amount < 0) return;
    await updateBudgets({ [`${catSlug}/${subSlug}`]: amount });
    await load();
  }

  async function handleSetBudget(key: string, amount: number) {
    await updateBudgets({ [key]: amount });
    await load();
  }

  async function handleCreateCategory(label: string) {
    await createCategory(label);
    await load();
    setTimeout(() => categoriesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }), 100);
  }

  async function handleCreateSubcategory(catSlug: string, label: string) {
    await createSubcategory(catSlug, label);
    await load();
  }

  async function handleDeleteCategory(catSlug: string) {
    await deleteCategory(catSlug);
    await load();
  }

  async function handleDeleteSubcategory(catSlug: string, subSlug: string) {
    await deleteSubcategory(catSlug, subSlug);
    await load();
  }

  function openAddCategory() {
    setDrawerView("create");
    setShowDrawer(true);
  }

  async function handleAddRecurring(entry: AddRecurringRequest) {
    const data = await addRecurring(entry);
    setRecurringData(data);
  }

  async function handleDeleteRecurring(id: string) {
    const data = await deleteRecurring(id);
    setRecurringData(data);
  }


  // Categories with at least one budgeted subcategory (for summary/donut)
  const activeCats = budgets.filter((b) => b.budget > 0);

  // All subcategories without a budget (for the drawer)
  const unbudgetedSubs = budgets.flatMap((cat) =>
    cat.subcategories
      .filter((s) => s.budget === 0)
      .map((s) => ({ catSlug: cat.category, catLabel: cat.label, sub: s }))
  );

  // Summary numbers
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
        <div className="card flex items-center gap-4">
          <SummaryRing pct={overallPct} />
          <div className="flex flex-col gap-1">
            <p className="text-xs font-medium" style={{ color: "var(--app-text-secondary)" }}>Total budget</p>
            <p className="text-lg font-bold" style={{ color: "var(--app-text-primary)" }}>
              {formatAmount(totalBudget, currency, 0)}
            </p>
            <p className="text-xs font-medium mt-2" style={{ color: "var(--app-text-secondary)" }}>Remaining this month</p>
            <p className="text-lg font-bold" style={{ color: "var(--app-text-primary)" }}>
              {formatAmount(totalRemaining, currency, 0)}
            </p>
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

      {/* Budget donut */}
      {activeCats.length > 0 && (
        <BudgetDonut entries={activeCats} currency={currency} total={totalBudget} onTrack={onTrack} warning={warning} exceeded={exceeded} />
      )}

      {/* By category */}
      {budgets.length > 0 && (
        <div className="card">
          {/* Toolbar */}
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--app-text-secondary)" }}>
              By category
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setHideUnbudgeted((v) => {
                  const next = !v;
                  localStorage.setItem("budget_hide_unset", String(next));
                  return next;
                })}
                className="text-xs px-2 py-1 rounded-lg"
                style={{
                  background: hideUnbudgeted ? "var(--app-accent)" : "var(--app-secondary-bg)",
                  color: hideUnbudgeted ? "#fff" : "var(--app-text-secondary)",
                }}
              >
                {hideUnbudgeted ? "Show all" : "Hide unset"}
              </button>
              <button
                onClick={openAddCategory}
                className="text-xs px-2 py-1 rounded-lg font-medium"
                style={{ background: "var(--app-secondary-bg)", color: "var(--app-accent)" }}
              >
                + Category
              </button>
            </div>
          </div>
          <div className="flex flex-col divide-y" style={{ borderColor: "var(--app-secondary-bg)" }}>
            {budgets.map((entry) => (
              <CategorySection
                key={entry.category}
                entry={entry}
                currency={currency}
                hideUnbudgeted={hideUnbudgeted}
                onEdit={handleEdit}
                onAddSubcategory={(slug, label) => setAddSubForCat({ slug, label })}
                onDeleteCategory={handleDeleteCategory}
                onDeleteSubcategory={handleDeleteSubcategory}
              />
            ))}
            <div ref={categoriesEndRef} />
          </div>
        </div>
      )}

      {/* Recurring section */}
      <RecurringSection
        data={recurringData}
        onDelete={handleDeleteRecurring}
        onAdd={() => setShowAddRecurring(true)}
      />

      {/* Drawer */}
      {showDrawer && (
        <BudgetDrawer
          unbudgetedSubs={unbudgetedSubs}
          currency={currency}
          initialView={drawerView}
          onSetBudget={handleSetBudget}
          onCreateCategory={handleCreateCategory}
          onClose={() => setShowDrawer(false)}
        />
      )}

      {/* Add subcategory drawer */}
      {addSubForCat && (
        <AddSubDrawer
          catSlug={addSubForCat.slug}
          catLabel={addSubForCat.label}
          onConfirm={handleCreateSubcategory}
          onClose={() => setAddSubForCat(null)}
        />
      )}

      {/* Add recurring drawer */}
      {showAddRecurring && (
        <AddRecurringDrawer
          defaultCurrency={recurringData.default_currency}
          categories={budgets.map((b) => ({ slug: b.category, label: b.label, subcategories: b.subcategories.map((s) => ({ slug: s.slug, label: s.label })) }))}
          onConfirm={handleAddRecurring}
          onClose={() => setShowAddRecurring(false)}
        />
      )}
    </div>
  );
}
