/** Fetch wrapper with Telegram initData authentication. */

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

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
    const response = await fetch(buildUrl(path), {
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
    delete<T>(path: string): Promise<T> {
      return request<T>("DELETE", path);
    },
    async getBlob(path: string, params?: Record<string, string>): Promise<{ blob: Blob; filename: string }> {
      const response = await fetch(buildUrl(path, params), {
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
