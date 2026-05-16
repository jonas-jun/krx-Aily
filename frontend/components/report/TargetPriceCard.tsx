import type { TargetPrice } from "@/lib/api";
import { formatPrice } from "@/lib/utils";

interface Props {
  targetPrice: TargetPrice;
}

export function TargetPriceCard({ targetPrice }: Props) {
  const hasData = targetPrice.avg !== null;
  const { current_price } = targetPrice;

  const gap =
    hasData && current_price && current_price > 0
      ? ((targetPrice.avg! - current_price) / current_price) * 100
      : null;

  const gapLabel =
    gap !== null
      ? `${gap >= 0 ? "+" : ""}${gap.toFixed(1)}%`
      : null;

  const gapCls =
    gap === null
      ? ""
      : gap >= 0
        ? "text-[#EF4444] font-semibold"
        : "text-slate-500 font-semibold";

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">목표주가</h2>
      {hasData ? (
        <div className="flex flex-col gap-3">
          {/* 평균 목표주가 + 현재주가 */}
          <div className="flex items-end gap-6">
            <div>
              <p className="text-[11px] text-slate-400 mb-0.5">평균 목표주가</p>
              <p className="text-3xl font-extrabold text-[#EF4444]">
                {formatPrice(targetPrice.avg)}
              </p>
            </div>
            {current_price !== null && (
              <div>
                <p className="text-[11px] text-slate-400 mb-0.5">현재주가</p>
                <p className="text-3xl font-extrabold text-[#1E3A5F]">
                  {formatPrice(current_price)}
                </p>
              </div>
            )}
          </div>

          {/* 최저·최고 + 괴리율 */}
          <div className="flex items-center gap-4 text-sm text-slate-500">
            <span>
              최저 <span className="font-semibold text-slate-700">{formatPrice(targetPrice.min)}</span>
            </span>
            <span>
              최고 <span className="font-semibold text-slate-700">{formatPrice(targetPrice.max)}</span>
            </span>
            {gapLabel && (
              <span className={gapCls}>
                괴리율 {gapLabel}
              </span>
            )}
          </div>
        </div>
      ) : (
        <p className="text-sm text-slate-400">목표주가 없음</p>
      )}
    </div>
  );
}
