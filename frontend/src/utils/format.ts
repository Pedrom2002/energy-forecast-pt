import i18n, { formatLocale } from '../i18n';

function currentLocale(locale?: string): string {
  if (locale) return locale;
  try {
    return formatLocale();
  } catch {
    const lang = (i18n?.language || 'en').toLowerCase();
    return lang.startsWith('pt') ? 'pt-PT' : 'en-GB';
  }
}

/**
 * Format a number using the current i18n locale (pt-PT or en-GB).
 * rule: number-formatting — locale-aware formatting
 */
export function formatNumber(value: number, decimals = 1, locale?: string): string {
  return value.toLocaleString(currentLocale(locale), {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Format MW values with unit */
export function formatMW(value: number, decimals = 1, locale?: string): string {
  return `${formatNumber(value, decimals, locale)} MW`;
}

/** Format percentage */
export function formatPercent(value: number, decimals = 1, locale?: string): string {
  return `${formatNumber(value, decimals, locale)}%`;
}

/** Format a date/timestamp using the current locale */
export function formatDateTime(timestamp: string, locale?: string): string {
  return new Date(timestamp).toLocaleString(currentLocale(locale));
}

export function formatDateShort(timestamp: string, locale?: string): string {
  return new Date(timestamp).toLocaleString(currentLocale(locale), {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Format uptime from seconds (language-agnostic: 1h 3m, 2d 4h) */
export function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
}

/** Format a snake_case key to Title Case */
export function formatKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Export array of objects to CSV and trigger download */
export function exportCSV(
  filename: string,
  headers: string[],
  rows: string[][],
): void {
  const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
