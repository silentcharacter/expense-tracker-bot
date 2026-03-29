import {
  BarChart,
  Bar,
  XAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { DailyTotal } from "../../api/types";
import { formatAmountCompact } from "../../utils/format";

interface DailyChartProps {
  data: DailyTotal[];
  currency: string;
}

interface TooltipPayload {
  value: number;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="px-3 py-2 rounded-lg text-sm"
      style={{
        backgroundColor: "var(--app-card-bg)",
        border: "1px solid var(--app-border)",
        color: "var(--app-text-primary)",
      }}
    >
      <p style={{ color: "var(--app-text-secondary)" }}>{label}</p>
      <p className="amount font-medium">{formatAmountCompact(payload[0].value, "USD")}</p>
    </div>
  );
}

function formatDayLabel(dateStr: string): string {
  const date = new Date(dateStr + "T12:00:00");
  const day = date.getDay();
  return ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"][day];
}

export function DailyChart({ data, currency: _currency }: DailyChartProps) {
  if (!data.length) return null;

  // Use week day labels if 7 or fewer days, otherwise day-of-month
  const useWeekDay = data.length <= 7;

  const chartData = data.map((d) => ({
    label: useWeekDay ? formatDayLabel(d.date) : new Date(d.date + "T12:00:00").getDate().toString(),
    value: d.amount_base,
    date: d.date,
  }));

  const maxValue = Math.max(...chartData.map((d) => d.value));

  return (
    <div className="card">
      <p className="text-sm font-semibold mb-3" style={{ color: "var(--app-text-primary)" }}>
        Daily Spending
      </p>
      <ResponsiveContainer width="100%" height={150}>
        <BarChart data={chartData} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <XAxis
            dataKey="label"
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 11, fill: "var(--app-text-secondary)" }}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "var(--app-secondary-bg)" }} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            {chartData.map((entry) => (
              <Cell
                key={entry.date}
                fill={
                  entry.value === maxValue
                    ? "var(--app-accent)"
                    : "color-mix(in srgb, var(--app-accent) 40%, var(--app-secondary-bg))"
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
