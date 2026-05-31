/** Fetch wrapper with Telegram initData authentication. */

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

const MAX_RETRIES = 4;
const RETRY_BASE_MS = 400;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Retry transient Cloud Function 503s during cold scale-out. */
async function fetchWithRetry(url: string, init: RequestInit): Promise<Response> {
  let lastResponse: Response | undefined;
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    try {
      const response = await fetch(url, init);
      lastResponse = response;
      if (response.status !== 503 || attempt === MAX_RETRIES - 1) {
        return response;
      }
    } catch (err) {
      if (attempt === MAX_RETRIES - 1) {
        throw err;
      }
    }
    await sleep(RETRY_BASE_MS * (attempt + 1));
  }
  return lastResponse!;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface ApiClient {
  get<T>(path: string, params?: Record<string, string>): Promise<T>;
  post<T>(path: string, body: unknown): Promise<T>;
  put<T>(path: string, body: unknown): Promise<T>;
  patch<T>(path: string, body: unknown): Promise<T>;
  delete<T>(path: string): Promise<T>;
  getBlob(path: string, params?: Record<string, string>): Promise<{ blob: Blob; filename: string }>;
}

function createApiClient(): ApiClient {
  function getInitData(): string {
    return window.Telegram?.WebApp?.initData ?? "";
  }

  function buildUrl(path: string, params?: Record<string, string>): string {
    const base = (API_BASE || window.location.origin).replace(/\/$/, "");
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return `${base}/api${path}${qs}`;
  }

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const response = await fetchWithRetry(buildUrl(path), {
      method,
      headers: {
        "Content-Type": "application/json",
        Authorization: `tma ${getInitData()}`,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({})) as { message?: string };
      throw new ApiError(response.status, error.message ?? "Request failed");
    }

    return response.json() as Promise<T>;
  }

  return {
    get<T>(path: string, params?: Record<string, string>): Promise<T> {
      return request<T>("GET", path + (params ? "?" + new URLSearchParams(params).toString() : ""));
    },
    post<T>(path: string, body: unknown): Promise<T> {
      return request<T>("POST", path, body);
    },
    put<T>(path: string, body: unknown): Promise<T> {
      return request<T>("PUT", path, body);
    },
    patch<T>(path: string, body: unknown): Promise<T> {
      return request<T>("PATCH", path, body);
    },
    delete<T>(path: string): Promise<T> {
      return request<T>("DELETE", path);
    },
    async getBlob(path: string, params?: Record<string, string>): Promise<{ blob: Blob; filename: string }> {
      const response = await fetchWithRetry(buildUrl(path, params), {
        method: "GET",
        headers: { Authorization: `tma ${getInitData()}` },
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({})) as { message?: string };
        throw new ApiError(response.status, error.message ?? "Request failed");
      }
      const disposition = response.headers.get("Content-Disposition") ?? "";
      const match = disposition.match(/filename="([^"]+)"/);
      const filename = match ? match[1] : "export.csv";
      const blob = await response.blob();
      return { blob, filename };
    },
  };
}

export const api = createApiClient();
