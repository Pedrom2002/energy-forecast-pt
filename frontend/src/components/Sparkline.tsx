import { AreaChart, Area, ResponsiveContainer } from 'recharts';

interface SparklineProps {
  data: number[];
  height?: number;
  color?: 'primary' | 'success' | 'accent';
  /** If true, render as filled area; otherwise line-only. */
  filled?: boolean;
  className?: string;
}

export function Sparkline({
  data,
  height = 40,
  color = 'primary',
  filled = true,
  className,
}: SparklineProps) {
  // Convert to Recharts format
  const chartData = data.map((v, i) => ({ i, v }));

  const strokeMap = { primary: '#f59e0b', success: '#10b981', accent: '#f97316' };
  const fillMap = { primary: '#fbbf24', success: '#10b981', accent: '#fb923c' };

  return (
    <div className={className} style={{ height, width: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
          <defs>
            <linearGradient id={`spark-${color}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={fillMap[color]} stopOpacity={0.5} />
              <stop offset="100%" stopColor={fillMap[color]} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="v"
            stroke={strokeMap[color]}
            strokeWidth={1.5}
            fill={filled ? `url(#spark-${color})` : 'transparent'}
            isAnimationActive={false}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
