const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export interface TickerItem {
  ticker: string;
  name: string;
  market: string;
}

export interface TargetPrice {
  avg: number | null;
  min: number | null;
  max: number | null;
  current_price: number | null;
}

export interface SourceItem {
  firm: string;
  title: string;
  date: string;
  pdf_url: string;
  target_price: number | null;
}

export interface AnalyzeResponse {
  ticker: string;
  name: string;
  report_count: number;
  analyzed_at: string;
  target_price: TargetPrice;
  sources: SourceItem[];
  model_version: string;
  full_report: string | null;
  dart_only: boolean;
}

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    let code = "UNKNOWN_ERROR";
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      code = body?.detail?.code ?? body?.error?.code ?? code;
      message = body?.detail?.message ?? body?.error?.message ?? message;
    } catch {}
    throw new ApiError(code, message, res.status);
  }

  return res.json() as Promise<T>;
}

export const api = {
  search: (q: string, limit = 10): Promise<TickerItem[]> =>
    apiFetch(`/search?q=${encodeURIComponent(q)}&limit=${limit}`),

  analyze: (ticker: string, name: string, n = 5): Promise<AnalyzeResponse> =>
    apiFetch("/analyze", {
      method: "POST",
      body: JSON.stringify({ ticker, name, n }),
    }),
};
