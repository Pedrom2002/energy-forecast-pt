/**
 * Chart skeleton with axis placeholders
 * rule: loading-chart — skeleton instead of empty axis frame
 */
export function ChartSkeleton({ height = 350 }: { height?: number }) {
  return (
    <div
      className="bg-surface rounded-xl border border-border shadow-sm overflow-hidden"
      aria-busy="true"
      aria-label="A carregar grafico..."
    >
      {/* Header */}
      <div className="px-5 sm:px-6 py-4 border-b border-border">
        <div className="h-4 w-40 bg-surface-bright rounded skeleton-shimmer" />
        <div className="h-3 w-56 bg-surface-bright rounded skeleton-shimmer mt-2" />
      </div>

      {/* Chart area */}
      <div className="p-5 sm:p-6">
        <div className="relative" style={{ height }}>
          {/* Y-axis */}
          <div className="absolute left-0 top-0 bottom-8 w-10 flex flex-col justify-between py-2">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="h-2.5 w-8 bg-surface-bright rounded skeleton-shimmer" style={{ animationDelay: `${i * 80}ms` }} />
            ))}
          </div>

          {/* Grid lines */}
          <div className="absolute left-12 right-0 top-0 bottom-8 flex flex-col justify-between">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="h-px bg-border/40" />
            ))}
          </div>

          {/* Fake data line */}
          <div className="absolute left-12 right-0 top-4 bottom-12">
            <svg viewBox="0 0 100 40" className="w-full h-full" preserveAspectRatio="none">
              <path
                d="M0,30 C10,28 20,15 30,18 C40,21 50,10 60,12 C70,14 80,22 90,8 L100,12"
                fill="none"
                stroke="var(--color-border)"
                strokeWidth="0.8"
                strokeDasharray="2 2"
              />
            </svg>
          </div>

          {/* X-axis */}
          <div className="absolute left-12 right-0 bottom-0 h-6 flex justify-between items-center">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-2.5 w-10 bg-surface-bright rounded skeleton-shimmer" style={{ animationDelay: `${i * 60}ms` }} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
