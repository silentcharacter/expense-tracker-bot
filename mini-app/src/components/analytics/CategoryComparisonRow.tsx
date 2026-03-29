import type { CategorySummary } from "../../api/types";
import { getCategoryColor, getCategoryLabel } from "../../utils/categories";
import { formatPercent } from "../../utils/format";

interface CategoryComparisonRowProps {
  category: CategorySummary;
}

export function CategoryComparisonRow({ category }: CategoryComparisonRowProps) {
  const color = getCategoryColor(category.category);
  const changePercent = category.change_percent ?? 0;
  const prev = category.previous_amount_base ?? 0;
  const curr = category.amount_base;
  const max = Math.max(curr, prev, 1);

  const badgeColor = changePercent <= 0 ? "#34d399" : "#fb923c";
  const badgeLabel =
    changePercent === 0
      ? "0%"
      : formatPercent(changePercent, true);

  return (
    <div className="flex items-center gap-3 py-2.5" style={{ borderBottom: "1px solid var(--app-border)" }}>
      {/* Color dot + label */}
      <div className="flex items-center gap-2 w-28 shrink-0">
        <span
          className="w-2.5 h-2.5 rounded-full shrink-0"
          style={{ backgroundColor: color }}
        />
        <span className="text-xs truncate" style={{ color: "var(--app-text-primary)" }}>
          {getCategoryLabel(category.category)}
        </span>
      </div>

      {/* Mini comparison bars */}
      <div className="flex-1 flex flex-col gap-1">
        {/* Current period bar */}
        <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: "var(--app-secondary-bg)" }}>
          <div
            className="h-full rounded-full"
            style={{ width: `${(curr / max) * 100}%`, backgroundColor: color }}
          />
        </div>
        {/* Previous period bar */}
        <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: "var(--app-secondary-bg)" }}>
          <div
            className="h-full rounded-full opacity-40"
            style={{ width: `${(prev / max) * 100}%`, backgroundColor: color }}
          />
        </div>
      </div>

      {/* % change badge */}
      <span
        className="text-xs font-semibold shrink-0 w-12 text-right"
        style={{ color: badgeColor }}
      >
        {badgeLabel}
      </span>
    </div>
  );
}
