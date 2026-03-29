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
  put<T>(path: string, body: unknown): Promise<T>;
  delete<T>(path: string): Promise<T>;
}

function createApiClient(): ApiClient {
  function getInitData(): string {
    return window.Telegram?.WebApp?.initData ?? "";
  }

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const base = (API_BASE || window.location.origin).replace(/\/$/, "");
    const url = `${base}/api${path}`;

    const response = await fetch(url, {
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
      const qs = params ? "?" + new URLSearchParams(params).toString() : "";
      return request<T>("GET", path + qs);
    },
    put<T>(path: string, body: unknown): Promise<T> {
      return request<T>("PUT", path, body);
    },
    delete<T>(path: string): Promise<T> {
      return request<T>("DELETE", path);
    },
  };
}

export const api = createApiClient();
