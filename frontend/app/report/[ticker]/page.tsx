"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, type AnalyzeResponse } from "@/lib/api";
import { ReportSkeleton } from "@/components/report/ReportSkeleton";
import { OpinionBadge } from "@/components/report/OpinionBadge";
import { TargetPriceCard } from "@/components/report/TargetPriceCard";
import { KeyPointsList } from "@/components/report/KeyPointsList";
import { RisksList } from "@/components/report/RisksList";
import { SourceList } from "@/components/report/SourceList";

function ReportContent() {
  const { ticker } = useParams<{ ticker: string }>();
  const searchParams = useSearchParams();
  const name = searchParams.get("name") ?? ticker;
  const n = Number(searchParams.get("n") ?? "5");

  const [data, setData] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.analyze(ticker, name, n);
        if (!cancelled) setData(res);
      } catch (err: unknown) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "알 수 없는 오류가 발생했습니다.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => { cancelled = true; };
  }, [ticker, name, n]);

  return (
    <div>
      <div className="mb-6">
        <Link href="/" className="text-sm text-slate-400 hover:text-slate-600 mb-3 inline-block">
          ← 뒤로
        </Link>
        <div className="flex items-center gap-2">
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900">{name}</h1>
          <span className="text-sm text-slate-400 font-mono">{ticker}</span>
        </div>
        {data && (
          <p className="text-xs text-slate-400 mt-1">
            리포트 {data.report_count}개 기반 · {new Date(data.analyzed_at).toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul" })} 분석
          </p>
        )}
      </div>

      {loading && <ReportSkeleton />}

      {!loading && error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      {!loading && !error && data && (
        <div className="space-y-4">
          <OpinionBadge opinions={data.opinions} />
          <TargetPriceCard targetPrice={data.target_price} />
          <KeyPointsList points={data.key_points} />
          <RisksList risks={data.risks} />
          <SourceList sources={data.sources} />
        </div>
      )}
    </div>
  );
}

export default function ReportPage() {
  return (
    <Suspense fallback={<ReportSkeleton />}>
      <ReportContent />
    </Suspense>
  );
}
