/** TTL cache backed by sessionStorage.
 *
 * Keys are prefixed with a version tag so we can invalidate every cached
 * bundle at once by bumping the prefix when the shape changes. All access
 * is wrapped in try/catch because Telegram's WebView can refuse storage.
 */

const TTL_MS = 10 * 60 * 1000;
const PREFIX = "expbot:cache:v1:";

interface Entry<T> {
  data: T;
  ts: number;
}

export function getCached<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(PREFIX + key);
    if (!raw) return null;
    const entry = JSON.parse(raw) as Entry<T>;
    if (Date.now() - entry.ts > TTL_MS) {
      sessionStorage.removeItem(PREFIX + key);
      return null;
    }
    return entry.data;
  } catch {
    return null;
  }
}

export function setCached<T>(key: string, data: T): void {
  try {
    const entry: Entry<T> = { data, ts: Date.now() };
    sessionStorage.setItem(PREFIX + key, JSON.stringify(entry));
  } catch {
    /* quota exceeded or storage disabled — silent no-op */
  }
}

export function clearCache(): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i);
      if (k && k.startsWith(PREFIX)) keys.push(k);
    }
    keys.forEach((k) => sessionStorage.removeItem(k));
  } catch {
    /* ignore */
  }
}
