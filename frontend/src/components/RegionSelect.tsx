import { REGIONS, type Region } from '../api/client';

interface RegionSelectProps {
  value: Region;
  onChange: (region: Region) => void;
  className?: string;
}

const REGION_EMOJI: Record<Region, string> = {
  Norte: '🏔️',
  Centro: '🏛️',
  Lisboa: '🌉',
  Alentejo: '🌾',
  Algarve: '🏖️',
};

export default function RegionSelect({ value, onChange, className = '' }: RegionSelectProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as Region)}
      className={`block w-full rounded-lg border border-border bg-white px-3 py-2.5 text-sm text-text-primary shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-200 focus:outline-none transition ${className}`}
    >
      {REGIONS.map((r) => (
        <option key={r} value={r}>
          {REGION_EMOJI[r]} {r}
        </option>
      ))}
    </select>
  );
}
