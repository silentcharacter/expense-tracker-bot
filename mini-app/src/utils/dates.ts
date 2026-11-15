/**
 * Timezone-aware date helpers built on Intl.DateTimeFormat#formatToParts, so
 * results never depend on the device clock zone or locale Date getters.
 * "ymd" always means a "YYYY-MM-DD" calendar date string. Months are 1-based
 * everywhere in this module unless a name says otherwise.
 */

export interface TzParts {
  year: number;
  /** 1-based month (1 = January). */
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
}

const FALLBACK_TZ = "UTC";
const fmtCache = new Map<string, Intl.DateTimeFormat>();

/** True when `tz` is a valid IANA zone for this runtime. */
export function isValidTimeZone(tz: string): boolean {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

/** The device's IANA zone (used only when user settings fail to load). */
export function deviceTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || FALLBACK_TZ;
  } catch {
    return FALLBACK_TZ;
  }
}

function partsFormatter(tz: string): Intl.DateTimeFormat {
  let f = fmtCache.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", {
      timeZone: isValidTimeZone(tz) ? tz : FALLBACK_TZ,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    fmtCache.set(tz, f);
  }
  return f;
}

/** Calendar/clock parts of an instant (Date or ISO string) in `tz`. */
export function partsInTz(date: Date | string, tz: string): TzParts {
  const d = typeof date === "string" ? new Date(date) : date;
  const out: TzParts = { year: 0, month: 0, day: 0, hour: 0, minute: 0, second: 0 };
  for (const p of partsFormatter(tz).formatToParts(d)) {
    if (p.type in out) out[p.type as keyof TzParts] = Number(p.value);
  }
  return out;
}

function pad(n: number, w = 2): string {
  return String(n).padStart(w, "0");
}

/** Build "YYYY-MM-DD" from a 1-based month. */
export function makeYmd(year: number, month: number, day: number): string {
  return `${pad(year, 4)}-${pad(month)}-${pad(day)}`;
}

/** Parse "YYYY-MM-DD" (or an ISO string starting with it) into numbers. */
export function parseYmd(ymd: string): { year: number; month: number; day: number } {
  const [y, m, d] = ymd.slice(0, 10).split("-").map(Number);
  return { year: y, month: m, day: d };
}

/** "YYYY-MM-DD" of `date` in `tz`. Strings are parsed as instants. */
export function toLocalDateStr(date: Date | string, tz: string): string {
  const p = partsInTz(date, tz);
  return makeYmd(p.year, p.month, p.day);
}

/** Today's "YYYY-MM-DD" in `tz`. */
export function todayInTz(tz: string, now: Date = new Date()): string {
  return toLocalDateStr(now, tz);
}

/** Shift a calendar date by `days` (pure calendar math, DST-free). */
export function addDays(ymd: string, days: number): string {
  const { year, month, day } = parseYmd(ymd);
  const d = new Date(Date.UTC(year, month - 1, day + days));
  return makeYmd(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate());
}

/** Day before `todayYmd` (defaults to today in `tz`). */
export function yesterdayInTz(tz: string, todayYmd?: string): string {
  return addDays(todayYmd ?? todayInTz(tz), -1);
}

/** First day of the month of `ymd`: "YYYY-MM-01". */
export function monthStart(ymd: string): string {
  return `${ymd.slice(0, 7)}-01`;
}

/** Shift the month of `ymd` by `delta`, returning the "YYYY-MM-01" of the result. */
export function addMonths(ymd: string, delta: number): string {
  const { year, month } = parseYmd(ymd);
  const idx = year * 12 + (month - 1) + delta;
  return makeYmd(Math.floor(idx / 12), (idx % 12) + 1, 1);
}

/** Number of days in the given 1-based month. */
export function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

/** Last day of the month of `ymd`. */
export function monthEnd(ymd: string): string {
  const { year, month } = parseYmd(ymd);
  return makeYmd(year, month, daysInMonth(year, month));
}

/** Weekday of a calendar date, 0 = Sunday. */
export function weekdayOf(ymd: string): number {
  const { year, month, day } = parseYmd(ymd);
  return new Date(Date.UTC(year, month - 1, day)).getUTCDay();
}

/** True when both instants fall on the same calendar day in `tz`. */
export function isSameDay(a: Date | string, b: Date | string, tz: string): boolean {
  return toLocalDateStr(a, tz) === toLocalDateStr(b, tz);
}

/**
 * Format a calendar date ("YYYY-MM-DD") without any zone shift: the date is
 * built at UTC noon and rendered in UTC, so the label always matches the string.
 */
export function formatYmd(ymd: string, options: Intl.DateTimeFormatOptions): string {
  const { year, month, day } = parseYmd(ymd);
  return new Date(Date.UTC(year, month - 1, day, 12)).toLocaleDateString(undefined, {
    ...options,
    timeZone: "UTC",
  });
}
