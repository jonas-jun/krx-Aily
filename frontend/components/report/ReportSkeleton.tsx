export function ReportSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="py-6 text-center space-y-4">
        <div className="relative w-12 h-12 mx-auto">
          <div className="absolute inset-0 border-4 border-red-100 rounded-full" />
          <div className="absolute inset-0 border-4 border-red-600 rounded-full border-t-transparent animate-spin" />
        </div>
        <p className="text-slate-500 font-medium">AI가 리포트를 분석하고 있습니다...</p>
        <p className="text-xs text-slate-400">10~30초 소요될 수 있습니다</p>
      </div>
      <div className="rounded-xl border border-slate-200 bg-slate-50 h-24" />
      <div className="rounded-xl border border-slate-200 bg-slate-50 h-20" />
      <div className="rounded-xl border border-slate-200 bg-slate-50 h-40" />
      <div className="rounded-xl border border-slate-200 bg-slate-50 h-32" />
    </div>
  );
}
