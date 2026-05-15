"use client";

import { StockSearch } from "@/components/ui/StockSearch";

export default function HomePage() {
  return (
    <div className="flex min-h-[70vh] flex-col items-center pt-16 md:pt-24 gap-10 px-4">
      <div className="text-center space-y-3">
        <div className="text-4xl sm:text-5xl mb-4">📈</div>
        <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">KRX-Aily</h1>
        <p className="text-slate-500 text-sm sm:text-base max-w-md mx-auto leading-relaxed">
          한국 상장 종목의 최신 애널리스트 리포트를<br />AI가 통합 분석해드립니다.
        </p>
      </div>

      <div className="w-full max-w-lg">
        <StockSearch />
      </div>
    </div>
  );
}
