import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Card, StatCard, CardSkeleton } from './Card'

describe('Card', () => {
  it('renders children', () => {
    render(<Card>Hello World</Card>)
    expect(screen.getByText('Hello World')).toBeInTheDocument()
  })

  it('renders title when provided', () => {
    render(<Card title="My Card">Content</Card>)
    expect(screen.getByText('My Card')).toBeInTheDocument()
  })

  it('renders subtitle when provided', () => {
    render(<Card title="Title" subtitle="Subtitle text">Content</Card>)
    expect(screen.getByText('Subtitle text')).toBeInTheDocument()
  })

  it('renders action when provided', () => {
    render(<Card title="Title" action={<button>Click</button>}>Content</Card>)
    expect(screen.getByText('Click')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    render(<Card className="custom-class">Content</Card>)
    const section = screen.getByText('Content').closest('section')
    expect(section?.className).toContain('custom-class')
  })

  it('sets aria-label from title', () => {
    render(<Card title="Accessible Card">Content</Card>)
    expect(screen.getByLabelText('Accessible Card')).toBeInTheDocument()
  })

  it('does not render header when no title or action', () => {
    const { container } = render(<Card>Just content</Card>)
    const header = container.querySelector('.border-b')
    expect(header).toBeNull()
  })
})

describe('StatCard', () => {
  it('renders label and value', () => {
    render(<StatCard label="Energy" value="1500 MW" icon={<span>icon</span>} />)
    expect(screen.getByText('Energy')).toBeInTheDocument()
    expect(screen.getByText('1500 MW')).toBeInTheDocument()
  })

  it('renders trend text when provided', () => {
    render(<StatCard label="Load" value={42} icon={<span>i</span>} trend="+5% from yesterday" />)
    expect(screen.getByText('+5% from yesterday')).toBeInTheDocument()
  })

  it('renders icon', () => {
    render(<StatCard label="Test" value="val" icon={<span data-testid="icon">IC</span>} />)
    expect(screen.getByTestId('icon')).toBeInTheDocument()
  })

  it('has accessible aria-label', () => {
    render(<StatCard label="Power" value="500" icon={<span>i</span>} />)
    expect(screen.getByLabelText('Power: 500')).toBeInTheDocument()
  })

  it('has role="status"', () => {
    render(<StatCard label="X" value="Y" icon={<span>i</span>} />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })
})

describe('CardSkeleton', () => {
  it('renders with default 3 skeleton lines', () => {
    const { container } = render(<CardSkeleton />)
    const shimmerDivs = container.querySelectorAll('.skeleton-shimmer')
    // 1 title bar + 3 lines = 4 shimmer elements
    expect(shimmerDivs.length).toBe(4)
  })

  it('renders with custom number of lines', () => {
    const { container } = render(<CardSkeleton lines={5} />)
    const shimmerDivs = container.querySelectorAll('.skeleton-shimmer')
    expect(shimmerDivs.length).toBe(6) // 1 title + 5 lines
  })

  it('has aria-busy attribute', () => {
    render(<CardSkeleton />)
    expect(screen.getByLabelText('A carregar...')).toHaveAttribute('aria-busy', 'true')
  })
})
