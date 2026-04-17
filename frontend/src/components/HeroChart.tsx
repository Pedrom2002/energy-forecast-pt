import { useEffect, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api, type EnergyData, type PredictionResponse } from '../api/client';
import { useTranslation } from 'react-i18next';

interface ChartPoint {
  hour: number;
  hourLabel: string;
  predicted: number;
  lower: number;
  delta: number; // upper - lower (used with stackId for band rendering)
  upper: number;
}

function buildForecastPayload(): EnergyData[] {
  const now = new Date();
  now.setMinutes(0, 0, 0);
  const items: EnergyData[] = [];
  for (let i = 0; i < 24; i++) {
    const ts = new Date(now.getTime() + i * 3600_000);
    const hour = ts.getHours();
    // Smooth temperature: peak at 15h, trough around 03h.
    const tempPhase = ((hour - 15) / 24) * 2 * Math.PI;
    const temperature = 17 + 5 * Math.cos(tempPhase); // ranges ~12..22
    const humidity = 60 + 10 * Math.cos((hour * Math.PI) / 12);
    const wind_speed = 8 + 4 * Math.random();
    const cloud_cover = 40 + 20 * Math.sin((hour * Math.PI) / 24);
    items.push({
      timestamp: ts.toISOString(),
      region: 'Lisboa',
      temperature,
      humidity,
      wind_speed,
      precipitation: 0,
      cloud_cover,
      pressure: 1015,
    });
  }
  return items;
}

function toChartPoints(predictions: PredictionResponse[]): ChartPoint[] {
  return predictions.map((p) => {
    const d = new Date(p.timestamp);
    const hour = d.getHours();
    return {
      hour,
      hourLabel: `${hour}h`,
      predicted: Math.round(p.predicted_consumption_mw),
      lower: Math.round(p.confidence_interval_lower),
      upper: Math.round(p.confidence_interval_upper),
      delta: Math.max(
        0,
        Math.round(p.confidence_interval_upper - p.confidence_interval_lower),
      ),
    };
  });
}

interface TooltipPayloadEntry {
  payload?: ChartPoint;
}

function HeroTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
}) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0]?.payload;
  if (!point) return null;
  return (
    <div
      className="rounded-lg border border-primary-400/30 bg-[#0b1020]/95 px-3 py-2 text-xs
        text-text-primary shadow-lg backdrop-blur-xl font-mono tabular-nums"
    >
      <div className="font-semibold">
        {point.hour.toString().padStart(2, '0')}:00 · {point.predicted} MW
      </div>
      <div className="text-[10px] text-primary-300 mt-0.5 uppercase tracking-wider">
        CI {point.lower} — {point.upper}
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div
      className="h-48 md:h-56 w-full rounded-lg bg-surface-dim skeleton-shimmer"
      aria-hidden
    />
  );
}

function OfflineState() {
  const { t } = useTranslation();
  return (
    <div className="h-48 md:h-56 w-full flex items-center justify-center rounded-lg border border-dashed border-border">
      <span className="text-xs font-mono uppercase tracking-wider text-text-muted">
        {t('hero.offline')}
      </span>
    </div>
  );
}

export default function HeroChart() {
  const [data, setData] = useState<ChartPoint[] | null>(null);
  const [error, setError] = useState<boolean>(false);
  const { t } = useTranslation();

  useEffect(() => {
    let cancelled = false;
    const items = buildForecastPayload();
    api
      .predictBatch(items)
      .then((res) => {
        if (cancelled) return;
        setData(toChartPoints(res.predictions));
      })
      .catch(() => {
        if (cancelled) return;
        setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <OfflineState />;
  if (!data) return <Skeleton />;

  const lastIdx = data.length - 1;

  return (
    <div
      role="img"
      aria-label={t('hero.aria')}
      className="h-48 md:h-56 w-full"
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 16, right: 12, left: 4, bottom: 4 }}>
          <defs>
            <linearGradient id="heroBand" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.28} />
              <stop offset="100%" stopColor="#22d3ee" stopOpacity={0.04} />
            </linearGradient>
            <linearGradient id="heroLine" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#22d3ee" />
              <stop offset="100%" stopColor="#fbbf24" />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
          <XAxis
            dataKey="hourLabel"
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#6b7a92', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
            interval={3}
          />
          <YAxis
            hide
            domain={[
              (dataMin: number) => Math.floor(dataMin * 0.95),
              (dataMax: number) => Math.ceil(dataMax * 1.05),
            ]}
          />
          <Tooltip
            content={<HeroTooltip />}
            cursor={{ stroke: 'rgba(34,211,238,0.4)', strokeWidth: 1, strokeDasharray: '3 3' }}
          />
          {/* Invisible baseline to stack the delta on top of */}
          <Area
            type="monotone"
            dataKey="lower"
            stackId="ci"
            stroke="none"
            fill="transparent"
            isAnimationActive={false}
            activeDot={false}
          />
          {/* The visible CI band: lower + delta, only delta is filled */}
          <Area
            type="monotone"
            dataKey="delta"
            stackId="ci"
            stroke="none"
            fill="url(#heroBand)"
            fillOpacity={1}
            isAnimationActive
            activeDot={false}
          />
          {/* Predicted line on top */}
          <Area
            type="monotone"
            dataKey="predicted"
            stroke="url(#heroLine)"
            strokeWidth={2.5}
            fill="transparent"
            dot={(props: { cx?: number; cy?: number; index?: number }) => {
              const { cx, cy, index } = props;
              if (
                cx === undefined ||
                cy === undefined ||
                (index !== 0 && index !== lastIdx)
              ) {
                return <g />;
              }
              const color = index === 0 ? '#22d3ee' : '#fbbf24';
              return (
                <circle
                  cx={cx}
                  cy={cy}
                  r={4}
                  fill={color}
                  stroke="#05080f"
                  strokeWidth={2}
                />
              );
            }}
            activeDot={{ r: 4, fill: '#22d3ee', stroke: '#05080f', strokeWidth: 2 }}
            isAnimationActive
          />
          <text
            x="100%"
            y={12}
            textAnchor="end"
            fill="#6b7a92"
            fontSize={10}
            fontFamily="JetBrains Mono, monospace"
          >
            MW
          </text>
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
