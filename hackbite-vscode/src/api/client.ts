import { getHackbiteConfig } from "../config";

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  timeoutMs?: number;
}

export class HackbiteApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "HackbiteApiError";
    this.status = status;
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const cfg = getHackbiteConfig();
  const method = options.method ?? "GET";
  const timeoutMs = options.timeoutMs ?? 30000;
  const url = new URL(`${cfg.backendUrl}${path}`);

  Object.entries(options.query ?? {}).forEach(([k, v]) => {
    if (v !== undefined) {
      url.searchParams.set(k, String(v));
    }
  });

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (cfg.apiKey) {
      headers["X-API-Key"] = cfg.apiKey;
    }

    const res = await fetch(url.toString(), {
      method,
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });

    const text = await res.text();
    const data = text ? (JSON.parse(text) as unknown) : undefined;

    if (!res.ok) {
      const detail = typeof data === "object" && data && "detail" in data ? String((data as { detail?: unknown }).detail) : text;
      throw new HackbiteApiError(detail || `Request failed: ${res.status}`, res.status);
    }

    return data as T;
  } catch (err) {
    if (err instanceof HackbiteApiError) {
      throw err;
    }
    if (err instanceof Error && err.name === "AbortError") {
      throw new HackbiteApiError(`Request timeout after ${timeoutMs}ms`);
    }
    throw new HackbiteApiError(err instanceof Error ? err.message : "Unknown API error");
  } finally {
    clearTimeout(timer);
  }
}
