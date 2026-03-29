import type { CategorySummary } from "../../api/types";
import { getCategoryLabel } from "../../utils/categories";
import { useTelegram } from "../../hooks/useTelegram";

interface CategoryFilterProps {
  categories: CategorySummary[];
  selected: string | null;
  onChange: (category: string | null) => void;
}

export function CategoryFilter({ categories, selected, onChange }: CategoryFilterProps) {
  const { hapticFeedback } = useTelegram();

  const top = categories
    .slice()
    .sort((a, b) => b.amount_base - a.amount_base)
    .slice(0, 5);

  function handleSelect(slug: string | null) {
    if (slug === selected) return;
    hapticFeedback?.impactOccurred("light");
    onChange(slug);
  }

  return (
    <div className="flex gap-2 overflow-x-auto pb-2 mb-3 no-scrollbar">
      <Chip label="All" active={selected === null} onClick={() => handleSelect(null)} />
      {top.map((cat) => (
        <Chip
          key={cat.category}
          label={getCategoryLabel(cat.category)}
          active={selected === cat.category}
          onClick={() => handleSelect(cat.category)}
        />
      ))}
    </div>
  );
}

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex-shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition-colors whitespace-nowrap"
      style={
        active
          ? { backgroundColor: "var(--app-accent)", color: "var(--tg-theme-button-text-color, #fff)" }
          : { backgroundColor: "var(--app-card-bg)", color: "var(--app-text-secondary)", border: "1px solid var(--app-border)" }
      }
    >
      {label}
    </button>
  );
}
