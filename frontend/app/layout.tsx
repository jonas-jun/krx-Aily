import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Header } from "@/components/ui/Header";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "fin-Aily-kr — 한국 주식 AI 리서치 분석",
  description: "한국 상장 종목의 최신 애널리스트 리포트를 AI가 통합 분석해드립니다.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className={`${inter.className} bg-white text-slate-900 antialiased`}>
        <Header />
        <main className="mx-auto max-w-3xl px-4 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
