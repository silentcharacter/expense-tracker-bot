import { formatAmount } from "../../utils/format";

interface DailyAverageCardProps {
  average: number;
  currency: string;
}

export function DailyAverageCard({ average, currency }: DailyAverageCardProps) {
  return (
    <div className="card">
      <p className="text-xs mb-1" style={{ color: "var(--app-text-secondary)" }}>
        Daily average
      </p>
      <p className="amount text-xl font-semibold" style={{ color: "var(--app-text-primary)" }}>
        {formatAmount(average, currency)}
      </p>
    </div>
  );
}
