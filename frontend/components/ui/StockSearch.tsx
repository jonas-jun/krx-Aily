"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type TickerItem } from "@/lib/api";

export function StockSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TickerItem[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.trim().length < 1) {
      setResults([]);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const items = await api.search(query.trim());
        setResults(items);
        setOpen(items.length > 0);
      } catch {
        setResults([]);
        setOpen(false);
      } finally {
        setLoading(false);
      }
    }, 300);
  }, [query]);

  const handleSelect = (item: TickerItem) => {
    setQuery("");
    setOpen(false);
    router.push(`/report/${item.ticker}?name=${encodeURIComponent(item.name)}`);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (results.length > 0) handleSelect(results[0]);
  };

  return (
    <div ref={containerRef} className="relative w-full">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="종목명 검색 (예: SK하이닉스, NAVER)"
            className="w-full rounded-lg border border-slate-300 bg-white px-4 py-3 sm:py-2.5 text-base sm:text-sm shadow-sm focus:border-red-400 focus:outline-none focus:ring-1 focus:ring-red-400"
          />
          {loading && (
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 text-xs">
              검색 중…
            </span>
          )}
        </div>
        <button
          type="submit"
          className="rounded-lg bg-red-600 px-4 py-3 sm:py-2.5 text-base sm:text-sm font-medium text-white hover:bg-red-700 active:bg-red-800 transition-colors"
        >
          검색
        </button>
      </form>

      {open && (
        <ul className="absolute z-10 mt-1 w-full rounded-lg border border-slate-200 bg-white shadow-lg">
          {results.map((item) => (
            <li key={item.ticker}>
              <button
                type="button"
                onClick={() => handleSelect(item)}
                className="flex w-full items-center gap-3 px-4 py-3 sm:py-2.5 text-left text-sm hover:bg-slate-50 active:bg-slate-100 transition-colors"
              >
                <span className="font-semibold text-slate-900">{item.name}</span>
                <span className="text-slate-400 font-mono text-xs">{item.ticker}</span>
                {item.market && (
                  <span className="ml-auto text-xs text-slate-400 shrink-0">{item.market}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
