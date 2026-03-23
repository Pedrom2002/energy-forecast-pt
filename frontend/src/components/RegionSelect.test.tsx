import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import RegionSelect from './RegionSelect'

describe('RegionSelect', () => {
  const defaultProps = {
    value: 'Lisboa' as const,
    onChange: vi.fn(),
  }

  it('renders a select element with all 5 regions', () => {
    render(<RegionSelect {...defaultProps} />)
    const select = screen.getByRole('combobox')
    expect(select).toBeInTheDocument()

    const options = screen.getAllByRole('option')
    expect(options).toHaveLength(5)
    expect(options.map((o) => o.textContent)).toEqual([
      'Alentejo', 'Algarve', 'Centro', 'Lisboa', 'Norte',
    ])
  })

  it('selects the correct value', () => {
    render(<RegionSelect {...defaultProps} value="Norte" />)
    const select = screen.getByRole('combobox') as HTMLSelectElement
    expect(select.value).toBe('Norte')
  })

  it('calls onChange when selection changes', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<RegionSelect value="Lisboa" onChange={onChange} />)

    const select = screen.getByRole('combobox')
    await user.selectOptions(select, 'Algarve')

    expect(onChange).toHaveBeenCalledWith('Algarve')
  })

  it('renders label when provided', () => {
    render(<RegionSelect {...defaultProps} label="Regiao" />)
    expect(screen.getByText('Regiao')).toBeInTheDocument()
  })

  it('uses default aria-label when no label provided', () => {
    render(<RegionSelect {...defaultProps} />)
    expect(screen.getByLabelText('Selecionar regiao')).toBeInTheDocument()
  })

  it('does not set aria-label when label prop is provided', () => {
    render(<RegionSelect {...defaultProps} label="Regiao" id="my-select" />)
    const select = screen.getByRole('combobox')
    expect(select).not.toHaveAttribute('aria-label')
  })

  it('applies custom className', () => {
    render(<RegionSelect {...defaultProps} className="extra-class" />)
    const select = screen.getByRole('combobox')
    expect(select.className).toContain('extra-class')
  })

  it('uses custom id', () => {
    render(<RegionSelect {...defaultProps} id="custom-id" label="Region" />)
    const select = document.getElementById('custom-id')
    expect(select).not.toBeNull()
  })
})
