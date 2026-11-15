/** Timezone choices for the settings picker: common zones first, then all IANA zones. */

export interface TimezoneOption {
  /** IANA name, e.g. "Europe/Kyiv". */
  id: string;
  /** Friendly label, e.g. "Kyiv (Europe/Kyiv)". */
  label: string;
}

const COMMON: Array<[string, string]> = [
  ["Asia/Bangkok", "Bangkok"],
  ["Asia/Singapore", "Singapore"],
  ["Asia/Tokyo", "Tokyo"],
  ["Asia/Jakarta", "Jakarta"],
  ["Australia/Sydney", "Sydney"],
  ["Europe/Kyiv", "Kyiv"],
  ["Europe/Berlin", "Berlin"],
  ["Europe/London", "London"],
  ["Europe/Paris", "Paris"],
  ["Europe/Moscow", "Moscow"],
  ["America/New_York", "New York"],
  ["America/Chicago", "Chicago"],
  ["America/Denver", "Denver"],
  ["America/Los_Angeles", "Los Angeles"],
  ["America/Sao_Paulo", "São Paulo"],
  ["Pacific/Auckland", "Auckland"],
];

function allSupportedZones(): string[] {
  try {
    const fn = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] })
      .supportedValuesOf;
    return typeof fn === "function" ? fn("timeZone") : [];
  } catch {
    return [];
  }
}

let cachedOptions: TimezoneOption[] | null = null;

/** Common zones first, then the remaining supported zones (no duplicates). */
export function timezoneOptions(): TimezoneOption[] {
  if (cachedOptions) return cachedOptions;
  const seen = new Set<string>();
  const out: TimezoneOption[] = [];
  for (const [id, city] of COMMON) {
    seen.add(id);
    out.push({ id, label: `${city} (${id})` });
  }
  for (const id of allSupportedZones()) {
    if (seen.has(id)) continue;
    seen.add(id);
    out.push({ id, label: id.replace(/_/g, " ") });
  }
  cachedOptions = out;
  return out;
}

/** Label for any IANA name, including ones outside the list. */
export function timezoneLabel(id: string): string {
  return timezoneOptions().find((o) => o.id === id)?.label ?? id;
}
