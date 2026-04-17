import { REGIONS, type Region } from '../api/client';
import { MapPin } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface RegionSelectProps {
  value: Region;
  onChange: (region: Region) => void;
  className?: string;
  id?: string;
  label?: string;
}

export default function RegionSelect({ value, onChange, className = '', id = 'region-select', label }: RegionSelectProps) {
  const { t } = useTranslation();
  return (
    <div>
      {label && (
        <label htmlFor={id} className="flex items-center gap-1.5 text-xs font-medium text-text-secondary mb-1.5">
          <MapPin className="w-3.5 h-3.5" aria-hidden="true" />
          {label}
        </label>
      )}
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value as Region)}
        aria-label={label ? undefined : t('predict.form.regionAria')}
        className={`block w-full rounded-lg border border-border bg-surface-dim px-3 min-h-[44px] text-sm text-text-primary cursor-pointer
          hover:border-border-strong focus-visible:border-primary-400 focus-visible:ring-2 focus-visible:ring-primary-100 focus-visible:outline-none transition ${className}`}
      >
        {REGIONS.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>
    </div>
  );
}
