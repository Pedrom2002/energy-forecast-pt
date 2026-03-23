import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  formatNumber,
  formatMW,
  formatPercent,
  formatDateTime,
  formatDateShort,
  formatUptime,
  formatKey,
  exportCSV,
} from './format'

describe('formatNumber', () => {
  it('formats with default 1 decimal place', () => {
    const result = formatNumber(1500.3)
    // pt-PT uses dot as thousands separator and comma as decimal
    expect(result).toContain('1')
    expect(result).toContain('500')
  })

  it('formats with custom decimal places', () => {
    const result = formatNumber(42.567, 2)
    expect(result).toMatch(/42[,.]57/)
  })

  it('formats zero', () => {
    const result = formatNumber(0, 1)
    expect(result).toMatch(/0[,.]0/)
  })

  it('formats negative numbers', () => {
    const result = formatNumber(-123.4, 1)
    expect(result).toContain('123')
  })

  it('pads with trailing zeros when needed', () => {
    const result = formatNumber(5, 2)
    expect(result).toMatch(/5[,.]00/)
  })
})

describe('formatMW', () => {
  it('appends MW unit', () => {
    expect(formatMW(1500)).toContain('MW')
  })

  it('uses custom decimals', () => {
    const result = formatMW(100, 0)
    expect(result).toContain('MW')
    expect(result).toContain('100')
  })
})

describe('formatPercent', () => {
  it('appends percent sign', () => {
    const result = formatPercent(85.5)
    expect(result).toContain('%')
    expect(result).toContain('85')
  })

  it('uses custom decimals', () => {
    const result = formatPercent(33.333, 2)
    expect(result).toContain('%')
  })
})

describe('formatDateTime', () => {
  it('formats an ISO timestamp', () => {
    const result = formatDateTime('2024-06-15T14:30:00Z')
    // Should produce a pt-PT locale string
    expect(typeof result).toBe('string')
    expect(result.length).toBeGreaterThan(0)
  })
})

describe('formatDateShort', () => {
  it('returns day/month and hour:minute', () => {
    const result = formatDateShort('2024-06-15T14:30:00Z')
    expect(typeof result).toBe('string')
    expect(result.length).toBeGreaterThan(0)
  })
})

describe('formatUptime', () => {
  it('formats seconds', () => {
    expect(formatUptime(30)).toBe('30s')
  })

  it('formats minutes', () => {
    expect(formatUptime(120)).toBe('2m')
  })

  it('formats hours and minutes', () => {
    expect(formatUptime(3661)).toBe('1h 1m')
  })

  it('formats days and hours', () => {
    expect(formatUptime(90000)).toBe('1d 1h')
  })

  it('floors fractional seconds', () => {
    expect(formatUptime(59.9)).toBe('59s')
  })

  it('edge: exactly 60 seconds is minutes', () => {
    expect(formatUptime(60)).toBe('1m')
  })

  it('edge: exactly 3600 seconds is hours', () => {
    expect(formatUptime(3600)).toBe('1h 0m')
  })
})

describe('formatKey', () => {
  it('converts snake_case to Title Case', () => {
    expect(formatKey('wind_speed')).toBe('Wind Speed')
  })

  it('handles single word', () => {
    expect(formatKey('temperature')).toBe('Temperature')
  })

  it('handles multiple underscores', () => {
    expect(formatKey('cloud_cover_percent')).toBe('Cloud Cover Percent')
  })
})

describe('exportCSV', () => {
  beforeEach(() => {
    // Mock URL.createObjectURL and revokeObjectURL
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:mock-url'),
      revokeObjectURL: vi.fn(),
    })
  })

  it('creates a CSV blob and triggers download', () => {
    const clickSpy = vi.fn()
    const createElementSpy = vi.spyOn(document, 'createElement').mockReturnValue({
      href: '',
      download: '',
      click: clickSpy,
    } as unknown as HTMLAnchorElement)

    exportCSV('test.csv', ['A', 'B'], [['1', '2'], ['3', '4']])

    expect(createElementSpy).toHaveBeenCalledWith('a')
    expect(clickSpy).toHaveBeenCalled()
    expect(URL.createObjectURL).toHaveBeenCalled()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')

    createElementSpy.mockRestore()
  })
})
