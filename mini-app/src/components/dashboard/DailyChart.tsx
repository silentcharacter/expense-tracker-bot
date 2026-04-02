import {
  BarChart,
  Bar,
  XAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { Period } from "../../api/summary";
import type { DailyTotal } from "../../api/types";
import { formatAmountCompact } from "../../utils/format";

interface DailyChartProps {
  data: DailyTotal[];
  currency: string;
  dateRange: { start: string; end: string };
  period: Period;
}

interface TooltipPayload {
  value: number;
  payload?: { isFuture?: boolean };
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string;
  currency: string;
}

function CustomTooltip({ active, payload, label, currency }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  const isFuture = payload[0].payload?.isFuture;
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
      <p className="amount font-medium">
        {isFuture ? "—" : formatAmountCompact(payload[0].value, currency)}
      </p>
    </div>
  );
}

function dateToStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function getTodayStr(): string {
  return dateToStr(new Date());
}

/** Returns the last day of the full period, regardless of what the API returned as end. */
function getPeriodDisplayEnd(period: Period, start: string): string {
  const startDate = new Date(start + "T12:00:00");
  if (period === "month") {
    // Last day of the month
    return dateToStr(new Date(startDate.getFullYear(), startDate.getMonth() + 1, 0));
  }
  if (period === "week") {
    // Mon–Sun: start is Monday, show through Sunday
    const sunday = new Date(startDate);
    sunday.setDate(sunday.getDate() + 6);
    return dateToStr(sunday);
  }
  // "today" or "year" — just use today as end
  return getTodayStr();
}

function generateAllDays(start: string, end: string): string[] {
  const dates: string[] = [];
  const current = new Date(start + "T12:00:00");
  const endDate = new Date(end + "T12:00:00");
  while (current <= endDate) {
    dates.push(
      `${current.getFullYear()}-${String(current.getMonth() + 1).padStart(2, "0")}-${String(current.getDate()).padStart(2, "0")}`
    );
    current.setDate(current.getDate() + 1);
  }
  return dates;
}

function formatDayLabel(dateStr: string, useWeekDay: boolean): string {
  const date = new Date(dateStr + "T12:00:00");
  if (useWeekDay) {
    return ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"][date.getDay()];
  }
  return String(date.getDate());
}

export function DailyChart({ data, currency, dateRange, period }: DailyChartProps) {
  const displayEnd = getPeriodDisplayEnd(period, dateRange.start);
  const allDays = generateAllDays(dateRange.start, displayEnd);
  if (!allDays.length) return null;

  const today = getTodayStr();
  const useWeekDay = allDays.length <= 7;
  const amountByDate = new Map(data.map((d) => [d.date, d.amount_base]));

  const chartData = allDays.map((date) => {
    const isFuture = date > today;
    const amount = amountByDate.get(date) ?? 0;
    return {
      label: formatDayLabel(date, useWeekDay),
      // Render a tiny placeholder height for future/zero days so bars are visible
      value: isFuture ? 0 : amount,
      date,
      isToday: date === today,
      isFuture,
    };
  });

  // XAxis interval: show ~6 ticks max for long periods
  const xInterval = allDays.length <= 7 ? 0 : Math.ceil(allDays.length / 6) - 1;

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
            tick={(props) => {
              const entry = chartData[props.index];
              const isToday = entry?.isToday;
              return (
                <text
                  x={props.x}
                  y={props.y + 12}
                  textAnchor="middle"
                  fontSize={isToday ? 12 : 11}
                  fontWeight={isToday ? 700 : 400}
                  fill={isToday ? "var(--app-accent)" : "var(--app-text-secondary)"}
                >
                  {props.value}
                </text>
              );
            }}
            interval={xInterval}
          />
          <Tooltip
            content={(props) => (
              <CustomTooltip
                active={props.active}
                payload={props.payload as TooltipPayload[] | undefined}
                label={props.label as string | undefined}
                currency={currency}
              />
            )}
            cursor={{ fill: "var(--app-secondary-bg)" }}
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} minPointSize={3}>
            {chartData.map((entry) => (
              <Cell
                key={entry.date}
                fill={
                  entry.isToday
                    ? "var(--app-accent)"
                    : entry.isFuture
                    ? "color-mix(in srgb, var(--app-accent) 15%, var(--app-secondary-bg))"
                    : entry.value > 0
                    ? "color-mix(in srgb, var(--app-accent) 45%, var(--app-secondary-bg))"
                    : "color-mix(in srgb, var(--app-accent) 15%, var(--app-secondary-bg))"
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
