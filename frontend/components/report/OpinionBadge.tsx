import type { Opinions } from "@/lib/api";

interface Props {
  opinions: Opinions;
}

export function OpinionBadge({ opinions }: Props) {
  const total = opinions.buy + opinions.neutral + opinions.sell;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">증권사 의견</h2>
      <div className="flex items-center gap-6">
        <OpinionItem label="매수" count={opinions.buy} total={total} color="emerald" />
        <OpinionItem label="중립" count={opinions.neutral} total={total} color="slate" />
        <OpinionItem label="매도" count={opinions.sell} total={total} color="red" />
      </div>
    </div>
  );
}

function OpinionItem({
  label,
  count,
  total,
  color,
}: {
  label: string;
  count: number;
  total: number;
  color: "emerald" | "slate" | "red";
}) {
  const colorMap = {
    emerald: { dot: "text-[#EF4444]", label: "text-[#EF4444]", bg: "bg-red-50" },
    slate: { dot: "text-slate-400", label: "text-slate-600", bg: "bg-slate-50" },
    red: { dot: "text-slate-400", label: "text-slate-500", bg: "bg-slate-50" },
  };
  const c = colorMap[color];
  const dots = total > 0 ? Math.round((count / total) * 5) : 0;

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="flex gap-0.5">
        {Array.from({ length: 5 }).map((_, i) => (
          <span key={i} className={`text-base ${i < dots ? c.dot : "text-slate-200"}`}>●</span>
        ))}
      </div>
      <span className={`text-xs font-medium ${c.label}`}>{label}</span>
      <span className="text-lg font-bold text-slate-800">{count}</span>
    </div>
  );
}
