import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDebounce } from './useDebounce'

describe('useDebounce', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('delays invocation by the specified delay', () => {
    const fn = vi.fn()
    const { result } = renderHook(() => useDebounce(fn, 300))

    act(() => {
      result.current('hello')
    })

    expect(fn).not.toHaveBeenCalled()

    act(() => {
      vi.advanceTimersByTime(300)
    })

    expect(fn).toHaveBeenCalledTimes(1)
    expect(fn).toHaveBeenCalledWith('hello')
  })

  it('uses default 500ms delay', () => {
    const fn = vi.fn()
    const { result } = renderHook(() => useDebounce(fn))

    act(() => {
      result.current()
    })

    act(() => {
      vi.advanceTimersByTime(499)
    })
    expect(fn).not.toHaveBeenCalled()

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('resets timer on rapid calls', () => {
    const fn = vi.fn()
    const { result } = renderHook(() => useDebounce(fn, 200))

    act(() => {
      result.current('a')
    })

    act(() => {
      vi.advanceTimersByTime(150)
    })

    act(() => {
      result.current('b')
    })

    act(() => {
      vi.advanceTimersByTime(200)
    })

    expect(fn).toHaveBeenCalledTimes(1)
    expect(fn).toHaveBeenCalledWith('b')
  })

  it('does not fire if not enough time passes', () => {
    const fn = vi.fn()
    const { result } = renderHook(() => useDebounce(fn, 500))

    act(() => {
      result.current()
    })

    act(() => {
      vi.advanceTimersByTime(200)
    })

    expect(fn).not.toHaveBeenCalled()
  })
})
