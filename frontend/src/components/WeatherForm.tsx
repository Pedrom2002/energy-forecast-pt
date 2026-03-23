import { type EnergyData, type Region } from '../api/client';
import RegionSelect from './RegionSelect';
import { Thermometer, Droplets, Wind, CloudRain, Cloud, Gauge } from 'lucide-react';

interface WeatherFormProps {
  data: EnergyData;
  onChange: (data: EnergyData) => void;
  showTimestamp?: boolean;
}

function InputField({
  label,
  icon: Icon,
  value,
  onChange,
  min,
  max,
  step = 0.1,
  unit,
}: {
  label: string;
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
      <label className="flex items-center gap-1.5 text-xs font-medium text-text-secondary mb-1.5">
        <Icon className="w-3.5 h-3.5" />
        {label}
        <span className="text-text-muted ml-auto">{unit}</span>
      </label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        min={min}
        max={max}
        step={step}
        className="block w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-text-primary shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-200 focus:outline-none transition"
      />
    </div>
  );
}

export default function WeatherForm({ data, onChange, showTimestamp = true }: WeatherFormProps) {
  const update = (field: keyof EnergyData, value: string | number) =>
    onChange({ ...data, [field]: value });

  return (
    <div className="space-y-4">
      {showTimestamp && (
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1.5">
            Timestamp (ISO 8601)
          </label>
          <input
            type="datetime-local"
            value={data.timestamp.slice(0, 16)}
            onChange={(e) => update('timestamp', e.target.value + ':00')}
            className="block w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-text-primary shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-200 focus:outline-none transition"
          />
        </div>
      )}

      <div>
        <label className="block text-xs font-medium text-text-secondary mb-1.5">Regiao</label>
        <RegionSelect value={data.region as Region} onChange={(r) => update('region', r)} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <InputField
          label="Temperatura"
          icon={Thermometer}
          value={data.temperature}
          onChange={(v) => update('temperature', v)}
          min={-20}
          max={50}
          unit="°C"
        />
        <InputField
          label="Humidade"
          icon={Droplets}
          value={data.humidity}
          onChange={(v) => update('humidity', v)}
          min={0}
          max={100}
          unit="%"
        />
        <InputField
          label="Vento"
          icon={Wind}
          value={data.wind_speed}
          onChange={(v) => update('wind_speed', v)}
          min={0}
          max={200}
          unit="km/h"
        />
        <InputField
          label="Precipitacao"
          icon={CloudRain}
          value={data.precipitation}
          onChange={(v) => update('precipitation', v)}
          min={0}
          max={500}
          unit="mm"
        />
        <InputField
          label="Nebulosidade"
          icon={Cloud}
          value={data.cloud_cover}
          onChange={(v) => update('cloud_cover', v)}
          min={0}
          max={100}
          unit="%"
        />
        <InputField
          label="Pressao"
          icon={Gauge}
          value={data.pressure}
          onChange={(v) => update('pressure', v)}
          min={900}
          max={1100}
          unit="hPa"
        />
      </div>
    </div>
  );
}
