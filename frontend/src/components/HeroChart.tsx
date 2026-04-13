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
    <div className="rounded-md border border-amber-200/40 bg-white/95 px-2.5 py-1.5 text-xs text-slate-700 shadow-md backdrop-blur dark:border-amber-500/30 dark:bg-slate-900/95 dark:text-slate-200">
      <div className="font-medium">
        {point.hour.toString().padStart(2, '0')}h00 · {point.predicted} MW
      </div>
      <div className="text-[10px] text-slate-500 dark:text-slate-400">
        CI {point.lower} – {point.upper}
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div
      className="h-48 md:h-56 w-full animate-pulse rounded-lg bg-gradient-to-b from-amber-100/40 to-amber-50/10 dark:from-amber-500/10 dark:to-amber-500/5"
      aria-hidden
    />
  );
}

function OfflineState() {
  return (
    <div className="h-48 md:h-56 w-full flex items-center justify-center rounded-lg border border-dashed border-slate-200/60 dark:border-slate-700/60">
      <span className="text-xs text-slate-400 dark:text-slate-500">Demo offline</span>
    </div>
  );
}

export default function HeroChart() {
  const [data, setData] = useState<ChartPoint[] | null>(null);
  const [error, setError] = useState<boolean>(false);

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
      aria-label="Próximas 24 horas de previsão de consumo para Lisboa"
      className="h-48 md:h-56 w-full"
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 16, right: 12, left: 4, bottom: 4 }}>
          <defs>
            <linearGradient id="heroBand" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.18} />
              <stop offset="100%" stopColor="#f59e0b" stopOpacity={0.06} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(100,116,139,0.1)" vertical={false} />
          <XAxis
            dataKey="hourLabel"
            axisLine={false}
            tickLine={false}
            tick={{ fill: 'rgba(100,116,139,0.7)', fontSize: 11 }}
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
            cursor={{ stroke: 'rgba(245,158,11,0.35)', strokeWidth: 1 }}
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
            stroke="#f59e0b"
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
              return (
                <circle
                  cx={cx}
                  cy={cy}
                  r={3.5}
                  fill="#f59e0b"
                  stroke="#fff"
                  strokeWidth={1.5}
                />
              );
            }}
            activeDot={{ r: 4, fill: '#f59e0b', stroke: '#fff', strokeWidth: 1.5 }}
            isAnimationActive
          />
          <text
            x="100%"
            y={12}
            textAnchor="end"
            className="fill-slate-400 dark:fill-slate-500"
            fontSize={10}
          >
            MW
          </text>
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
