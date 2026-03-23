/**
 * Format a number using pt-PT locale (e.g., 1.500,3)
 * rule: number-formatting — locale-aware formatting
 */
export function formatNumber(value: number, decimals = 1): string {
  return value.toLocaleString('pt-PT', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/**
 * Format MW values with unit
 */
export function formatMW(value: number, decimals = 1): string {
  return `${formatNumber(value, decimals)} MW`;
}

/**
 * Format percentage
 */
export function formatPercent(value: number, decimals = 1): string {
  return `${formatNumber(value, decimals)}%`;
}

/**
 * Format a date/timestamp using pt-PT locale
 */
export function formatDateTime(timestamp: string): string {
  return new Date(timestamp).toLocaleString('pt-PT');
}

export function formatDateShort(timestamp: string): string {
  return new Date(timestamp).toLocaleString('pt-PT', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Format uptime from seconds
 */
export function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
}

/**
 * Format a snake_case key to Title Case
 */
export function formatKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Export array of objects to CSV and trigger download
 */
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
