import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastContainer, toast } from './Toast'

describe('ToastContainer', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders nothing when there are no messages', () => {
    const { container } = render(<ToastContainer />)
    expect(container.innerHTML).toBe('')
  })

  it('displays a success toast', () => {
    render(<ToastContainer />)

    act(() => {
      toast.success('Operation completed')
    })

    expect(screen.getByText('Operation completed')).toBeInTheDocument()
  })

  it('displays an error toast', () => {
    render(<ToastContainer />)

    act(() => {
      toast.error('Something went wrong')
    })

    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('displays an info toast', () => {
    render(<ToastContainer />)

    act(() => {
      toast.info('FYI message')
    })

    expect(screen.getByText('FYI message')).toBeInTheDocument()
  })

  it('auto-dismisses after 4 seconds', () => {
    render(<ToastContainer />)

    act(() => {
      toast.success('Temporary')
    })

    expect(screen.getByText('Temporary')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(4000)
    })

    expect(screen.queryByText('Temporary')).not.toBeInTheDocument()
  })

  it('can be manually dismissed with close button', async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    render(<ToastContainer />)

    act(() => {
      toast.info('Dismissable')
    })

    expect(screen.getByText('Dismissable')).toBeInTheDocument()

    const closeButton = screen.getByRole('button', { name: /fechar/i })
    await user.click(closeButton)

    expect(screen.queryByText('Dismissable')).not.toBeInTheDocument()
  })

  it('displays multiple toasts simultaneously', () => {
    render(<ToastContainer />)

    act(() => {
      toast.success('First')
      toast.error('Second')
      toast.info('Third')
    })

    expect(screen.getByText('First')).toBeInTheDocument()
    expect(screen.getByText('Second')).toBeInTheDocument()
    expect(screen.getByText('Third')).toBeInTheDocument()
  })

  it('has correct aria-live attribute', () => {
    render(<ToastContainer />)

    act(() => {
      toast.info('Accessible')
    })

    const container = screen.getByLabelText('Notificacoes')
    expect(container).toHaveAttribute('aria-live', 'polite')
  })

  it('toast messages have role="status"', () => {
    render(<ToastContainer />)

    act(() => {
      toast.success('With role')
    })

    const statuses = screen.getAllByRole('status')
    expect(statuses.length).toBeGreaterThanOrEqual(1)
  })
})
