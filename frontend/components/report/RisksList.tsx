interface Props {
  risks: string[];
}

export function RisksList({ risks }: Props) {
  if (risks.length === 0) return null;

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">리스크</h2>
      <ul className="space-y-2">
        {risks.map((risk, i) => (
          <li key={i} className="flex gap-2 text-sm text-slate-700">
            <span className="flex-shrink-0 text-slate-400 mt-0.5">▼</span>
            <span className="leading-relaxed">{risk}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
