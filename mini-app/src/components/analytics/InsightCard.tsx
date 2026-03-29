interface InsightCardProps {
  emoji: string;
  title: string;
  subtitle: string;
  badge: string;
  badgePositive?: boolean; // true = green, false = red/orange, undefined = neutral
}

export function InsightCard({ emoji, title, subtitle, badge, badgePositive }: InsightCardProps) {
  const badgeColor =
    badgePositive === true
      ? "#34d399"
      : badgePositive === false
        ? "#fb923c"
        : "var(--app-accent)";

  return (
    <div
      className="flex items-start gap-3 py-3"
      style={{ borderBottom: "1px solid var(--app-border)" }}
    >
      <span className="text-2xl leading-none mt-0.5">{emoji}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold" style={{ color: "var(--app-text-primary)" }}>
          {title}
        </p>
        <p className="text-xs mt-0.5" style={{ color: "var(--app-text-secondary)" }}>
          {subtitle}
        </p>
      </div>
      <span
        className="text-xs font-semibold shrink-0 px-2 py-1 rounded-full"
        style={{ backgroundColor: `${badgeColor}22`, color: badgeColor }}
      >
        {badge}
      </span>
    </div>
  );
}
