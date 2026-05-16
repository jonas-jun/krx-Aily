"use client";

import { StockSearch } from "@/components/ui/StockSearch";
import { Logo } from "@/components/ui/Logo";

export default function HomePage() {
  return (
    <div className="flex min-h-[70vh] flex-col items-center pt-16 md:pt-24 gap-10 px-4">
      <div className="text-center space-y-4">
        <Logo size="lg" />
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
