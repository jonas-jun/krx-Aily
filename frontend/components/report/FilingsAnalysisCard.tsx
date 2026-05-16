import type { AnalyzeResponse } from "@/lib/api";

interface Props {
  analysis: NonNullable<AnalyzeResponse["corporate_filings_analysis"]>;
}

export function FilingsAnalysisCard({ analysis }: Props) {
  const { revenue_structure_change, profit_trend, key_changes } = analysis;
  if (!revenue_structure_change && !profit_trend && !key_changes?.length) return null;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-4">
      <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">공시 · 리포트 교차 분석</h2>

      {key_changes && key_changes.length > 0 && (
        <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 space-y-2">
          <p className="text-xs font-semibold text-amber-700 uppercase tracking-wide">주요 변화 포인트</p>
          <ul className="space-y-1.5">
            {key_changes.map((item, i) => (
              <li key={i} className="flex gap-2 text-sm text-amber-900 leading-snug">
                <span className="mt-0.5 flex-shrink-0 w-1.5 h-1.5 rounded-full bg-amber-400 mt-1.5" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="space-y-3">
        {revenue_structure_change && (
          <div>
            <p className="text-xs font-semibold text-slate-400 mb-1">매출 구조 변화</p>
            <p className="text-sm text-slate-600 leading-relaxed">{revenue_structure_change}</p>
          </div>
        )}
        {profit_trend && (
          <div>
            <p className="text-xs font-semibold text-slate-400 mb-1">이익 흐름</p>
            <p className="text-sm text-slate-600 leading-relaxed">{profit_trend}</p>
          </div>
        )}
      </div>
    </div>
  );
}
