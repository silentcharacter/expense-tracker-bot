/** Category config — emojis and colors consistent with the bot. */

export interface CategoryConfig {
  emoji: string;
  color: string;
  label: string;
}

export const CATEGORY_CONFIG: Record<string, CategoryConfig> = {
  food:          { emoji: "🍕", color: "#34d399", label: "Food & Drinks" },
  transport:     { emoji: "🚗", color: "#22d3ee", label: "Transport" },
  housing:       { emoji: "🏠", color: "#a78bfa", label: "Housing" },
  health:        { emoji: "💊", color: "#f472b6", label: "Health" },
  entertainment: { emoji: "🎮", color: "#fbbf24", label: "Entertainment" },
  shopping:      { emoji: "🛍️", color: "#fb923c", label: "Shopping" },
  education:     { emoji: "📚", color: "#60a5fa", label: "Education" },
  services:      { emoji: "✂️", color: "#c084fc", label: "Services" },
  subscriptions: { emoji: "📱", color: "#f87171", label: "Subscriptions" },
  travel:        { emoji: "✈️", color: "#2dd4bf", label: "Travel" },
  other:         { emoji: "📦", color: "#94a3b8", label: "Other" },
};

export const CATEGORY_SLUGS = Object.keys(CATEGORY_CONFIG);

export function getCategoryEmoji(slug: string): string {
  return CATEGORY_CONFIG[slug]?.emoji ?? "📦";
}

export function getCategoryColor(slug: string): string {
  return CATEGORY_CONFIG[slug]?.color ?? "#94a3b8";
}

export function getCategoryLabel(slug: string): string {
  return CATEGORY_CONFIG[slug]?.label ?? slug;
}
