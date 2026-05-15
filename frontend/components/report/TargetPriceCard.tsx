import type { TargetPrice } from "@/lib/api";
import { formatPrice } from "@/lib/utils";

interface Props {
  targetPrice: TargetPrice;
}

export function TargetPriceCard({ targetPrice }: Props) {
  const hasData = targetPrice.avg !== null;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">목표주가</h2>
      {hasData ? (
        <div className="flex flex-col gap-1">
          <div className="text-3xl font-extrabold text-red-600">
            {formatPrice(targetPrice.avg)}
          </div>
          <div className="flex gap-4 text-sm text-slate-500 mt-1">
            <span>최저 <span className="font-semibold text-slate-700">{formatPrice(targetPrice.min)}</span></span>
            <span>최고 <span className="font-semibold text-slate-700">{formatPrice(targetPrice.max)}</span></span>
          </div>
        </div>
      ) : (
        <p className="text-sm text-slate-400">목표주가 없음</p>
      )}
    </div>
  );
}
