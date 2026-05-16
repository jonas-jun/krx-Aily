interface Props {
  points: string[];
}

export function KeyPointsList({ points }: Props) {
  if (points.length === 0) return null;

  return (
    <div className="rounded-xl border border-red-100 bg-red-50 p-4">
      <h2 className="text-xs font-semibold text-[#EF4444] uppercase tracking-wide mb-3">핵심 포인트</h2>
      <ol className="space-y-2">
        {points.map((point, i) => (
          <li key={i} className="flex gap-3 text-sm text-slate-700">
            <span className="flex-shrink-0 flex items-center justify-center w-5 h-5 rounded-full bg-[#EF4444] text-white text-xs font-bold mt-0.5">
              {i + 1}
            </span>
            <span className="leading-relaxed">{point}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
