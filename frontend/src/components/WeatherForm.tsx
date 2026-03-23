import { type EnergyData, type Region } from '../api/client';
import RegionSelect from './RegionSelect';
import { Thermometer, Droplets, Wind, CloudRain, Cloud, Gauge } from 'lucide-react';

interface WeatherFormProps {
  data: EnergyData;
  onChange: (data: EnergyData) => void;
  showTimestamp?: boolean;
  idPrefix?: string;
}

function InputField({
  label,
  id,
  icon: Icon,
  value,
  onChange,
  min,
  max,
  step = 0.1,
  unit,
}: {
  label: string;
  id: string;
  icon: React.ComponentType<{ className?: string }>;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
  unit: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="flex items-center gap-1.5 text-xs font-medium text-text-secondary mb-1.5">
        <Icon className="w-3.5 h-3.5" aria-hidden="true" />
        {label}
        <span className="text-text-muted ml-auto" aria-hidden="true">{unit}</span>
      </label>
      <input
        id={id}
        type="number"
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        min={min}
        max={max}
        step={step}
        aria-describedby={`${id}-range`}
        className="block w-full rounded-lg border border-border bg-surface px-3 min-h-[44px] text-sm text-text-primary shadow-xs
          focus-visible:border-primary-500 focus-visible:ring-2 focus-visible:ring-primary-200 focus-visible:outline-none transition tabular-nums"
      />
      <span id={`${id}-range`} className="sr-only">{min} a {max} {unit}</span>
    </div>
  );
}

export default function WeatherForm({ data, onChange, showTimestamp = true, idPrefix = 'wf' }: WeatherFormProps) {
  const update = (field: keyof EnergyData, value: string | number) =>
    onChange({ ...data, [field]: value });

  return (
    <fieldset className="space-y-4">
      <legend className="sr-only">Dados meteorologicos para previsao</legend>

      {showTimestamp && (
        <div>
          <label htmlFor={`${idPrefix}-timestamp`} className="block text-xs font-medium text-text-secondary mb-1.5">
            Timestamp (ISO 8601)
          </label>
          <input
            id={`${idPrefix}-timestamp`}
            type="datetime-local"
            value={data.timestamp.slice(0, 16)}
            onChange={(e) => update('timestamp', e.target.value + ':00')}
            className="block w-full rounded-lg border border-border bg-surface px-3 min-h-[44px] text-sm text-text-primary shadow-xs cursor-pointer
              focus-visible:border-primary-500 focus-visible:ring-2 focus-visible:ring-primary-200 focus-visible:outline-none transition"
          />
        </div>
      )}

      <RegionSelect
        id={`${idPrefix}-region`}
        label="Regiao"
        value={data.region as Region}
        onChange={(r) => update('region', r)}
      />

      <div className="grid grid-cols-2 gap-3">
        <InputField
          id={`${idPrefix}-temp`}
          label="Temperatura"
          icon={Thermometer}
          value={data.temperature}
          onChange={(v) => update('temperature', v)}
          min={-20}
          max={50}
          unit="°C"
        />
        <InputField
          id={`${idPrefix}-hum`}
          label="Humidade"
          icon={Droplets}
          value={data.humidity}
          onChange={(v) => update('humidity', v)}
          min={0}
          max={100}
          unit="%"
        />
        <InputField
          id={`${idPrefix}-wind`}
          label="Vento"
          icon={Wind}
          value={data.wind_speed}
          onChange={(v) => update('wind_speed', v)}
          min={0}
          max={200}
          unit="km/h"
        />
        <InputField
          id={`${idPrefix}-precip`}
          label="Precipitacao"
          icon={CloudRain}
          value={data.precipitation}
          onChange={(v) => update('precipitation', v)}
          min={0}
          max={500}
          unit="mm"
        />
        <InputField
          id={`${idPrefix}-cloud`}
          label="Nebulosidade"
          icon={Cloud}
          value={data.cloud_cover}
          onChange={(v) => update('cloud_cover', v)}
          min={0}
          max={100}
          unit="%"
        />
        <InputField
          id={`${idPrefix}-pressure`}
          label="Pressao"
          icon={Gauge}
          value={data.pressure}
          onChange={(v) => update('pressure', v)}
          min={900}
          max={1100}
          unit="hPa"
        />
      </div>
    </fieldset>
  );
}
