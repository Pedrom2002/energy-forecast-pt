import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ChartSkeleton } from './ChartSkeleton'

describe('ChartSkeleton', () => {
  it('renders with default height of 350', () => {
    const { container } = render(<ChartSkeleton />)
    const chartArea = container.querySelector('[style*="height"]') as HTMLElement
    expect(chartArea).not.toBeNull()
    expect(chartArea.style.height).toBe('350px')
  })

  it('renders with custom height', () => {
    const { container } = render(<ChartSkeleton height={200} />)
    const chartArea = container.querySelector('[style*="height"]') as HTMLElement
    expect(chartArea.style.height).toBe('200px')
  })

  it('has aria-busy attribute', () => {
    render(<ChartSkeleton />)
    expect(screen.getByLabelText('Loading...')).toHaveAttribute('aria-busy', 'true')
  })

  it('renders Y-axis placeholders', () => {
    const { container } = render(<ChartSkeleton />)
    // 5 Y-axis items + 6 X-axis items + header shimmer elements
    const shimmerElements = container.querySelectorAll('.skeleton-shimmer')
    expect(shimmerElements.length).toBeGreaterThanOrEqual(5)
  })

  it('renders an SVG path for the fake data line', () => {
    const { container } = render(<ChartSkeleton />)
    const svg = container.querySelector('svg')
    expect(svg).not.toBeNull()
    const path = svg?.querySelector('path')
    expect(path).not.toBeNull()
  })
})
