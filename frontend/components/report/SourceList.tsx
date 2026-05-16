import type { SourceItem } from "@/lib/api";

interface Props {
  sources: SourceItem[];
}

export function SourceList({ sources }: Props) {
  if (sources.length === 0) return null;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">분석 근거 리포트</h2>
      <ul className="divide-y divide-slate-100">
        {sources.map((s, i) => (
          <li key={i} className="flex items-center justify-between py-2.5 gap-3">
            <div className="flex flex-col gap-0.5 min-w-0">
              <span className="text-xs font-semibold text-[#EF4444]">{s.firm}</span>
              <span className="text-sm text-slate-700 truncate">{s.title}</span>
              <span className="text-xs text-slate-400">{s.date}</span>
            </div>
            {s.pdf_url && (
              <a
                href={s.pdf_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-shrink-0 text-xs text-[#EF4444] hover:text-red-700 font-medium"
              >
                PDF ↗
              </a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
